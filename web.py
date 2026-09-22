import importlib
import hmac
import os

SOCKETIO_ASYNC_MODE = 'threading'
eventlet = None
# eventlet 的绿色 DNS 在部分服务器环境会导致出站 HTTPS 解析超时（价格无法更新），
# 可设置 WEB_DISABLE_EVENTLET=1 强制使用 threading 模式。
_disable_eventlet = str(os.getenv('WEB_DISABLE_EVENTLET', '') or '').strip().lower() in ('1', 'true', 'yes', 'on')
if not _disable_eventlet:
    try:
        eventlet = importlib.import_module('eventlet')
        eventlet.monkey_patch()
        SOCKETIO_ASYNC_MODE = 'eventlet'
    except ImportError:
        pass

from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, session, url_for
import json
import hashlib
import secrets
import requests
import logging
import sys
from datetime import datetime, timezone, timedelta
from functools import wraps
import threading
import time
from flask_socketio import SocketIO

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# AlphaEngine 只读状态文件：默认与 Web 位于同一项目根目录，也可由服务器环境变量覆盖。
_alpha_engine_state_file = os.getenv('ALPHA_ENGINE_STATE_FILE', '').strip()
if _alpha_engine_state_file:
    alpha_engine_state_file = (
        _alpha_engine_state_file
        if os.path.isabs(_alpha_engine_state_file)
        else os.path.abspath(os.path.join(os.path.dirname(__file__), _alpha_engine_state_file))
    )
else:
    alpha_engine_state_file = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'AlphaEngine', 'data', 'state.json'
    ))

ALPHA_ENGINE_REGIME_LABELS = {
    'BEAR_BOTTOM': '熊底',
    'RECOVERY': '牛初',
    'BULL': '牛中',
    'DEEP_BULL': '牛顶',
    'BULL_COOLING': '转熊',
    'BEAR': '熊中',
    'BEAR_DEEP': '深熊',
}


def load_alpha_engine_regime():
    """只读 AlphaEngine 的 regime.current，不修改其项目或状态文件。"""
    try:
        with open(alpha_engine_state_file, 'r', encoding='utf-8') as state_file:
            state_data = json.load(state_file)
        regime_data = state_data.get('regime', {}) if isinstance(state_data, dict) else {}
        current = regime_data.get('current') if isinstance(regime_data, dict) else None
        if current is None and isinstance(state_data, dict):
            current = state_data.get('current')
        current = str(current or '').strip().upper()
        return current if current in ALPHA_ENGINE_REGIME_LABELS else ''
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return ''


def load_alpha_engine_alpha():
    """只读 AlphaEngine 的 alpha.current，不修改其项目或状态文件。"""
    try:
        with open(alpha_engine_state_file, 'r', encoding='utf-8') as state_file:
            state_data = json.load(state_file)
        alpha_data = state_data.get('alpha', {}) if isinstance(state_data, dict) else {}
        current = alpha_data.get('current') if isinstance(alpha_data, dict) else None
        if current is None:
            current = state_data.get('alpha', state_data.get('alpha.current'))
        return float(current) if current is not None else 0.0
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0.0


def load_alpha_engine_ma():
    """只读 AlphaEngine 状态文件中的 K 线趋势摘要 (state["ma"])。

    容错: 文件缺失 / 无 ma / 字段类型异常 → None, 不抛错。
    """
    try:
        with open(alpha_engine_state_file, 'r', encoding='utf-8') as state_file:
            state_data = json.load(state_file)
        ma_data = state_data.get('ma') if isinstance(state_data, dict) else None
        if not isinstance(ma_data, dict):
            return None
        available = ma_data.get('available')
        zone = ma_data.get('zone')
        as_of = ma_data.get('as_of')
        if available is not None and not isinstance(available, bool):
            return None
        if zone is not None and not isinstance(zone, str):
            return None
        if as_of is not None and not isinstance(as_of, str):
            return None
        return {
            'available': bool(available),
            'zone': zone or None,
            'as_of': as_of or None,
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def alpha_engine_regime_label(regime):
    return ALPHA_ENGINE_REGIME_LABELS.get(regime, '未知')


def alpha_engine_ma_signature(ma):
    """K 线趋势变化指纹 (available/zone/as_of 任一变化即算变化); 非 dict → None。"""
    if not isinstance(ma, dict):
        return None
    return (bool(ma.get('available')), ma.get('zone'), ma.get('as_of'))


def alpha_engine_update_changed(market_data, new_regime, new_alpha, new_ma):
    """regime / alpha / K 线趋势 任一变化 → 需要推送前端。"""
    if not isinstance(market_data, dict):
        return True
    if market_data.get('alpha_engine_regime') != new_regime:
        return True
    if market_data.get('cycle') != alpha_engine_regime_label(new_regime):
        return True
    try:
        old_alpha = float(market_data.get('alpha_engine_alpha', 0.0))
    except (TypeError, ValueError):
        old_alpha = 0.0
    if abs(old_alpha - new_alpha) > 0.001:
        return True
    return (alpha_engine_ma_signature(market_data.get('alpha_engine_ma'))
            != alpha_engine_ma_signature(new_ma))


# Promo 发帖数据只通过 HTTP 推送进入 Web (POST /api/update_post_feed),
# Web 不再直读 Promo 项目文件。

# 帖子类型中文标签
POST_TYPE_LABELS = {
    'launch': '启动',
    'regime_switch': '牛熊切换',
    'open_position': '开仓',
    'close_position': '平仓',
    'cycle_summary': '周期总结',
    'milestone': '里程碑',
    'weekly_report': '周报',
    'ai_regime_update': 'AI市场判断',
    'alphaengine': 'Alpha分析',
    'hot_content': '热点内容',
}
POST_FEED_PAGE_SIZE = 20

# 过滤掉的发帖类型 (如热点内容, 不展示不加载)
POST_TYPE_EXCLUDED = {'hot_content', 'hot'}


def _parse_post_timestamp(value):
    """解析发帖时间戳为可比较的 UTC datetime。

    兼容多种格式: Z / +08:00 / +00:00 / 无时区 / 带毫秒。
    解析失败返回 None (调用方回退字符串排序)。
    """
    raw_value = str(value or '').strip()
    if not raw_value:
        return None

    # 规范化: Z 结尾 → +00:00 (fromisoformat 在旧版本不支持 Z)
    text = raw_value
    if text.endswith('Z') or text.endswith('z'):
        text = text[:-1] + '+00:00'

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # 尝试常见格式
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    # 无时区 → 视为 UTC
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _post_sort_key(post):
    """发帖记录排序 key: 真实时间优先, 无法解析时回退字符串。"""
    dt = _parse_post_timestamp(post.get('timestamp'))
    if dt is not None:
        return (0, dt.timestamp())
    return (1, str(post.get('timestamp') or ''))


def _normalize_post_record(record, source):
    """把 Promo 归档记录 / AlphaEngine 桥记录规范化为前端展示结构。

    热点内容 (hot_content) 等被排除的类型直接返回 None, 不加载不展示。
    """
    if not isinstance(record, dict):
        return None
    post_type = str(record.get('post_type') or record.get('type') or 'alphaengine').strip()
    if post_type.lower() in POST_TYPE_EXCLUDED:
        return None
    timestamp = str(record.get('timestamp') or record.get('ts') or '').strip()
    content = str(record.get('content') or '').strip()
    if not content:
        return None
    label = str(record.get('label') or '').strip()
    platform = str(record.get('platform') or 'alpha_engine').strip()
    extra = record.get('extra') if isinstance(record.get('extra'), dict) else {}
    return {
        'timestamp': timestamp,
        'date': str(record.get('date') or '')[:10],
        'post_type': post_type,
        'type_label': POST_TYPE_LABELS.get(post_type, post_type),
        'label': label,
        'content': content,
        'platform': platform,
        'success': bool(record.get('success', True)),
        'post_id': str(record.get('post_id') or '').strip(),
        'post_url': str(record.get('post_url') or '').strip(),
        'alpha': extra.get('alpha'),
        'regime': extra.get('new_regime') or extra.get('cycle') or '',
        'source': source,
    }


def load_promo_posts(limit=200):
    """加载发帖数据 (只读本地 data/post_feed.json, 由 Promo/AlphaEngine 通过 HTTP 推送维护)。

    文件不存在或为空时返回空列表; Web 不再回退读取 Promo 项目文件。
    """
    local_file = os.path.join(data_dir, 'post_feed.json')
    if os.path.exists(local_file):
        try:
            with open(local_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                posts = []
                for record in data:
                    item = _normalize_post_record(record, record.get('source', 'promo') if isinstance(record, dict) else 'promo')
                    if item:
                        posts.append(item)
                posts.sort(key=_post_sort_key)
                if limit is not None and len(posts) > limit:
                    posts = posts[-limit:]
                return posts
        except (OSError, json.JSONDecodeError) as exc:
            print(f'[发帖] 读取本地发帖数据失败: {exc}')
    return []


def save_post_feed(posts):
    """保存发帖数据到本地 data/post_feed.json (用户可手动编辑管理)。"""
    file_path = os.path.join(data_dir, 'post_feed.json')
    _save_json_if_changed(file_path, posts, '发帖动态')


def _post_feed_payload(posts, limit=POST_FEED_PAGE_SIZE):
    posts = posts if isinstance(posts, list) else []
    page = posts[-limit:] if limit > 0 else []
    return {
        'post_feed': page,
        'post_feed_total': len(posts),
        'post_feed_has_more': len(posts) > len(page),
    }

def _env_int(name, default):
    """Read a positive integer environment variable with fallback."""
    raw = os.getenv(name, '')
    try:
        value = int(raw)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return default


app = Flask(__name__)
# 会话签名密钥: 优先 WEB_SESSION_SECRET; 未配置则每次启动随机生成(重启后会话失效)。
_SESSION_SECRET_FROM_ENV = bool(str(os.getenv('WEB_SESSION_SECRET', '') or '').strip())
app.config['SECRET_KEY'] = (
    str(os.getenv('WEB_SESSION_SECRET', '') or '').strip() or secrets.token_hex(32)
)
# 会话有效期(小时), 默认 168 = 7 天
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=_env_int('WEB_SESSION_HOURS', 168))
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# 添加 CORS 支持
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
socketio = SocketIO(app, cors_allowed_origins='*', async_mode=SOCKETIO_ASYNC_MODE)


# ---------------------------------------------------------------------------
# POST 接口鉴权: 设置环境变量 WEB_API_TOKEN 后强制校验写接口;
# 未设置时保持旧行为(无鉴权)。只读 GET 接口不受影响。
# 支持三种携带方式: Authorization: Bearer <token> / X-Webhook-Token / ?token=
# ---------------------------------------------------------------------------
def _extract_api_token():
    auth = str(request.headers.get('Authorization') or '').strip()
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    header_token = str(request.headers.get('X-Webhook-Token') or '').strip()
    if header_token:
        return header_token
    return str(request.args.get('token') or '').strip()


def require_api_token(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = str(os.getenv('WEB_API_TOKEN', '') or '').strip()
        if expected and not hmac.compare_digest(_extract_api_token(), expected):
            return jsonify({'status': 'error', 'message': 'unauthorized'}), 401
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# 登录门禁: 配置 WEB_LOGIN_PASSWORD 或 WEB_LOGIN_PASSWORD_SHA256 后启用;
# 未配置密码时保持旧行为(开放访问), 部署时必须配置。
# 凭据与开关在每次请求时读取环境变量, 便于测试与无需改代码的热调整。
# ---------------------------------------------------------------------------
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 60
_login_failures = {}
_login_failures_lock = threading.Lock()


def _valid_sha256(value):
    return len(value) == 64 and all(ch in '0123456789abcdef' for ch in value)


def _get_login_credentials():
    """返回 (username, plain_password, sha256_hex)。SHA256 优先且需为合法十六进制。"""
    username = str(os.getenv('WEB_LOGIN_USERNAME', '') or '').strip() or 'admin'
    plain_password = str(os.getenv('WEB_LOGIN_PASSWORD', '') or '')
    sha256_hex = str(os.getenv('WEB_LOGIN_PASSWORD_SHA256', '') or '').strip().lower()
    if sha256_hex and not _valid_sha256(sha256_hex):
        sha256_hex = ''
    return username, plain_password, sha256_hex


def _invalid_sha256_configured():
    """WEB_LOGIN_PASSWORD_SHA256 已配置但不是 64 位十六进制。"""
    raw = str(os.getenv('WEB_LOGIN_PASSWORD_SHA256', '') or '').strip().lower()
    return bool(raw) and not _valid_sha256(raw)


def _login_enabled():
    _, plain_password, sha256_hex = _get_login_credentials()
    return bool(plain_password or sha256_hex)


def _check_login_credentials(username, password):
    expected_username, plain_password, sha256_hex = _get_login_credentials()
    username_ok = hmac.compare_digest(
        str(username or '').encode('utf-8'), expected_username.encode('utf-8')
    )
    if sha256_hex:
        password_digest = hashlib.sha256(str(password or '').encode('utf-8')).hexdigest()
        password_ok = hmac.compare_digest(password_digest, sha256_hex)
    else:
        password_ok = hmac.compare_digest(
            str(password or '').encode('utf-8'), plain_password.encode('utf-8')
        )
    return username_ok and password_ok


def _safe_next_path(target):
    """只允许站内相对路径作为登录后回跳地址, 防止开放重定向。"""
    path = str(target or '').strip()
    # 控制字符(含 \t \r \n \x00 与 DEL)可被响应头/浏览器规范化成外站目标, 一律拒绝
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in path):
        return ''
    if not path.startswith('/') or path.startswith('//') or path.startswith('/\\'):
        return ''
    if '\\' in path:
        return ''
    return path


def _client_ip():
    return str(request.remote_addr or 'unknown')


def _login_lock_remaining(ip):
    with _login_failures_lock:
        entry = _login_failures.get(ip)
        if not entry:
            return 0.0
        remaining = float(entry.get('locked_until', 0.0)) - time.time()
        if remaining > 0:
            return remaining
        if int(entry.get('count', 0)) >= LOGIN_MAX_FAILURES:
            _login_failures.pop(ip, None)
        return 0.0


def _record_login_failure(ip):
    with _login_failures_lock:
        now = time.time()
        for stale_ip in [
            key for key, value in _login_failures.items()
            if key != ip and float(value.get('seen', now)) < now - 3600
        ]:
            _login_failures.pop(stale_ip, None)
        entry = _login_failures.setdefault(ip, {'count': 0, 'locked_until': 0.0})
        entry['count'] = int(entry.get('count', 0)) + 1
        entry['seen'] = now
        if entry['count'] >= LOGIN_MAX_FAILURES:
            entry['locked_until'] = now + LOGIN_LOCK_SECONDS
            return True
        return False


def _clear_login_failures(ip):
    with _login_failures_lock:
        _login_failures.pop(ip, None)


@app.before_request
def enforce_login_guard():
    """登录门禁守卫: 放行白名单/写接口/已登录, 其余读接口 401、页面 302 到 /login。"""
    if request.method == 'OPTIONS':
        return None

    path = request.path or '/'
    if path in ('/login', '/logout', '/health') or path.startswith('/static/'):
        return None
    # 写接口保持各自 @require_api_token 原有鉴权, 不受登录门禁影响
    if path.startswith('/api/update_'):
        return None
    if not _login_enabled():
        return None
    if session.get('auth') is True:
        return None

    if path.startswith('/api/'):
        return jsonify({'status': 'error', 'message': 'login required'}), 401
    if path == '/':
        return redirect(url_for('login'))
    next_path = path
    if request.query_string:
        next_path = f"{path}?{request.query_string.decode('utf-8', 'ignore')}"
    return redirect(url_for('login', next=next_path))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not _login_enabled():
        return redirect('/')

    next_path = _safe_next_path(request.values.get('next'))
    if request.method == 'GET':
        if session.get('auth') is True:
            return redirect(next_path or '/')
        return render_template('login.html', error='', username='', next=next_path)

    username = str(request.form.get('username') or '')
    password = str(request.form.get('password') or '')
    ip = _client_ip()

    lock_seconds = _login_lock_remaining(ip)
    if lock_seconds > 0:
        return render_template(
            'login.html',
            error=f'尝试次数过多，请 {int(lock_seconds) + 1} 秒后再试',
            username=username,
            next=next_path,
        ), 429

    if _check_login_credentials(username, password):
        _clear_login_failures(ip)
        # 清空登录前会话, 防止 session fixation
        session.clear()
        session.permanent = True
        session['auth'] = True
        session['user'] = username
        return redirect(next_path or '/')

    _record_login_failure(ip)
    return render_template(
        'login.html', error='用户名或密码错误', username=username, next=next_path
    ), 401


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect('/login')


MAX_TRIANGLE_RECORDS = _env_int('WEB_MAX_TRIANGLE_RECORDS', 3000)
MAX_TRIANGLE_ROUNDS = _env_int('WEB_MAX_TRIANGLE_ROUNDS', 1000)
MAX_ARBITRAGE_RECORDS = _env_int('WEB_MAX_ARBITRAGE_RECORDS', 5000)
MAX_LEAD_RECORDS = _env_int('WEB_MAX_LEAD_RECORDS', 5000)
MAX_PROFIT_CURVE_POINTS = _env_int('WEB_MAX_PROFIT_CURVE_POINTS', 4000)
TRIANGLE_OPEN_TYPES = {'开仓', '加仓'}


def _trim_list_inplace(items, limit, keep='head'):
    """Trim list in place to prevent unbounded growth."""
    if not isinstance(items, list) or limit <= 0:
        return
    if len(items) <= limit:
        return
    if keep == 'tail':
        del items[:len(items) - limit]
    else:
        del items[limit:]


def _trim_profit_curve_points(total_profit_data):
    if not isinstance(total_profit_data, dict):
        return
    curve_data = total_profit_data.get('profit_curve_data')
    if not isinstance(curve_data, dict):
        return
    points = curve_data.get('data_points')
    _trim_list_inplace(points, MAX_PROFIT_CURVE_POINTS, keep='tail')


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_profit_curve_date(value):
    parts = str(value or '').split('-')
    if len(parts) < 2:
        return None

    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2]) if len(parts) > 2 else 1
    except (TypeError, ValueError):
        return None

    if month < 1 or month > 12:
        return None
    if day < 1 or day > 31:
        day = 1
    return year, month, day


def _build_total_profit_summary(total_profit_data):
    summary = {
        'total_net_profit': 0.0,
        'total_margin': 0.0,
        'total_return_rate': 0.0,
        'yearly_return_rate': 0.0,
        'yearly_return_profit': 0.0,
        'total_principal': 0.0
    }

    if not isinstance(total_profit_data, dict):
        return summary

    curve_data = total_profit_data.get('profit_curve_data')
    if not isinstance(curve_data, dict):
        return summary

    raw_points = curve_data.get('data_points')
    if not isinstance(raw_points, list):
        return summary

    normalized_points = []
    for index, point in enumerate(raw_points):
        if not isinstance(point, dict):
            continue

        date_parts = _parse_profit_curve_date(point.get('date'))
        normalized_points.append({
            'year': date_parts[0] if date_parts else None,
            'sort_key': date_parts if date_parts else (9999, 12, 31),
            'index': index,
            'principal': _to_float(point.get('principal'), 0.0),
            'total_funds': _to_float(point.get('total_funds'), 0.0)
        })

    if not normalized_points:
        return summary

    normalized_points.sort(key=lambda point: (point['sort_key'], point['index']))

    last_point = normalized_points[-1]
    total_principal = last_point['principal']
    total_margin = last_point['total_funds']
    total_net_profit = total_margin - total_principal
    total_return_rate = (total_net_profit / total_principal * 100) if total_principal > 0 else 0.0

    current_year = datetime.now().year
    current_year_points = []
    baseline_point = None

    for point in normalized_points:
        point_year = point['year']
        if point_year == current_year:
            current_year_points.append(point)
        elif point_year is not None and point_year < current_year:
            baseline_point = point

    yearly_return_profit = 0.0
    yearly_return_rate = 0.0
    if current_year_points:
        yearly_start_point = baseline_point or current_year_points[0]
        yearly_end_point = current_year_points[-1]

        yearly_start_profit = yearly_start_point['total_funds'] - yearly_start_point['principal']
        yearly_end_profit = yearly_end_point['total_funds'] - yearly_end_point['principal']
        yearly_return_profit = yearly_end_profit - yearly_start_profit

        yearly_base_funds = yearly_start_point['total_funds']
        yearly_return_rate = (yearly_return_profit / yearly_base_funds * 100) if yearly_base_funds > 0 else 0.0

    summary.update({
        'total_net_profit': round(total_net_profit, 4),
        'total_margin': round(total_margin, 4),
        'total_return_rate': round(total_return_rate, 6),
        'yearly_return_rate': round(yearly_return_rate, 6),
        'yearly_return_profit': round(yearly_return_profit, 4),
        'total_principal': round(total_principal, 4)
    })
    return summary


TRIANGLE_CLOSE_TYPES = {'平仓', '止盈', '止损'}


def _sum_triangle_round_profit(round_records):
    if not isinstance(round_records, list):
        return 0.0

    total_profit = 0.0
    for record in round_records:
        if not isinstance(record, dict):
            continue
        total_profit += _to_float(record.get('pnl', record.get('profit', 0.0)), 0.0)
    return total_profit


def _extract_triangle_profit_delta(trade_data):
    if not isinstance(trade_data, dict):
        return None

    for field_name in ('realized_pnl', 'net_profit'):
        field_value = trade_data.get(field_name)
        if field_value is not None:
            return _to_float(field_value, 0.0)

    gross_pnl = trade_data.get('gross_pnl')
    if gross_pnl is not None:
        gross_pnl_value = _to_float(gross_pnl, 0.0)
        open_fee = _to_float(trade_data.get('open_fee', 0.0), 0.0)
        close_fee = _to_float(trade_data.get('close_fee', 0.0), 0.0)
        return round(gross_pnl_value - open_fee - close_fee, 4)

    trade_type = str(trade_data.get('trade_type') or '').strip()
    if trade_type not in TRIANGLE_CLOSE_TYPES and not any(keyword in trade_type for keyword in TRIANGLE_CLOSE_TYPES):
        return None

    entry_price = _to_float(trade_data.get('entry_price'), None)
    exit_price = _to_float(trade_data.get('exit_price'), None)
    quantity = _to_float(trade_data.get('quantity'), None)
    if entry_price is None or exit_price is None or quantity is None or quantity <= 0:
        return None

    side = str(trade_data.get('side') or '').strip().upper()
    if side == 'SELL':
        gross_pnl_value = (exit_price - entry_price) * quantity
    elif side == 'BUY':
        gross_pnl_value = (entry_price - exit_price) * quantity
    else:
        return None

    open_fee = _to_float(trade_data.get('open_fee', 0.0), 0.0)
    close_fee = _to_float(trade_data.get('close_fee', 0.0), 0.0)
    return round(gross_pnl_value - open_fee - close_fee, 4)


def _trade_type_matches(trade_type, keywords):
    normalized = str(trade_type or '').strip()
    if not normalized:
        return False
    if normalized in keywords:
        return True
    return any(keyword in normalized for keyword in keywords)


def _build_lead_record_key(trade_data):
    account_id = str(trade_data.get('account_id') or 'unknown').strip()
    order_id = str(trade_data.get('order_id') or '').strip()
    if order_id:
        return f'{account_id}:{order_id}'

    signal_id = str(trade_data.get('signal_id') or '').strip()
    if signal_id:
        trade_type = str(trade_data.get('trade_type') or '').strip()
        return f'{account_id}:signal:{signal_id}:{trade_type}'

    return ':'.join([
        account_id,
        str(trade_data.get('symbol') or '').strip(),
        str(trade_data.get('side') or '').strip(),
        str(trade_data.get('trade_type') or '').strip(),
        str(trade_data.get('timestamp') or '').strip(),
        f"{_to_float(trade_data.get('quantity'), 0.0):.8f}",
        f"{_to_float(trade_data.get('price'), 0.0):.8f}",
    ])


def _normalize_lead_trade_record(trade_data):
    timestamp = str(
        trade_data.get('timestamp')
        or trade_data.get('exit_timestamp')
        or trade_data.get('entry_timestamp')
        or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ).strip()
    trade_type = str(trade_data.get('trade_type') or '未知').strip() or '未知'
    order_pnl = _extract_triangle_profit_delta(trade_data)
    realized_pnl = trade_data.get('realized_pnl')

    normalized = {
        'order_key': '',
        'order_id': str(trade_data.get('order_id') or '').strip(),
        'account_id': str(trade_data.get('account_id') or '').strip(),
        'account_label': str(trade_data.get('account_label') or trade_data.get('account_id') or '默认账户').strip(),
        'symbol': str(trade_data.get('symbol') or '').strip(),
        'side': str(trade_data.get('side') or '').strip().upper(),
        'quantity': round(_to_float(trade_data.get('quantity'), 0.0), 8),
        'price': _to_float(trade_data.get('price'), 0.0),
        'trade_type': trade_type,
        'reason': str(trade_data.get('reason') or trade_data.get('alert_message') or '').strip(),
        'timestamp': timestamp,
        'gross_pnl': trade_data.get('gross_pnl'),
        'realized_pnl': round(_to_float(realized_pnl, order_pnl), 4) if (realized_pnl is not None or order_pnl is not None) else None,
        'order_pnl': round(_to_float(order_pnl, 0.0), 4) if order_pnl is not None else None,
        'open_fee': round(_to_float(trade_data.get('open_fee'), 0.0), 4) if trade_data.get('open_fee') is not None else 0.0,
        'close_fee': round(_to_float(trade_data.get('close_fee'), 0.0), 4) if trade_data.get('close_fee') is not None else 0.0,
        'entry_price': _to_float(trade_data.get('entry_price'), None),
        'exit_price': _to_float(trade_data.get('exit_price'), None),
    }
    normalized['order_key'] = _build_lead_record_key(normalized)
    return normalized


def _build_lead_summary(trade_records, initial_funds=0.0, archived_realized_pnl=0.0):
    total_realized_pnl = _to_float(archived_realized_pnl, 0.0)
    close_trade_count = 0
    win_trades = 0
    lose_trades = 0

    if isinstance(trade_records, list):
        for record in trade_records:
            if not isinstance(record, dict):
                continue
            profit_value = record.get('order_pnl')
            if profit_value is None:
                profit_value = _extract_triangle_profit_delta(record)
            if profit_value is None and not _trade_type_matches(record.get('trade_type'), TRIANGLE_CLOSE_TYPES):
                continue

            profit = _to_float(profit_value, 0.0)
            total_realized_pnl += profit
            close_trade_count += 1
            if profit > 0:
                win_trades += 1
            elif profit < 0:
                lose_trades += 1

    initial_funds_value = _to_float(initial_funds, 0.0)
    current_funds = initial_funds_value + total_realized_pnl
    total_return_rate = (total_realized_pnl / initial_funds_value * 100) if initial_funds_value > 0 else 0.0

    return {
        'initial_funds': round(initial_funds_value, 4),
        'total_realized_pnl': round(total_realized_pnl, 4),
        'current_funds': round(current_funds, 4),
        'total_return_rate': round(total_return_rate, 6),
        'close_trade_count': close_trade_count,
        'win_trades': win_trades,
        'lose_trades': lose_trades,
        'archived_realized_pnl': round(_to_float(archived_realized_pnl, 0.0), 4),
        'retained_record_count': len(trade_records) if isinstance(trade_records, list) else 0,
    }


def _normalize_triangle_trade_record(trade_data):
    normalized = _normalize_lead_trade_record(trade_data)
    strategy_type = str(trade_data.get('strategy_type') or '').strip().lower()
    if strategy_type in {'', 'legacy_triangle', 'triangle', 'multistrategy_4h', 'multi'}:
        strategy_type = 'triangle'

    normalized['strategy_type'] = strategy_type
    normalized['strategy_label'] = str(trade_data.get('strategy_label') or '三角策略').strip() or '三角策略'
    normalized['web_strategy_label'] = str(trade_data.get('web_strategy_label') or '三角策略').strip() or '三角策略'
    return normalized


def _parse_triangle_trade_timestamp(value):
    raw_value = str(value or '').strip()
    if not raw_value:
        return None

    for format_pattern in ('%Y-%m-%d-%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw_value, format_pattern)
        except ValueError:
            continue
    return None


def _triangle_position_bucket_key(trade_data):
    account_id = str(trade_data.get('account_id') or trade_data.get('account_label') or 'unknown').strip()
    symbol = str(trade_data.get('symbol') or '').strip()
    return f'{account_id}:{symbol}'


def _triangle_get_position_bucket(position_buckets, trade_data, side):
    bucket_key = _triangle_position_bucket_key(trade_data)
    bucket = position_buckets.setdefault(bucket_key, {
        'BUY': {'quantity': 0.0, 'avg_price': 0.0},
        'SELL': {'quantity': 0.0, 'avg_price': 0.0},
    })
    return bucket[side]


def _triangle_apply_open_trade(position_buckets, trade_data):
    side = str(trade_data.get('side') or '').strip().upper()
    if side not in {'BUY', 'SELL'}:
        return None

    quantity = _to_float(trade_data.get('quantity'), 0.0)
    if quantity <= 0:
        return None

    price = _to_float(trade_data.get('price'), 0.0)
    bucket = _triangle_get_position_bucket(position_buckets, trade_data, side)
    current_quantity = _to_float(bucket.get('quantity', 0.0), 0.0)
    new_quantity = current_quantity + quantity
    if new_quantity <= 0:
        bucket['quantity'] = 0.0
        bucket['avg_price'] = 0.0
        return None

    bucket['avg_price'] = round((bucket.get('avg_price', 0.0) * current_quantity + price * quantity) / new_quantity, 8)
    bucket['quantity'] = round(new_quantity, 8)
    return None


def _triangle_apply_close_trade(position_buckets, trade_data, update_record=True):
    side = str(trade_data.get('side') or '').strip().upper()
    if side not in {'BUY', 'SELL'}:
        return None

    quantity = _to_float(trade_data.get('quantity'), 0.0)
    if quantity <= 0:
        return None

    open_side = 'SELL' if side == 'BUY' else 'BUY'
    bucket = _triangle_get_position_bucket(position_buckets, trade_data, open_side)
    available_quantity = _to_float(bucket.get('quantity', 0.0), 0.0)
    if available_quantity <= 0:
        return None

    matched_quantity = min(quantity, available_quantity)
    entry_price = _to_float(bucket.get('avg_price', 0.0), 0.0)
    exit_price = _to_float(trade_data.get('price'), 0.0)
    if open_side == 'SELL':
        gross_pnl = (entry_price - exit_price) * matched_quantity
    else:
        gross_pnl = (exit_price - entry_price) * matched_quantity

    open_fee = _to_float(trade_data.get('open_fee', 0.0), 0.0)
    close_fee = _to_float(trade_data.get('close_fee', 0.0), 0.0)
    order_pnl = round(gross_pnl - open_fee - close_fee, 4)

    if update_record:
        trade_data['entry_price'] = round(entry_price, 4)
        trade_data['exit_price'] = round(exit_price, 4)
        trade_data['open_price'] = round(entry_price, 4)
        trade_data['close_price'] = round(exit_price, 4)
        trade_data['gross_pnl'] = round(gross_pnl, 4)
        trade_data['realized_pnl'] = order_pnl
        trade_data['order_pnl'] = order_pnl
        trade_data['open_fee'] = round(open_fee, 4) if open_fee else 0.0
        trade_data['close_fee'] = round(close_fee, 4) if close_fee else 0.0

    remaining_quantity = round(available_quantity - matched_quantity, 8)
    if remaining_quantity <= 0:
        bucket['quantity'] = 0.0
        bucket['avg_price'] = 0.0
    else:
        bucket['quantity'] = remaining_quantity

    return order_pnl


def _rebuild_triangle_open_positions(trade_records):
    position_buckets = {}
    if not isinstance(trade_records, list):
        return position_buckets

    ordered_records = sorted(
        enumerate(trade_records),
        key=lambda item: (
            _parse_triangle_trade_timestamp(
                item[1].get('timestamp')
                or item[1].get('exit_timestamp')
                or item[1].get('entry_timestamp')
            ) or datetime.min,
            -item[0],
        ),
    )

    for _, record in ordered_records:
        if not isinstance(record, dict):
            continue
        trade_type = str(record.get('trade_type') or '').strip()
        if trade_type in TRIANGLE_OPEN_TYPES:
            _triangle_apply_open_trade(position_buckets, record)
        elif _trade_type_matches(trade_type, TRIANGLE_CLOSE_TYPES):
            _triangle_apply_close_trade(position_buckets, record, update_record=False)

    return position_buckets


def _replay_trade_records_with_pnl(trade_records):
    position_buckets = {}
    if not isinstance(trade_records, list):
        return position_buckets

    ordered_records = sorted(
        enumerate(trade_records),
        key=lambda item: (
            _parse_triangle_trade_timestamp(
                item[1].get('timestamp')
                or item[1].get('exit_timestamp')
                or item[1].get('entry_timestamp')
            ) or datetime.min,
            -item[0],
        ),
    )

    for _, record in ordered_records:
        if not isinstance(record, dict):
            continue
        trade_type = str(record.get('trade_type') or '').strip()
        if trade_type in TRIANGLE_OPEN_TYPES:
            _triangle_apply_open_trade(position_buckets, record)
        elif _trade_type_matches(trade_type, TRIANGLE_CLOSE_TYPES):
            _triangle_apply_close_trade(position_buckets, record, update_record=True)

    return position_buckets


def _normalize_triangle_summary(summary, round_records=None):
    normalized = dict(summary) if isinstance(summary, dict) else {}
    round_profit = _sum_triangle_round_profit(round_records)
    initial_funds = _to_float(normalized.get('initial_funds', 0.0), 0.0)

    total_realized_pnl = normalized.get('total_realized_pnl')
    if total_realized_pnl is None:
        total_realized_pnl = normalized.get('total_profit', normalized.get('total_profit_all', 0.0))
    total_realized_pnl = _to_float(total_realized_pnl, 0.0)

    normalized['initial_funds'] = round(initial_funds, 4)
    normalized['total_realized_pnl'] = round(total_realized_pnl, 4)
    normalized['current_funds'] = round(initial_funds + total_realized_pnl, 4)
    normalized['total_return_rate'] = round((total_realized_pnl / initial_funds * 100) if initial_funds > 0 else 0.0, 6)
    normalized['total_profit'] = round(_to_float(normalized.get('total_profit', total_realized_pnl), total_realized_pnl), 4)
    normalized['total_profit_all'] = round(_to_float(normalized.get('total_profit_all', total_realized_pnl + round_profit), total_realized_pnl + round_profit), 4)
    normalized['close_trade_count'] = int(_to_float(normalized.get('close_trade_count', 0), 0.0))
    normalized['win_trades'] = int(_to_float(normalized.get('win_trades', 0), 0.0))
    normalized['lose_trades'] = int(_to_float(normalized.get('lose_trades', 0), 0.0))
    normalized['archived_realized_pnl'] = round(_to_float(normalized.get('archived_realized_pnl', 0.0), 0.0), 4)
    normalized['retained_record_count'] = int(_to_float(normalized.get('retained_record_count', 0), 0.0))
    return normalized


def _build_triangle_summary(trade_records, initial_funds=0.0, archived_realized_pnl=0.0, round_records=None):
    summary = _build_lead_summary(
        trade_records,
        initial_funds=initial_funds,
        archived_realized_pnl=archived_realized_pnl,
    )
    total_realized_pnl = _to_float(summary.get('total_realized_pnl', 0.0), 0.0)
    round_profit = _sum_triangle_round_profit(round_records)

    summary['total_profit'] = round(total_realized_pnl, 4)
    summary['total_profit_all'] = round(total_realized_pnl + round_profit, 4)
    return summary


def load_lead_data():
    file_path = os.path.join(data_dir, 'lead_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                raw_records = data.get('trade_records', []) if isinstance(data, dict) else []
                summary = data.get('summary', {}) if isinstance(data, dict) else {}
                normalized_records = []
                seen_keys = set()
                for raw_record in raw_records:
                    if not isinstance(raw_record, dict):
                        continue
                    record = _normalize_lead_trade_record(raw_record)
                    if record['order_key'] in seen_keys:
                        continue
                    seen_keys.add(record['order_key'])
                    normalized_records.append(record)
                _replay_trade_records_with_pnl(normalized_records)
                archived_realized_pnl = _to_float(summary.get('archived_realized_pnl', 0.0), 0.0)
                initial_funds = _to_float(summary.get('initial_funds', 0.0), 0.0)
                return {
                    'summary': _build_lead_summary(normalized_records, initial_funds=initial_funds, archived_realized_pnl=archived_realized_pnl),
                    'trade_records': normalized_records,
                }
        except Exception as e:
            print(f"读取带单策略数据失败: {e}")
    return {
        'summary': _build_lead_summary([], initial_funds=0.0, archived_realized_pnl=0.0),
        'trade_records': [],
    }


def _save_json_if_changed(file_path, data, label):
    try:
        new_content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        old_content = ''
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                old_content = f.read()
        if new_content == old_content:
            return
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"{label}已保存")
    except Exception as e:
        print(f"保存{label}失败: {e}")


def save_lead_data(data):
    _save_json_if_changed(os.path.join(data_dir, 'lead_trades.json'), data, '带单策略数据')


# 从本地文件读取总盈亏数据
def load_total_profit_data():
    file_path = os.path.join(data_dir, 'total_profit.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['profit_summary'] = _build_total_profit_summary(data)
                return data
        except Exception as e:
            print(f"读取总盈亏数据失败: {e}")
    return {
        'profit_summary': {
            'total_net_profit': 0.0,
            'total_margin': 0.0,
            'total_return_rate': 0.0,
            'yearly_return_rate': 0.0,
            'yearly_return_profit': 0.0,
            'total_principal': 0.0
        },
        'trade_records': [],
        'symbol_profit_tracker': {}
    }

# 套利策略数据不再从本地文件加载，完全依赖在线数据

# 从本地文件读取三角策略数据
def load_triangle_data():
    triangle_file_path = os.path.join(data_dir, 'triangle_trades.json')
    legacy_triangle_file_path = os.path.join(data_dir, 'triangle_trades.json')
    source_file_path = triangle_file_path if os.path.exists(triangle_file_path) else legacy_triangle_file_path

    if os.path.exists(source_file_path):
        try:
            with open(source_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            raw_records = data.get('trade_records', []) if isinstance(data, dict) else []
            round_records = data.get('round_records', []) if isinstance(data, dict) else []
            summary = data.get('summary', {}) if isinstance(data, dict) else {}

            normalized_records = []
            seen_keys = set()
            for raw_record in raw_records:
                if not isinstance(raw_record, dict):
                    continue
                record = _normalize_triangle_trade_record(raw_record)
                if record['order_key'] in seen_keys:
                    continue
                seen_keys.add(record['order_key'])
                normalized_records.append(record)

            computed_summary = _normalize_triangle_summary(summary, round_records)

            return {
                'trade_records': normalized_records,
                'round_records': round_records,
                'summary': computed_summary,
            }
        except Exception as e:
            print(f"读取三角策略数据失败: {e}")

    return {
        'trade_records': [],
        'round_records': [],
        'summary': _build_triangle_summary([], initial_funds=0.0, archived_realized_pnl=0.0, round_records=[]),
    }


def save_triangle_data(data):
    _save_json_if_changed(os.path.join(data_dir, 'triangle_trades.json'), data, '三角策略数据')

# 从本地文件读取套利策略数据
def load_arbitrage_data():
    file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取套利策略数据失败: {e}")
    return {
        'profit_summary': {
            'total_net_profit': 0.0,
            'total_margin': 0.0,
            'total_return_rate': 0.0,
            'yearly_return_rate': 0.0,
            'yearly_return_profit': 0.0,
            'initial_funds': 0.0
        },
        'trade_records': [],
    }

# 将套利策略数据保存到本地文件
def save_arbitrage_data(data):
    _save_json_if_changed(os.path.join(data_dir, 'arbitrage_trades.json'), data, '套利策略数据')

def load_top_data():
    file_path = os.path.join(data_dir, 'top_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取摸顶策略数据失败: {e}")
    return {'position_status': '摸顶做空', 'position_quantity': 0.0, 'position_avg_price': 0.0, 'position_symbol': 'BTCUSDT', 'trade_records': []}


def save_top_data(data):
    _save_json_if_changed(os.path.join(data_dir, 'top_trades.json'), data, '摸顶策略数据')


def load_bottom_data():
    file_path = os.path.join(data_dir, 'bottom_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取抄底策略数据失败: {e}")
    return {'position_status': '抄底做多', 'position_quantity': 0.0, 'position_avg_price': 0.0, 'position_symbol': 'BTCUSDT', 'trade_records': []}


def save_bottom_data(data):
    _save_json_if_changed(os.path.join(data_dir, 'bottom_trades.json'), data, '抄底策略数据')

# 定期检查文件更新的函数
def check_file_updates():
    import gc
    total_profit_file_path = os.path.join(data_dir, 'total_profit.json')
    top_file_path = os.path.join(data_dir, 'top_trades.json')
    bottom_file_path = os.path.join(data_dir, 'bottom_trades.json')
    # GC 节流：每 10 分钟主动回收一次
    _GC_INTERVAL = 600.0
    _last_gc = time.monotonic()
    triangle_file_path = os.path.join(data_dir, 'triangle_trades.json')
    legacy_triangle_file_path = os.path.join(data_dir, 'triangle_trades.json')
    lead_file_path = os.path.join(data_dir, 'lead_trades.json')
    arbitrage_file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    last_modified_alpha_engine = 0
    last_modified_total_profit = 0
    last_modified_top = 0
    last_modified_bottom = 0
    last_modified_triangle = 0
    last_modified_triangle_legacy = 0
    last_modified_lead = 0
    last_modified_arbitrage = 0
    last_modified_promo_posts = 0
    last_modified_promo_alpha = 0
    
    while True:
        try:
            # 只读 AlphaEngine 状态，并在其状态变更后推送新的中文阶段和alpha值
            if os.path.exists(alpha_engine_state_file):
                current_modified = os.path.getmtime(alpha_engine_state_file)
                if current_modified > last_modified_alpha_engine:
                    new_regime = load_alpha_engine_regime()
                    new_alpha = load_alpha_engine_alpha()
                    new_ma = load_alpha_engine_ma()
                    if new_regime:
                        last_modified_alpha_engine = current_modified
                        new_cycle = alpha_engine_regime_label(new_regime)
                        if alpha_engine_update_changed(data_storage.market_data,
                                                       new_regime, new_alpha, new_ma):
                            data_storage.update_market_data({
                                'cycle': new_cycle,
                                'alpha_engine_regime': new_regime,
                                'alpha_engine_alpha': new_alpha,
                                'alpha_engine_ma': new_ma,
                            })
                            socketio.emit('market_update', {
                                'market_data': data_storage.market_data,
                                'strategy_status': data_storage.strategy_status,
                            })
                            print(f'AlphaEngine 已更新: {new_regime} -> {new_cycle}, alpha={new_alpha:+.4f}')

            # 检查总盈亏数据文件
            if os.path.exists(total_profit_file_path):
                current_modified = os.path.getmtime(total_profit_file_path)
                if current_modified > last_modified_total_profit:
                    last_modified_total_profit = current_modified
                    new_data = load_total_profit_data()
                    old_snapshot = json.dumps(data_storage.total_profit_data, ensure_ascii=False, sort_keys=True)
                    data_storage.total_profit_data = new_data
                    data_storage.update_global_data()
                    new_snapshot = json.dumps(data_storage.total_profit_data, ensure_ascii=False, sort_keys=True)
                    if old_snapshot != new_snapshot:
                        print("总盈利数据已更新")
            
            # 检查摸顶策略文件
            if os.path.exists(top_file_path):
                current_modified = os.path.getmtime(top_file_path)
                if current_modified > last_modified_top:
                    last_modified_top = current_modified
                    new_data = load_top_data()
                    old_snapshot = json.dumps(data_storage.top_data, ensure_ascii=False, sort_keys=True)
                    data_storage.top_data.update(new_data)
                    data_storage.strategy_status['top'] = data_storage.top_data.get('status', '持仓')
                    data_storage.update_global_data()
                    new_snapshot = json.dumps(data_storage.top_data, ensure_ascii=False, sort_keys=True)
                    if old_snapshot != new_snapshot:
                        print("摸顶策略数据已更新")

            # 检查抄底策略文件
            if os.path.exists(bottom_file_path):
                current_modified = os.path.getmtime(bottom_file_path)
                if current_modified > last_modified_bottom:
                    last_modified_bottom = current_modified
                    new_data = load_bottom_data()
                    old_snapshot = json.dumps(data_storage.bottom_data, ensure_ascii=False, sort_keys=True)
                    data_storage.bottom_data.update(new_data)
                    data_storage.strategy_status['bottom'] = data_storage.bottom_data.get('status', '清仓')
                    data_storage.update_global_data()
                    new_snapshot = json.dumps(data_storage.bottom_data, ensure_ascii=False, sort_keys=True)
                    if old_snapshot != new_snapshot:
                        print("抄底策略数据已更新")

            
            # 检查三角策略数据文件
            triangle_source_file_path = triangle_file_path if os.path.exists(triangle_file_path) else legacy_triangle_file_path
            if os.path.exists(triangle_source_file_path):
                current_modified = os.path.getmtime(triangle_source_file_path)
                last_modified_ref = last_modified_triangle if triangle_source_file_path == triangle_file_path else last_modified_triangle_legacy

                if current_modified > last_modified_ref:
                    if triangle_source_file_path == triangle_file_path:
                        last_modified_triangle = current_modified
                    else:
                        last_modified_triangle_legacy = current_modified

                    # 重新加载数据
                    new_data = load_triangle_data()
                    old_records = json.dumps(data_storage.triangle_data, ensure_ascii=False, sort_keys=True)
                    old_summary = json.dumps(data_storage.triangle_summary, ensure_ascii=False, sort_keys=True)
                    data_storage.triangle_data = new_data.get('trade_records', [])
                    data_storage.triangle_rounds = new_data.get('round_records', [])
                    data_storage.triangle_summary = new_data.get('summary', {
                        'initial_funds': 0.0,
                        'total_realized_pnl': 0.0,
                        'current_funds': 0.0,
                        'total_return_rate': 0.0,
                        'close_trade_count': 0,
                        'win_trades': 0,
                        'lose_trades': 0,
                        'archived_realized_pnl': 0.0,
                        'retained_record_count': 0,
                    })
                    data_storage._triangle_open_positions = _rebuild_triangle_open_positions(data_storage.triangle_data)
                    data_storage.strategy_status['triangle'] = '运行'

                    data_storage.update_global_data()
                    new_records = json.dumps(data_storage.triangle_data, ensure_ascii=False, sort_keys=True)
                    new_summary = json.dumps(data_storage.triangle_summary, ensure_ascii=False, sort_keys=True)
                    if old_records != new_records or old_summary != new_summary:
                        print("三角策略数据已更新")

            # 检查带单策略数据文件
            if os.path.exists(lead_file_path):
                current_modified = os.path.getmtime(lead_file_path)
                if current_modified > last_modified_lead:
                    last_modified_lead = current_modified
                    new_data = load_lead_data()
                    old_snapshot = json.dumps(data_storage.lead_data, ensure_ascii=False, sort_keys=True)
                    data_storage.lead_data = new_data
                    data_storage.strategy_status['lead'] = '运行'
                    data_storage.update_global_data()
                    new_snapshot = json.dumps(data_storage.lead_data, ensure_ascii=False, sort_keys=True)
                    if old_snapshot != new_snapshot:
                        print("带单策略数据已更新")
            
            # 检查套利策略数据文件
            if os.path.exists(arbitrage_file_path):
                current_modified = os.path.getmtime(arbitrage_file_path)
                if current_modified > last_modified_arbitrage:
                    last_modified_arbitrage = current_modified
                    new_data = load_arbitrage_data()
                    old_snapshot = json.dumps(data_storage.arbitrage_data, ensure_ascii=False, sort_keys=True)
                    data_storage.arbitrage_data = new_data
                    data_storage.update_global_data()
                    new_snapshot = json.dumps(data_storage.arbitrage_data, ensure_ascii=False, sort_keys=True)
                    if old_snapshot != new_snapshot:
                        print("套利策略数据已更新")

            # 检查本地发帖数据文件 (用户手动编辑 post_feed.json 时刷新)
            try:
                post_feed_file = os.path.join(data_dir, 'post_feed.json')
                if os.path.exists(post_feed_file):
                    current_mtime = os.path.getmtime(post_feed_file)
                    if current_mtime > last_modified_promo_posts:
                        last_modified_promo_posts = current_mtime
                        if data_storage.update_post_feed():
                            socketio.emit('post_feed_update', {
                                **_post_feed_payload(data_storage.post_feed),
                            })
                            print('发帖动态已更新 (本地文件)')
            except Exception as exc:
                print(f'检查发帖数据失败: {exc}')

            # 周期 GC：释放文件读取 / json 解析残留的临时 dict
            _now = time.monotonic()
            if _now - _last_gc >= _GC_INTERVAL:
                _last_gc = _now
                gc.collect()

            # 每 5 秒检查一次
            time.sleep(5)
        except Exception as e:
            print(f"检查文件更新失败: {e}")
            time.sleep(5)

# 全局数据存储
# 加载摸顶策略数据
top_file_data = load_top_data()
# 加载抄底策略数据
bottom_file_data = load_bottom_data()
# 加载总盈亏数据
total_profit_data = load_total_profit_data()
# 加载套利策略数据
arbitrage_data = load_arbitrage_data()
# 加载带单策略数据
lead_data = load_lead_data()
# 加载三角策略数据
triangle_data = load_triangle_data()
triangle_trade_records = triangle_data.get('trade_records', [])
triangle_round_records = triangle_data.get('round_records', [])
triangle_summary = triangle_data.get('summary', {
    'win_trades': 0,
    'lose_trades': 0,
    'total_profit': 0.0,
    'total_profit_all': 0.0,
    'initial_funds': 1000.0
})

alpha_engine_regime = load_alpha_engine_regime()
alpha_engine_cycle = alpha_engine_regime_label(alpha_engine_regime)
alpha_engine_alpha = load_alpha_engine_alpha()
alpha_engine_ma = load_alpha_engine_ma()

# 定期获取 BTC 价格（DataFeed 优先 → Binance API → CoinGecko 回退）
def fetch_btc_price():
    time.sleep(10)

    feeder = None
    last_df_status = ''
    try:
        _df_dir = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'DataFeed'
        ))
        if _df_dir not in sys.path:
            sys.path.insert(0, _df_dir)
        from datafeed.price_feeder import get_price_feeder

        feeder = get_price_feeder()
        feeder.watch_coins(['BTC'])
        feeder.start()
        time.sleep(3)
        st = feeder.get_status_log()
        print(f'[Web] {st}')
        last_df_status = st
    except Exception as e:
        print(f'[Web] DataFeed 不可用 ({e})，使用直接 API 模式')

    last_source = 'none'
    last_price = 0.0
    last_emit_time = 0.0
    last_emit_log_time = 0.0
    EMIT_INTERVAL = 5.0
    retry_coingecko_at = 0.0
    datafeed_reported = False

    while True:
        btc_price = 0.0
        source = 'none'
        try:
            # 1. 优先 DataFeed 缓存
            if feeder is not None:
                price, source = feeder.get_price('BTC')
                if price is not None and price > 0:
                    btc_price = float(price)
                    if not datafeed_reported:
                        print(f'[Web] DataFeed 首帧到达 BTC={btc_price}')
                        datafeed_reported = True

            # 2. DataFeed 无数据 → 回退到直接 Binance API
            if btc_price <= 0:
                btc_price = _fetch_binance_price()
                if btc_price > 0:
                    source = 'api'

            # 3. Binance 也失败 → 回退 CoinGecko
            if btc_price <= 0:
                now = time.time()
                if now >= retry_coingecko_at:
                    btc_price = _fetch_coingecko_price()
                    if btc_price > 0:
                        source = 'coingecko'
                    retry_coingecko_at = now + 120
                else:
                    time.sleep(1)
                    continue

            if btc_price > 0:
                source_changed = source != last_source
                price_changed = abs(btc_price - last_price) > 0.01
                last_source = source
                last_price = btc_price

                data_storage.update_market_data({'btc_price': btc_price})
                now = time.time()
                should_emit = (source_changed or price_changed
                               or now - last_emit_time >= EMIT_INTERVAL)
                if source_changed:
                    print(f'[Web] BTC 价格源切换: {last_source} -> {source} price={btc_price}')
                elif abs(btc_price - last_price) > 1000:
                    print(f'[Web] BTC 价格显著变动 source={source} price={btc_price}')
                    last_price = btc_price
                elif now - last_emit_time >= 30.0:
                    print(f'[Web] BTC 当前 source={source} price={btc_price}')
                    last_emit_log_time = now
                if should_emit:
                    socketio.emit('market_update', {
                        'market_data': data_storage.market_data,
                        'strategy_status': data_storage.strategy_status,
                    })
                    last_emit_time = now

            if feeder is not None:
                try:
                    st = feeder.get_status_log()
                    if st != last_df_status:
                        print(f'[Web] {st}')
                        last_df_status = st
                except Exception:
                    pass

        except Exception as e:
            print(f'[Web] 获取 BTC 价格失败: {e}')

        time.sleep(1)


def _fetch_binance_price() -> float:
    try:
        response = requests.get(
            'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=3
        )
        if response.status_code == 200:
            data = response.json()
            return float(data.get('price', 0))
    except Exception:
        pass
    return 0.0


def _fetch_coingecko_price() -> float:
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
            timeout=3,
        )
        if response.status_code == 200:
            data = response.json()
            if 'bitcoin' in data and 'usd' in data['bitcoin']:
                return float(data['bitcoin']['usd'])
    except Exception:
        pass
    return 0.0

global_data = {
    'triangle': triangle_trade_records,
    'triangle_rounds': triangle_round_records,
    'triangle_summary': triangle_summary,
    'arbitrage_data': arbitrage_data,
    'lead_data': lead_data,
    'total_profit_data': total_profit_data,
    'top_data': top_file_data,
    'bottom_data': bottom_file_data,
    'strategy_status': {
        'lead': '运行',
        'triangle': '运行',
        'arbitrage': '运行',
        'top': top_file_data.get('status', '持仓'),
        'bottom': bottom_file_data.get('status', '清仓'),
    },
'market_data': {
        'cycle': alpha_engine_cycle,
        'alpha_engine_regime': alpha_engine_regime,
        'alpha_engine_alpha': alpha_engine_alpha,
        'alpha_engine_ma': alpha_engine_ma,
        'btc_price': 58000.0
    },
    'post_feed': load_promo_posts()
}

    # 数据存储类
class DataStorage:
    def __init__(self):
        self.triangle_data = global_data['triangle']
        self.triangle_rounds = global_data.get('triangle_rounds', [])
        self.triangle_summary = global_data['triangle_summary']
        self.arbitrage_data = global_data['arbitrage_data']
        self.lead_data = global_data['lead_data']
        self.total_profit_data = global_data['total_profit_data']
        self.top_data = global_data['top_data']
        self.bottom_data = global_data['bottom_data']
        self.strategy_status = global_data['strategy_status']
        self.market_data = global_data['market_data']
        self.post_feed = global_data.get('post_feed', [])
        self.arbitrage_start_time = None  # 套利策略启动时间
        self._triangle_signal_ids = set()
        self._apply_memory_limits()
        self._refresh_triangle_signal_ids()
        self._triangle_open_positions = _rebuild_triangle_open_positions(self.triangle_data)

    def _refresh_triangle_signal_ids(self):
        self._triangle_signal_ids = {
            str(record.get('signal_id')).strip()
            for record in self.triangle_data
            if isinstance(record, dict) and str(record.get('signal_id') or '').strip()
        }

    def _apply_memory_limits(self):
        _trim_list_inplace(self.triangle_data, MAX_TRIANGLE_RECORDS, keep='head')
        _trim_list_inplace(self.triangle_rounds, MAX_TRIANGLE_ROUNDS, keep='head')

        if isinstance(self.arbitrage_data, dict):
            records = self.arbitrage_data.get('trade_records')
            if isinstance(records, list) and len(records) > MAX_ARBITRAGE_RECORDS:
                summary = self.arbitrage_data.get('profit_summary')
                if not isinstance(summary, dict):
                    summary = {}
                    self.arbitrage_data['profit_summary'] = summary

                drop_count = len(records) - MAX_ARBITRAGE_RECORDS
                dropped = records[:drop_count]
                archived = _to_float(summary.get('archived_net_profit', 0.0), 0.0)
                archived += sum(_to_float(item.get('net_profit', 0.0), 0.0) for item in dropped)

                del records[:drop_count]
                summary['archived_net_profit'] = round(archived, 4)
                summary['retained_record_count'] = len(records)

        if not isinstance(self.lead_data, dict):
            self.lead_data = {'summary': _build_lead_summary([], 0.0, 0.0), 'trade_records': []}
        self.lead_data.setdefault('trade_records', [])
        self.lead_data.setdefault('summary', {})
        lead_records = self.lead_data.get('trade_records')
        if isinstance(lead_records, list) and len(lead_records) > MAX_LEAD_RECORDS:
            lead_summary = self.lead_data.get('summary')
            if not isinstance(lead_summary, dict):
                lead_summary = {}
                self.lead_data['summary'] = lead_summary

            archived_realized_pnl = _to_float(lead_summary.get('archived_realized_pnl', 0.0), 0.0)
            dropped_records = lead_records[MAX_LEAD_RECORDS:]
            archived_realized_pnl += sum(
                _to_float(record.get('order_pnl'), _extract_triangle_profit_delta(record) or 0.0)
                for record in dropped_records
                if isinstance(record, dict)
            )
            del lead_records[MAX_LEAD_RECORDS:]
            self.lead_data['summary'] = _build_lead_summary(
                lead_records,
                initial_funds=lead_summary.get('initial_funds', 0.0),
                archived_realized_pnl=archived_realized_pnl,
            )

        _trim_profit_curve_points(self.total_profit_data)
        if isinstance(self.total_profit_data, dict):
            self.total_profit_data['profit_summary'] = _build_total_profit_summary(self.total_profit_data)
    
    def update_global_data(self):
        global global_data
        self._apply_memory_limits()
        global_data['triangle'] = self.triangle_data
        global_data['triangle_summary'] = self.triangle_summary
        global_data['triangle_rounds'] = self.triangle_rounds
        global_data['arbitrage_data'] = self.arbitrage_data
        global_data['lead_data'] = self.lead_data
        global_data['total_profit_data'] = self.total_profit_data
        global_data['top_data'] = self.top_data
        global_data['bottom_data'] = self.bottom_data
        global_data['strategy_status'] = self.strategy_status
        global_data['market_data'] = self.market_data
        global_data['arbitrage_start_time'] = self.arbitrage_start_time
    
    def add_triangle_trade(self, trade_data):
        signal_id = str(trade_data.get('signal_id') or '').strip()
        if signal_id and signal_id in self._triangle_signal_ids:
            print(f"三角策略重复信号已忽略: {signal_id}")
            return

        if not isinstance(self.triangle_data, list):
            self.triangle_data = []
        if not isinstance(self.triangle_rounds, list):
            self.triangle_rounds = []
        if not isinstance(self.triangle_summary, dict):
            self.triangle_summary = {}
        if not isinstance(getattr(self, '_triangle_open_positions', None), dict):
            self._triangle_open_positions = _rebuild_triangle_open_positions(self.triangle_data)

        raw_records = trade_data.get('trade_records') if isinstance(trade_data, dict) and isinstance(trade_data.get('trade_records'), list) else [trade_data]
        existing_records = []
        existing_keys = set()

        for current in self.triangle_data:
            if not isinstance(current, dict):
                continue
            record = _normalize_triangle_trade_record(current)
            if record['order_key'] in existing_keys:
                continue
            existing_keys.add(record['order_key'])
            existing_records.append(record)

        added_records = 0
        duplicate_records = 0
        added_close_profit = 0.0
        added_close_count = 0
        added_win_count = 0
        added_lose_count = 0
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                continue
            record = _normalize_triangle_trade_record(raw_record)
            if record['order_key'] in existing_keys:
                duplicate_records += 1
                continue
            existing_keys.add(record['order_key'])

            trade_type = str(record.get('trade_type') or '').strip()
            if trade_type in TRIANGLE_OPEN_TYPES:
                _triangle_apply_open_trade(self._triangle_open_positions, record)
            elif _trade_type_matches(trade_type, TRIANGLE_CLOSE_TYPES):
                computed_pnl = _triangle_apply_close_trade(self._triangle_open_positions, record, update_record=True)
                if computed_pnl is not None:
                    added_close_profit += _to_float(computed_pnl, 0.0)
                    added_close_count += 1
                    if computed_pnl > 0:
                        added_win_count += 1
                    elif computed_pnl < 0:
                        added_lose_count += 1

            existing_records.insert(0, record)
            added_records += 1

        summary = self.triangle_summary if isinstance(self.triangle_summary, dict) else {}
        initial_funds = _to_float(summary.get('initial_funds', trade_data.get('initial_funds', 0.0) if isinstance(trade_data, dict) else 0.0), 0.0)

        if isinstance(trade_data, dict) and isinstance(trade_data.get('round_record'), dict):
            self.triangle_rounds.insert(0, trade_data['round_record'])
        if isinstance(trade_data, dict) and isinstance(trade_data.get('round_records'), list):
            self.triangle_rounds = trade_data['round_records']

        if len(existing_records) > MAX_TRIANGLE_RECORDS:
            del existing_records[MAX_TRIANGLE_RECORDS:]

        self.triangle_data = existing_records
        current_total_realized_pnl = _to_float(summary.get('total_realized_pnl', summary.get('total_profit', 0.0)), 0.0) + added_close_profit
        round_profit = _sum_triangle_round_profit(self.triangle_rounds)
        current_return_rate = (current_total_realized_pnl / initial_funds * 100) if initial_funds > 0 else 0.0
        current_funds = initial_funds + current_total_realized_pnl

        updated_summary = dict(summary)
        updated_summary.update({
            'initial_funds': round(initial_funds, 4),
            'total_realized_pnl': round(current_total_realized_pnl, 4),
            'current_funds': round(current_funds, 4),
            'total_return_rate': round(current_return_rate, 6),
            'total_profit': round(current_total_realized_pnl, 4),
            'total_profit_all': round(current_total_realized_pnl + round_profit, 4),
            'retained_record_count': len(existing_records),
            'close_trade_count': int(_to_float(summary.get('close_trade_count', 0), 0.0)) + added_close_count,
            'win_trades': int(_to_float(summary.get('win_trades', 0), 0.0)) + added_win_count,
            'lose_trades': int(_to_float(summary.get('lose_trades', 0), 0.0)) + added_lose_count,
        })

        if 'archived_realized_pnl' not in updated_summary:
            updated_summary['archived_realized_pnl'] = 0.0

        self.triangle_summary = updated_summary
        self.strategy_status['triangle'] = '运行'
        if signal_id:
            self._triangle_signal_ids.add(signal_id)

        self.update_global_data()
        latest_record = existing_records[0] if existing_records else {}
        latest_symbol = latest_record.get('symbol', '-') if isinstance(latest_record, dict) else '-'
        latest_account = latest_record.get('account_label', '-') if isinstance(latest_record, dict) else '-'
        latest_type = latest_record.get('trade_type', '-') if isinstance(latest_record, dict) else '-'
        latest_pnl = _to_float(latest_record.get('order_pnl'), 0.0) if isinstance(latest_record, dict) else 0.0
        print(
            f"三角更新 | 新增:{added_records} 重复:{duplicate_records} 最新:{latest_account}/{latest_symbol}/{latest_type} "
            f"订单盈亏:{latest_pnl:.4f}USDT"
        )

        # 保存三角策略数据到本地文件
        save_triangle_data({
            'trade_records': self.triangle_data,
            'round_records': self.triangle_rounds,
            'summary': self.triangle_summary,
        })

    def update_lead_data(self, data):
        if not isinstance(self.lead_data, dict):
            self.lead_data = load_lead_data()
        self.lead_data.setdefault('trade_records', [])
        self.lead_data.setdefault('summary', {})

        raw_records = data.get('trade_records') if isinstance(data, dict) and isinstance(data.get('trade_records'), list) else [data]
        existing_records = []
        existing_keys = set()

        for current in self.lead_data.get('trade_records', []):
            if not isinstance(current, dict):
                continue
            record = _normalize_lead_trade_record(current)
            if record['order_key'] in existing_keys:
                continue
            existing_keys.add(record['order_key'])
            existing_records.append(record)

        added_records = 0
        duplicate_records = 0
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                continue
            record = _normalize_lead_trade_record(raw_record)
            if record['order_key'] in existing_keys:
                duplicate_records += 1
                continue
            existing_keys.add(record['order_key'])
            existing_records.insert(0, record)
            added_records += 1

        summary = self.lead_data.get('summary', {}) if isinstance(self.lead_data.get('summary'), dict) else {}
        initial_funds = _to_float(summary.get('initial_funds', data.get('initial_funds', 0.0) if isinstance(data, dict) else 0.0), 0.0)
        archived_realized_pnl = _to_float(summary.get('archived_realized_pnl', 0.0), 0.0)

        _replay_trade_records_with_pnl(existing_records)

        if len(existing_records) > MAX_LEAD_RECORDS:
            dropped_records = existing_records[MAX_LEAD_RECORDS:]
            archived_realized_pnl += sum(
                _to_float(record.get('order_pnl'), _extract_triangle_profit_delta(record) or 0.0)
                for record in dropped_records
                if isinstance(record, dict)
            )
            del existing_records[MAX_LEAD_RECORDS:]

        _replay_trade_records_with_pnl(existing_records)

        self.lead_data = {
            'summary': _build_lead_summary(
                existing_records,
                initial_funds=initial_funds,
                archived_realized_pnl=archived_realized_pnl,
            ),
            'trade_records': existing_records,
        }
        self.strategy_status['lead'] = '运行'

        latest_record = existing_records[0] if existing_records else {}
        latest_symbol = latest_record.get('symbol', '-') if isinstance(latest_record, dict) else '-'
        latest_account = latest_record.get('account_label', '-') if isinstance(latest_record, dict) else '-'
        latest_type = latest_record.get('trade_type', '-') if isinstance(latest_record, dict) else '-'
        latest_pnl = _to_float(latest_record.get('order_pnl'), 0.0) if isinstance(latest_record, dict) else 0.0
        print(
            f"带单更新 | 新增:{added_records} 重复:{duplicate_records} 最新:{latest_account}/{latest_symbol}/{latest_type} "
            f"订单盈亏:{latest_pnl:.4f}USDT"
        )

        self.update_global_data()
        save_lead_data(self.lead_data)
    
    def update_arbitrage_data(self, data):
        """更新套利数据：仅以单笔订单的 net_profit 作为总额计算来源。"""
        arbitrage_data_file = os.path.join(data_dir, 'arbitrage_trades.json')
        existing_data = {}
        if os.path.exists(arbitrage_data_file):
            try:
                with open(arbitrage_data_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"读取套利策略数据文件异常: {e}")

        def build_record(detail):
            symbol = detail.get('symbol', 'UNKNOWN')
            close_time = detail.get('close_time_cn') or detail.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            close_order_id = detail.get('close_order_id') or detail.get('order_id')
            order_id = str(close_order_id) if close_order_id else f"{symbol}_{close_time}"
            return {
                'symbol': symbol,
                'open_side': detail.get('open_side', 'SELL'),
                'quantity': _to_float(detail.get('open_executed_qty', detail.get('quantity', 0))),
                'open_price': _to_float(detail.get('open_avg_price', detail.get('open_price', 0))),
                'close_price': _to_float(detail.get('close_avg_price', detail.get('close_price', 0))),
                'net_profit': _to_float(detail.get('net_profit', 0)),
                'timestamp': close_time,
                'order_id': order_id
            }

        if not isinstance(self.arbitrage_data, dict):
            self.arbitrage_data = {}
        self.arbitrage_data.setdefault('trade_records', [])
        self.arbitrage_data.setdefault('profit_summary', {})

        # 启动时间只保留首次有效值，避免后续请求覆盖
        self.arbitrage_start_time = (
            existing_data.get('start_time')
            or self.arbitrage_data.get('start_time')
            or data.get('start_time')
        )
        if self.arbitrage_start_time:
            self.arbitrage_data['start_time'] = self.arbitrage_start_time

        incoming_summary = data.get('profit_summary', {}) if isinstance(data.get('profit_summary'), dict) else {}
        current_summary = self.arbitrage_data.get('profit_summary', {}) if isinstance(self.arbitrage_data.get('profit_summary'), dict) else {}
        existing_summary = existing_data.get('profit_summary', {}) if isinstance(existing_data.get('profit_summary'), dict) else {}

        # 初始资金优先使用本地已落盘的值，其次才使用请求中的值
        initial_funds = _to_float(
            existing_summary.get(
                'initial_funds',
                current_summary.get('initial_funds', incoming_summary.get('initial_funds', 500.0))
            ),
            500.0
        )

        # 先规范化已有记录并按 order_id 去重
        normalized_records = []
        existing_ids = set()
        for record in self.arbitrage_data.get('trade_records', []):
            normalized = build_record(record)
            if normalized['order_id'] in existing_ids:
                continue
            existing_ids.add(normalized['order_id'])
            normalized_records.append(normalized)
        self.arbitrage_data['trade_records'] = normalized_records

        # 只接收订单明细，汇总完全由订单 net_profit 自动重算
        incoming_records = data.get('trade_details') or data.get('trade_records') or []
        added_records = 0
        duplicate_records = 0
        added_symbols = []

        for detail in incoming_records:
            record = build_record(detail)
            if record['order_id'] in existing_ids:
                duplicate_records += 1
                continue
            existing_ids.add(record['order_id'])
            self.arbitrage_data['trade_records'].append(record)
            added_records += 1
            added_symbols.append(record['symbol'])

        archived_net_profit = _to_float(
            current_summary.get('archived_net_profit', existing_summary.get('archived_net_profit', 0.0)),
            0.0
        )

        # 套利记录按最新优先保留尾部，被裁剪部分的利润并入归档，保证累计收益不丢失
        records = self.arbitrage_data['trade_records']
        if len(records) > MAX_ARBITRAGE_RECORDS:
            drop_count = len(records) - MAX_ARBITRAGE_RECORDS
            dropped_records = records[:drop_count]
            archived_net_profit += sum(_to_float(item.get('net_profit', 0.0)) for item in dropped_records)
            del records[:drop_count]

        retained_net_profit = sum(_to_float(record.get('net_profit', 0.0)) for record in records)
        total_net_profit = archived_net_profit + retained_net_profit
        total_margin = initial_funds + total_net_profit
        total_return_rate = (total_net_profit / initial_funds * 100) if initial_funds > 0 else 0.0

        profit_summary = {
            'total_net_profit': round(total_net_profit, 4),
            'initial_funds': initial_funds,
            'total_margin': round(total_margin, 4),
            'total_return_rate': round(total_return_rate, 6),
            'archived_net_profit': round(archived_net_profit, 4),
            'retained_record_count': len(records)
        }

        # 非核心扩展字段只做透传，不参与总额计算
        for key in ['yearly_return_rate', 'yearly_return_profit', 'round_net_profit', 'round_return_rate']:
            if key in incoming_summary:
                profit_summary[key] = incoming_summary[key]
            elif key in current_summary:
                profit_summary[key] = current_summary[key]
            elif key in existing_summary:
                profit_summary[key] = existing_summary[key]

        self.arbitrage_data['profit_summary'] = profit_summary

        symbol_summary = ','.join(added_symbols[:5]) if added_symbols else '无新增交易'
        if len(added_symbols) > 5:
            symbol_summary += f" 等{len(added_symbols)}个"

        new_profit = sum(_to_float(record.get('net_profit', 0.0)) for record in self.arbitrage_data['trade_records'][-added_records:]) if added_records > 0 else 0.0
        print(
            f"套利更新 | 收到:{len(incoming_records)} 新增:{added_records} 重复:{duplicate_records} "
            f"新增净收益:{new_profit:.4f}USDT"
        )
        print(
            f"套利汇总 | 交易对:{symbol_summary} 总盈利:{total_net_profit:.4f}USDT "
            f"总保证金:{total_margin:.4f}USDT 收益率:{total_return_rate:.6f}%"
        )

        self.update_global_data()
        save_arbitrage_data(self.arbitrage_data)
    
    def update_strategy_status(self, strategy, status):
        if strategy in self.strategy_status:
            self.strategy_status[strategy] = status
            self.update_global_data()
            return True
        return False
    
    def update_market_data(self, data):
        if 'cycle' in data:
            self.market_data['cycle'] = data['cycle']
        if 'alpha_engine_regime' in data:
            self.market_data['alpha_engine_regime'] = data['alpha_engine_regime']
        if 'alpha_engine_alpha' in data:
            self.market_data['alpha_engine_alpha'] = data['alpha_engine_alpha']
        if 'alpha_engine_ma' in data:
            self.market_data['alpha_engine_ma'] = data['alpha_engine_ma']
        if 'btc_price' in data:
            self.market_data['btc_price'] = data['btc_price']
        self.update_global_data()
        return True

    def update_post_feed(self):
        """从本地 post_feed.json 重载发帖数据 (用户手动编辑后刷新)。"""
        new_feed = load_promo_posts()
        old_snapshot = json.dumps(self.post_feed, ensure_ascii=False, sort_keys=True)
        new_snapshot = json.dumps(new_feed, ensure_ascii=False, sort_keys=True)
        if old_snapshot != new_snapshot:
            self.post_feed = new_feed
            self.update_global_data()
            return True
        return False

    def add_post_to_feed(self, post):
        """接收一条新帖, 追加/去重到 post_feed, 保存并推送。"""
        if not isinstance(post, dict):
            return False
        content = str(post.get('content') or '').strip()
        if not content:
            return False

        item = _normalize_post_record(post, str(post.get('source') or 'promo').strip() or 'promo')
        if not item:
            return False

        # 去重: 同 label + 同 timestamp + 同 post_type 视为重复
        new_key = (str(item.get('label') or ''), str(item.get('timestamp') or ''), str(item.get('post_type') or ''))
        for existing in self.post_feed:
            ekey = (str(existing.get('label') or ''), str(existing.get('timestamp') or ''), str(existing.get('post_type') or ''))
            if ekey == new_key:
                return False

        self.post_feed.append(item)
        self.post_feed.sort(key=_post_sort_key)
        if len(self.post_feed) > 500:
            self.post_feed = self.post_feed[-500:]
        save_post_feed(self.post_feed)
        self.update_global_data()
        return True
    
    def update_top_data(self, data):
        for key in ('position_status', 'position_quantity', 'position_avg_price', 'position_symbol', 'trade_records', 'status'):
            if key in data:
                self.top_data[key] = data[key]
        self.strategy_status['top'] = self.top_data.get('status', '持仓')
        self.update_global_data()
        save_top_data(self.top_data)
        return True

    def update_bottom_data(self, data):
        for key in ('position_status', 'position_quantity', 'position_avg_price', 'position_symbol', 'trade_records', 'status'):
            if key in data:
                self.bottom_data[key] = data[key]
        self.strategy_status['bottom'] = self.bottom_data.get('status', '清仓')
        self.update_global_data()
        save_bottom_data(self.bottom_data)
        return True
    
    def get_all_data(self):
        return {
            'triangle': self.triangle_data,
            'triangle_rounds': self.triangle_rounds,
            'triangle_summary': self.triangle_summary,
            'lead': self.lead_data,
            'arbitrage': self.arbitrage_data,
            'total_profit': self.total_profit_data,
            'top': self.top_data,
            'bottom': self.bottom_data,
            'strategy_status': self.strategy_status,
            'market_data': self.market_data,
            **_post_feed_payload(self.post_feed),
            'arbitrage_start_time': self.arbitrage_start_time
        }

# 初始化数据存储
data_storage = DataStorage()

# 启动文件更新检查线程
file_update_thread = threading.Thread(target=check_file_updates, daemon=True)
file_update_thread.start()

# 启动获取 BTC 价格的线程
btc_price_thread = threading.Thread(target=fetch_btc_price, daemon=True)
btc_price_thread.start()

# WebSocket 事件处理
@socketio.on('connect')
def handle_connect():
    # 登录门禁开启时拒绝未登录的 Socket.IO 连接, 避免绕过登录直接获取数据
    if _login_enabled() and session.get('auth') is not True:
        return False
    # print('Client connected')
    socketio.emit('all_data', data_storage.get_all_data())

@socketio.on('disconnect')
def handle_disconnect():
    pass

# API 端点
@app.route('/api/update_triangle', methods=['POST'])
@require_api_token
def update_triangle_data():
    data = request.json
    if data:
        data_storage.add_triangle_trade(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_lead', methods=['POST'])
@require_api_token
def update_lead_data():
    data = request.json
    if data:
        data_storage.update_lead_data(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_arbitrage', methods=['POST'])
@require_api_token
def update_arbitrage_data():
    data = request.json
    if data:
        data_storage.update_arbitrage_data(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_post_feed', methods=['POST'])
@require_api_token
def update_post_feed():
    """接收 Promo / AlphaEngine 推送的单条帖子, 保存到 post_feed.json 并推送前端。"""
    data = request.json
    if data and isinstance(data, dict):
        added = data_storage.add_post_to_feed(data)
        socketio.emit('post_feed_update', {
            **_post_feed_payload(data_storage.post_feed),
        })
        return jsonify({'status': 'success', 'added': added})
    return jsonify({'status': 'error'}), 400

@app.route('/api/get_post_feed', methods=['GET'])
def get_post_feed():
    """分页读取发帖动态，默认返回最新 20 条，before 用于继续读取更早的帖子。"""
    try:
        limit = int(request.args.get('limit', POST_FEED_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = POST_FEED_PAGE_SIZE
    limit = max(1, min(limit, 50))
    before = str(request.args.get('before') or '').strip()
    posts = data_storage.post_feed if isinstance(data_storage.post_feed, list) else []

    candidates = posts
    if before:
        # 按真实时间过滤: 只返回早于 before 时间戳的帖子
        before_dt = _parse_post_timestamp(before)
        if before_dt is not None:
            candidates = [
                post for post in posts
                if _post_sort_key(post) < (0, before_dt.timestamp())
            ]
        else:
            candidates = [post for post in posts if str(post.get('timestamp') or '') < before]

    page = candidates[-limit:]
    return jsonify({
        'post_feed': page,
        'post_feed_total': len(posts),
        'post_feed_has_more': len(candidates) > len(page),
    })

@app.route('/health')
def health():
    return jsonify({
        'ok': True,
        'service': 'Web',
        'auth_required': bool(str(os.getenv('WEB_API_TOKEN', '') or '').strip()),
    })


@app.route('/api/get_data', methods=['GET'])
def get_data():
    return jsonify(data_storage.get_all_data())

@app.route('/api/update_strategy_status', methods=['POST'])
@require_api_token
def update_strategy_status():
    data = request.json
    if data and 'strategy' in data and 'status' in data:
        success = data_storage.update_strategy_status(data['strategy'], data['status'])
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_market_data', methods=['POST'])
@require_api_token
def update_market_data():
    data = request.json
    if data:
        success = data_storage.update_market_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_top', methods=['POST'])
@require_api_token
def update_top_data():
    data = request.json
    if data:
        success = data_storage.update_top_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_bottom', methods=['POST'])
@require_api_token
def update_bottom_data():
    data = request.json
    if data:
        success = data_storage.update_bottom_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

# 主页
@app.route('/')
def index():
    return render_template('index.html')

# 上下文处理器
@app.context_processor
def inject_datetime():
    return {'current_datetime': datetime.now()}

# 为 data 目录添加静态文件路由
@app.route('/data/<path:filename>')
def serve_data_file(filename):
    return send_from_directory(data_dir, filename)

# 为 static 目录添加静态文件路由
@app.route('/static/<path:filename>')
def serve_static_file(filename):
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_dir, filename)

if __name__ == '__main__':
    class FilteredStderr:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def write(self, message):
            if not message:
                return

            if 'Bad request version' in message:
                return
            if 'code 400, message' in message:
                return

            # 过滤包含控制字符的异常协议噪音行
            has_ctrl = any((ord(ch) < 32 and ch not in '\r\n\t') for ch in message)
            if has_ctrl:
                return

            self.wrapped.write(message)

        def flush(self):
            self.wrapped.flush()

    # 降低普通请求日志级别，并屏蔽异常协议扫描噪音
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.logger.disabled = True
    sys.stderr = FilteredStderr(sys.stderr)
    run_kwargs = {
        'host': '0.0.0.0',
        'port': 5000,
        'debug': False,
        'log_output': False,
    }
    if SOCKETIO_ASYNC_MODE != 'eventlet':
        run_kwargs['allow_unsafe_werkzeug'] = True
    if not str(os.getenv('WEB_API_TOKEN', '') or '').strip():
        print('[Web] WARNING: 未设置 WEB_API_TOKEN, 写接口无鉴权 (建议仅内网暴露或尽快配置)')
    if not _SESSION_SECRET_FROM_ENV:
        print('[Web] WARNING: 未设置 WEB_SESSION_SECRET, 已生成临时会话密钥, 重启后会话失效')
    if _invalid_sha256_configured():
        print(
            '[Web] WARNING: WEB_LOGIN_PASSWORD_SHA256 配置非法（非 64 位 hex），'
            + ('登录未启用' if not _login_enabled() else '已忽略，回退使用 WEB_LOGIN_PASSWORD')
        )
    elif not _login_enabled():
        print('[Web] WARNING: 登录未启用（未配置 WEB_LOGIN_PASSWORD），面板开放访问；部署时必须配置')
    print(f'[Web] 异步模式: {SOCKETIO_ASYNC_MODE} (WEB_DISABLE_EVENTLET={_disable_eventlet})')
    try:
        socketio.run(app, **run_kwargs)
    except TypeError as exc:
        # 旧版 Flask (<2.2) 不支持 allow_unsafe_werkzeug 参数, 去掉后重试
        if 'allow_unsafe_werkzeug' not in str(exc):
            raise
        run_kwargs.pop('allow_unsafe_werkzeug', None)
        socketio.run(app, **run_kwargs)
