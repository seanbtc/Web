from flask import Flask, render_template, jsonify, request, send_from_directory
import os
import json
import requests
import logging
import sys
from datetime import datetime
import threading
import time
from flask_socketio import SocketIO

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# 添加 CORS 支持
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response
socketio = SocketIO(app, cors_allowed_origins='*')


def _env_int(name, default):
    """读取正整数环境变量，非法值回退默认。"""
    raw = os.getenv(name, '')
    try:
        value = int(raw)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return default


MAX_TRADINGVIEW_RECORDS = _env_int('WEB_MAX_TRADINGVIEW_RECORDS', 3000)
MAX_TRADINGVIEW_ROUNDS = _env_int('WEB_MAX_TRADINGVIEW_ROUNDS', 1000)
MAX_TOP_BOTTOM_RECORDS = _env_int('WEB_MAX_TOP_BOTTOM_RECORDS', 3000)
MAX_SPOT_RECORDS = _env_int('WEB_MAX_SPOT_RECORDS', 3000)
MAX_ARBITRAGE_RECORDS = _env_int('WEB_MAX_ARBITRAGE_RECORDS', 5000)
MAX_LEAD_RECORDS = _env_int('WEB_MAX_LEAD_RECORDS', 5000)
MAX_PROFIT_CURVE_POINTS = _env_int('WEB_MAX_PROFIT_CURVE_POINTS', 4000)


def _trim_list_inplace(items, limit, keep='head'):
    """原地裁剪列表，避免历史数据无限增长。"""
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


TRADINGVIEW_CLOSE_TYPES = {'平仓', '止盈', '止损'}


def _sum_tradingview_round_profit(round_records):
    if not isinstance(round_records, list):
        return 0.0

    total_profit = 0.0
    for record in round_records:
        if not isinstance(record, dict):
            continue
        total_profit += _to_float(record.get('pnl', record.get('profit', 0.0)), 0.0)
    return total_profit


def _extract_tradingview_profit_delta(trade_data):
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
    if trade_type not in TRADINGVIEW_CLOSE_TYPES and not any(keyword in trade_type for keyword in TRADINGVIEW_CLOSE_TYPES):
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
    order_pnl = _extract_tradingview_profit_delta(trade_data)
    realized_pnl = trade_data.get('realized_pnl')

    normalized = {
        'order_key': '',
        'order_id': str(trade_data.get('order_id') or '').strip(),
        'account_id': str(trade_data.get('account_id') or '').strip(),
        'account_label': str(trade_data.get('account_label') or trade_data.get('account_id') or '默认账号').strip(),
        'account_type': str(trade_data.get('account_type') or '').strip(),
        'account_profile': str(trade_data.get('account_profile') or '').strip(),
        'symbol': str(trade_data.get('symbol') or '').strip(),
        'side': str(trade_data.get('side') or '').strip().upper(),
        'quantity': round(_to_float(trade_data.get('quantity'), 0.0), 8),
        'price': _to_float(trade_data.get('price'), 0.0),
        'trade_type': trade_type,
        'reason': str(trade_data.get('reason') or trade_data.get('alert_message') or '').strip(),
        'timestamp': timestamp,
        'order_status': str(trade_data.get('order_status') or '').strip(),
        'signal_id': str(trade_data.get('signal_id') or '').strip(),
        'gross_pnl': trade_data.get('gross_pnl'),
        'realized_pnl': round(_to_float(realized_pnl, order_pnl), 4) if (realized_pnl is not None or order_pnl is not None) else None,
        'order_pnl': round(_to_float(order_pnl, 0.0), 4) if order_pnl is not None else None,
        'open_fee': round(_to_float(trade_data.get('open_fee'), 0.0), 4) if trade_data.get('open_fee') is not None else 0.0,
        'close_fee': round(_to_float(trade_data.get('close_fee'), 0.0), 4) if trade_data.get('close_fee') is not None else 0.0,
        'entry_price': _to_float(trade_data.get('entry_price'), None),
        'exit_price': _to_float(trade_data.get('exit_price'), None),
        'entry_timestamp': str(trade_data.get('entry_timestamp') or '').strip(),
        'exit_timestamp': str(trade_data.get('exit_timestamp') or '').strip(),
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
                profit_value = _extract_tradingview_profit_delta(record)
            if profit_value is None and not _trade_type_matches(record.get('trade_type'), TRADINGVIEW_CLOSE_TYPES):
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


def save_lead_data(data):
    file_path = os.path.join(data_dir, 'lead_trades.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("带单策略数据已保存")
    except Exception as e:
        print(f"保存带单策略数据失败: {e}")

# 从本地文件读取摸顶抄底策略数据
def load_top_bottom_data():
    file_path = os.path.join(data_dir, 'top_bottom_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取摸顶抄底数据失败: {e}")
    return {'trade_records': []}

# 从本地文件读取现货策略数据
def load_spot_data():
    file_path = os.path.join(data_dir, 'spot_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取现货策略数据失败: {e}")
    return {'trade_records': []}

# 从本地文件读取总仓盈亏数据
def load_total_profit_data():
    file_path = os.path.join(data_dir, 'total_profit.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['profit_summary'] = _build_total_profit_summary(data)
                return data
        except Exception as e:
            print(f"读取总仓盈亏数据失败: {e}")
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

# 从本地文件读取TradingView策略数据
def load_tradingview_data():
    file_path = os.path.join(data_dir, 'tradingview_trades.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"读取TradingView策略数据失败: {e}")
    return {'trade_records': [], 'round_records': [], 'summary': {
        'win_trades': 0,
        'lose_trades': 0,
        'total_profit': 0.0,
        'total_profit_all': 0.0,
        'initial_funds': 1000.0
    }}

# 保存TradingView策略数据到本地文件
def save_tradingview_data(data):
    file_path = os.path.join(data_dir, 'tradingview_trades.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("TradingView策略数据已保存")
    except Exception as e:
        print(f"保存TradingView策略数据失败: {e}")

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

# 保存套利策略数据到本地文件
def save_arbitrage_data(data):
    file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("套利策略数据已保存")
    except Exception as e:
        print(f"保存套利策略数据失败: {e}")

# 定期检查文件更新的函数
def check_file_updates():
    top_bottom_file_path = os.path.join(data_dir, 'top_bottom_trades.json')
    spot_file_path = os.path.join(data_dir, 'spot_trades.json')
    total_profit_file_path = os.path.join(data_dir, 'total_profit.json')
    tradingview_file_path = os.path.join(data_dir, 'tradingview_trades.json')
    lead_file_path = os.path.join(data_dir, 'lead_trades.json')
    arbitrage_file_path = os.path.join(data_dir, 'arbitrage_trades.json')
    last_modified_top_bottom = 0
    last_modified_spot = 0
    last_modified_total_profit = 0
    last_modified_tradingview = 0
    last_modified_lead = 0
    last_modified_arbitrage = 0
    
    while True:
        try:
            # 检查摸顶抄底策略文件
            if os.path.exists(top_bottom_file_path):
                current_modified = os.path.getmtime(top_bottom_file_path)
                if current_modified > last_modified_top_bottom:
                    last_modified_top_bottom = current_modified
                    # 重新加载数据
                    new_data = load_top_bottom_data()
                    # 更新仓位状态
                    data_storage.top_bottom_data['position_status'] = new_data.get('position_status', '摸顶做空')
                    data_storage.top_bottom_data['position_quantity'] = new_data.get('position_quantity', 0.1)
                    data_storage.top_bottom_data['position_avg_price'] = new_data.get('position_avg_price', 11600.0)
                    data_storage.top_bottom_data['position_symbol'] = new_data.get('position_symbol', 'BTCUSDT')
                    data_storage.top_bottom_data['trade_records'] = new_data.get('trade_records', [])
                    # 更新策略状态
                    data_storage.strategy_status['top_bottom'] = new_data.get('position_status', '摸顶做空')
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("摸顶抄底数据已更新")
            
            # 检查现货策略文件
            if os.path.exists(spot_file_path):
                current_modified = os.path.getmtime(spot_file_path)
                if current_modified > last_modified_spot:
                    last_modified_spot = current_modified
                    # 重新加载数据
                    new_data = load_spot_data()
                    # 更新仓位状态
                    data_storage.spot_data['position_quantity'] = new_data.get('position_quantity', 0.0)
                    data_storage.spot_data['position_avg_price'] = new_data.get('position_avg_price', 0.0)
                    data_storage.spot_data['position_symbol'] = new_data.get('position_symbol', 'BTCUSDT')
                    data_storage.spot_data['trade_records'] = new_data.get('trade_records', [])
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("现货策略数据已更新")
            
            # 检查总仓盈亏数据文件
            if os.path.exists(total_profit_file_path):
                current_modified = os.path.getmtime(total_profit_file_path)
                if current_modified > last_modified_total_profit:
                    last_modified_total_profit = current_modified
                    # 重新加载数据
                    new_data = load_total_profit_data()
                    # 更新总仓盈亏数据
                    data_storage.total_profit_data = new_data
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("总仓盈亏数据已更新")
            

            
            # 检查TradingView策略数据文件
            if os.path.exists(tradingview_file_path):
                current_modified = os.path.getmtime(tradingview_file_path)
                if current_modified > last_modified_tradingview:
                    last_modified_tradingview = current_modified
                    # 重新加载数据
                    new_data = load_tradingview_data()
                    # 更新TradingView策略数据
                    data_storage.tradingview_data = new_data.get('trade_records', [])
                    data_storage.tradingview_rounds = new_data.get('round_records', [])
                    data_storage.tradingview_summary = new_data.get('summary', {
                        'win_trades': 0,
                        'lose_trades': 0,
                        'total_profit': 0.0,
                        'total_profit_all': 0.0,
                        'initial_funds': 1000.0
                    })
                    data_storage._refresh_tradingview_signal_ids()
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("TradingView策略数据已更新")

            # 检查带单策略数据文件
            if os.path.exists(lead_file_path):
                current_modified = os.path.getmtime(lead_file_path)
                if current_modified > last_modified_lead:
                    last_modified_lead = current_modified
                    new_data = load_lead_data()
                    data_storage.lead_data = new_data
                    data_storage.strategy_status['lead'] = '运行'
                    data_storage.update_global_data()
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("带单策略数据已更新")
            
            # 检查套利策略数据文件
            if os.path.exists(arbitrage_file_path):
                current_modified = os.path.getmtime(arbitrage_file_path)
                if current_modified > last_modified_arbitrage:
                    last_modified_arbitrage = current_modified
                    # 重新加载数据
                    new_data = load_arbitrage_data()
                    # 更新套利策略数据
                    data_storage.arbitrage_data = new_data
                    data_storage.update_global_data()
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    print("套利策略数据已更新")
            
            # 每5秒检查一次
            time.sleep(5)
        except Exception as e:
            print(f"检查文件更新失败: {e}")
            time.sleep(5)

# 全局数据存储
# 加载摸顶抄底策略数据
top_bottom_file_data = load_top_bottom_data()
# 加载现货策略数据
spot_file_data = load_spot_data()
# 加载总仓盈亏数据
total_profit_data = load_total_profit_data()
# 加载套利策略数据
arbitrage_data = load_arbitrage_data()
# 加载带单策略数据
lead_data = load_lead_data()
# 加载TradingView策略数据
tradingview_data = load_tradingview_data()
tradingview_trade_records = tradingview_data.get('trade_records', [])
tradingview_round_records = tradingview_data.get('round_records', [])
tradingview_summary = tradingview_data.get('summary', {
    'win_trades': 0,
    'lose_trades': 0,
    'total_profit': 0.0,
    'total_profit_all': 0.0,
    'initial_funds': 1000.0
})

# 定期获取BTC价格的函数
def fetch_btc_price():
    # 延迟启动，确保服务已经完全启动
    time.sleep(10)
    
    while True:
        try:
            # 尝试使用Binance API
            response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=3)
            if response.status_code == 200:
                data = response.json()
                if 'price' in data:
                    btc_price = float(data['price'])
                    # 更新市场数据
                    data_storage.update_market_data({'btc_price': btc_price})
                    # 广播更新
                    socketio.emit('all_data', data_storage.get_all_data())
                    # print(f"BTC价格更新: ${btc_price}")
            else:
                # 如果Binance API失败，尝试使用CoinGecko API
                response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    if 'bitcoin' in data and 'usd' in data['bitcoin']:
                        btc_price = float(data['bitcoin']['usd'])
                        # 更新市场数据
                        data_storage.update_market_data({'btc_price': btc_price})
                        # 广播更新
                        socketio.emit('all_data', data_storage.get_all_data())
                        # print(f"BTC价格更新 (CoinGecko): ${btc_price}")
        except Exception as e:
            print(f"获取BTC价格失败: {e}")
        # 每30秒获取一次价格
        time.sleep(30)

global_data = {
    'tradingview': tradingview_trade_records,  # TradingView交易数据
    'tradingview_rounds': tradingview_round_records,  # TradingView过去几轮盈利记录
    'tradingview_summary': tradingview_summary,  # TradingView策略盈亏摘要
    'arbitrage_data': arbitrage_data,  # 套利策略数据
    'lead_data': lead_data,  # 带单策略数据
    'total_profit_data': total_profit_data,  # 总仓盈亏数据
    'top_bottom_data': {
        'position_status': top_bottom_file_data.get('position_status', '摸顶做空'),  # 当前仓位状态：摸顶做空/抄底做多
        'position_quantity': top_bottom_file_data.get('position_quantity', 0.17),  # 当前仓位数量
        'position_avg_price': top_bottom_file_data.get('position_avg_price', 116900.0),  # 当前仓位均价
        'position_symbol': top_bottom_file_data.get('position_symbol', 'BTCUSDT'),  # 交易对
        'trade_records': top_bottom_file_data.get('trade_records', [])  # 从本地文件读取交易记录
    },
    'spot_data': {
        'position_quantity': spot_file_data.get('position_quantity', 0.0),  # 当前仓位数量
        'position_avg_price': spot_file_data.get('position_avg_price', 0.0),  # 当前仓位均价
        'position_symbol': spot_file_data.get('position_symbol', 'BTCUSDT'),  # 交易对
        'trade_records': spot_file_data.get('trade_records', [])  # 从本地文件读取交易记录
    },
    'strategy_status': {
        'lead': '运行',         # 带单策略状态：运行/暂停
        'tradingview': '做空',  # 4H多空策略状态：做空/做多/暂停
        'arbitrage': '运行',     # 套利策略状态：运行/暂停
        'top_bottom': top_bottom_file_data.get('position_status', '摸顶做空'),  # 摸顶抄底策略状态：摸顶做空/抄底做多/空仓
        'spot': '空仓'           # 现货策略状态：运行满仓/建仓/空仓
    },
    'market_data': {
        'cycle': '熊',  # 牛熊周期判断：牛/熊
        'btc_price': 68000.0  # 当前BTCUSDT价格
    }
}

# 数据存储类
class DataStorage:
    def __init__(self):
        self.tradingview_data = global_data['tradingview']
        self.tradingview_rounds = global_data.get('tradingview_rounds', [])
        self.tradingview_summary = global_data['tradingview_summary']
        self.arbitrage_data = global_data['arbitrage_data']
        self.lead_data = global_data['lead_data']
        self.total_profit_data = global_data['total_profit_data']
        self.top_bottom_data = global_data['top_bottom_data']
        self.spot_data = global_data['spot_data']
        self.strategy_status = global_data['strategy_status']
        self.market_data = global_data['market_data']
        self.arbitrage_start_time = None  # 套利策略启动时间
        self._tradingview_signal_ids = set()
        self._apply_memory_limits()
        self._refresh_tradingview_signal_ids()

    def _refresh_tradingview_signal_ids(self):
        self._tradingview_signal_ids = {
            str(record.get('signal_id')).strip()
            for record in self.tradingview_data
            if isinstance(record, dict) and str(record.get('signal_id') or '').strip()
        }

    def _apply_memory_limits(self):
        _trim_list_inplace(self.tradingview_data, MAX_TRADINGVIEW_RECORDS, keep='head')
        _trim_list_inplace(self.tradingview_rounds, MAX_TRADINGVIEW_ROUNDS, keep='head')

        if isinstance(self.top_bottom_data, dict):
            _trim_list_inplace(self.top_bottom_data.get('trade_records'), MAX_TOP_BOTTOM_RECORDS, keep='head')
        if isinstance(self.spot_data, dict):
            _trim_list_inplace(self.spot_data.get('trade_records'), MAX_SPOT_RECORDS, keep='head')

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
                _to_float(record.get('order_pnl'), _extract_tradingview_profit_delta(record) or 0.0)
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
        global_data['tradingview'] = self.tradingview_data
        global_data['tradingview_rounds'] = self.tradingview_rounds
        global_data['tradingview_summary'] = self.tradingview_summary
        global_data['arbitrage_data'] = self.arbitrage_data
        global_data['lead_data'] = self.lead_data
        global_data['total_profit_data'] = self.total_profit_data
        global_data['top_bottom_data'] = self.top_bottom_data
        global_data['spot_data'] = self.spot_data
        global_data['strategy_status'] = self.strategy_status
        global_data['market_data'] = self.market_data
        global_data['arbitrage_start_time'] = self.arbitrage_start_time
    
    def add_tradingview_trade(self, trade_data):
        signal_id = str(trade_data.get('signal_id') or '').strip()
        if signal_id and signal_id in self._tradingview_signal_ids:
            print(f"TradingView重复信号已忽略: {signal_id}")
            return

        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        trade_data.setdefault('strategy_type', 'legacy_tradingview')
        trade_data.setdefault('strategy_label', '4H策略')
        trade_data.setdefault('web_mode', 'tradingview')
        trade_data.setdefault('web_category', 'tradingview')
        trade_data.setdefault('web_strategy_label', '4H策略')
        trade_data.setdefault('account_id', 'default')
        trade_data.setdefault('account_label', '默认账号')
        trade_data.setdefault('account_profile', 'default.json')
        # 插入到列表开头，实现时间从近到远显示
        self.tradingview_data.insert(0, trade_data)
        if signal_id:
            self._tradingview_signal_ids.add(signal_id)

        # 支持通过接口附带更新过去几轮盈利记录
        if isinstance(trade_data.get('round_record'), dict):
            self.tradingview_rounds.insert(0, trade_data['round_record'])
        if isinstance(trade_data.get('round_records'), list):
            self.tradingview_rounds = trade_data['round_records']

        profit_delta = _extract_tradingview_profit_delta(trade_data)
        if profit_delta is not None:
            current_total_profit = _to_float(self.tradingview_summary.get('total_profit', 0.0), 0.0)
            self.tradingview_summary['total_profit'] = round(current_total_profit + profit_delta, 4)

            current_win_trades = int(_to_float(self.tradingview_summary.get('win_trades', 0), 0.0))
            current_lose_trades = int(_to_float(self.tradingview_summary.get('lose_trades', 0), 0.0))
            if profit_delta > 0:
                self.tradingview_summary['win_trades'] = current_win_trades + 1
                self.tradingview_summary['lose_trades'] = current_lose_trades
            elif profit_delta < 0:
                self.tradingview_summary['win_trades'] = current_win_trades
                self.tradingview_summary['lose_trades'] = current_lose_trades + 1
            else:
                self.tradingview_summary['win_trades'] = current_win_trades
                self.tradingview_summary['lose_trades'] = current_lose_trades
        else:
            # 兼容旧版手工推送：如果上游已经给了累计总盈亏，仍然直接采用。
            if 'win_trades' in trade_data:
                self.tradingview_summary['win_trades'] = trade_data['win_trades']
            if 'lose_trades' in trade_data:
                self.tradingview_summary['lose_trades'] = trade_data['lose_trades']
            if 'total_profit' in trade_data:
                self.tradingview_summary['total_profit'] = trade_data['total_profit']
            if 'initial_funds' in trade_data:
                self.tradingview_summary['initial_funds'] = trade_data['initial_funds']

        self.tradingview_summary['total_profit_all'] = round(
            _to_float(self.tradingview_summary.get('total_profit', 0.0), 0.0)
            + _sum_tradingview_round_profit(self.tradingview_rounds),
            4,
        )

        self._apply_memory_limits()
        
        self.update_global_data()
        # 保存TradingView策略数据到本地文件
        save_tradingview_data({
            'trade_records': self.tradingview_data,
            'round_records': self.tradingview_rounds,
            'summary': self.tradingview_summary
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

        if len(existing_records) > MAX_LEAD_RECORDS:
            dropped_records = existing_records[MAX_LEAD_RECORDS:]
            archived_realized_pnl += sum(
                _to_float(record.get('order_pnl'), _extract_tradingview_profit_delta(record) or 0.0)
                for record in dropped_records
                if isinstance(record, dict)
            )
            del existing_records[MAX_LEAD_RECORDS:]

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
        """更新套利数据：只以唯一订单的 net_profit 作为总额计算来源。"""
        arbitrage_data_file = os.path.join(data_dir, 'arbitrage_trades.json')
        existing_data = {}
        if os.path.exists(arbitrage_data_file):
            try:
                with open(arbitrage_data_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"⚠️ 读取套利策略数据文件异常：{e}")

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

        # 初始资金优先使用本地已填写值，其次才使用请求中的值
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

        # 套利记录按最新优先保留尾部，同时将被裁剪部分利润归档，保证累计收益不丢失。
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
        if 'btc_price' in data:
            self.market_data['btc_price'] = data['btc_price']
        self.update_global_data()
        return True
    
    def update_top_bottom_data(self, data):
        if 'position_status' in data:
            self.top_bottom_data['position_status'] = data['position_status']
        if 'position_quantity' in data:
            self.top_bottom_data['position_quantity'] = data['position_quantity']
        if 'position_avg_price' in data:
            self.top_bottom_data['position_avg_price'] = data['position_avg_price']
        if 'position_symbol' in data:
            self.top_bottom_data['position_symbol'] = data['position_symbol']
        if 'trade_records' in data:
            self.top_bottom_data['trade_records'] = data['trade_records']
        self.update_global_data()
        return True
    
    def add_top_bottom_trade(self, trade_data):
        # 确保trade_data包含必要的字段
        required_fields = ['mode', 'quantity', 'avg_price', 'is_closed', 'profit']
        for field in required_fields:
            if field not in trade_data:
                return False
        
        # 添加时间戳
        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        
        # 如果已平仓，添加平仓时间戳
        if trade_data.get('is_closed'):
            trade_data['close_timestamp'] = trade_data.get('close_timestamp', datetime.now().strftime('%Y-%m-%d-%H:%M:%S'))
        
        # 插入到列表开头，实现时间从近到远显示
        self.top_bottom_data['trade_records'].insert(0, trade_data)
        _trim_list_inplace(self.top_bottom_data.get('trade_records'), MAX_TOP_BOTTOM_RECORDS, keep='head')
        
        self.update_global_data()
        return True
    
    def update_spot_data(self, data):
        if 'position_quantity' in data:
            self.spot_data['position_quantity'] = data['position_quantity']
        if 'position_avg_price' in data:
            self.spot_data['position_avg_price'] = data['position_avg_price']
        if 'position_symbol' in data:
            self.spot_data['position_symbol'] = data['position_symbol']
        if 'trade_records' in data:
            self.spot_data['trade_records'] = data['trade_records']
        self.update_global_data()
        return True
    
    def add_spot_trade(self, trade_data):
        # 确保trade_data包含必要的字段
        required_fields = ['quantity', 'avg_price', 'is_closed', 'profit']
        for field in required_fields:
            if field not in trade_data:
                return False
        
        # 添加时间戳
        trade_data['timestamp'] = datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
        
        # 如果已平仓，添加平仓时间戳
        if trade_data.get('is_closed'):
            trade_data['close_timestamp'] = trade_data.get('close_timestamp', datetime.now().strftime('%Y-%m-%d-%H:%M:%S'))
        
        # 插入到列表开头，实现时间从近到远显示
        self.spot_data['trade_records'].insert(0, trade_data)
        _trim_list_inplace(self.spot_data.get('trade_records'), MAX_SPOT_RECORDS, keep='head')
        
        self.update_global_data()
        return True
    
    def get_all_data(self):
        return {
            'tradingview': self.tradingview_data,
            'tradingview_rounds': self.tradingview_rounds,
            'tradingview_summary': self.tradingview_summary,
            'lead': self.lead_data,
            'arbitrage': self.arbitrage_data,
            'total_profit': self.total_profit_data,
            'top_bottom': self.top_bottom_data,
            'spot': self.spot_data,
            'strategy_status': self.strategy_status,
            'market_data': self.market_data,
            'arbitrage_start_time': self.arbitrage_start_time
        }

# 初始化数据存储
data_storage = DataStorage()

# 启动文件更新检查线程
file_update_thread = threading.Thread(target=check_file_updates, daemon=True)
file_update_thread.start()

# 启动获取BTC价格的线程
btc_price_thread = threading.Thread(target=fetch_btc_price, daemon=True)
btc_price_thread.start()

# WebSocket事件处理
@socketio.on('connect')
def handle_connect():
    # print('Client connected')
    socketio.emit('all_data', data_storage.get_all_data())

@socketio.on('disconnect')
def handle_disconnect():
    pass

# API端点
@app.route('/api/update_tradingview', methods=['POST'])
def update_tradingview_data():
    data = request.json
    if data:
        data_storage.add_tradingview_trade(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_lead', methods=['POST'])
def update_lead_data():
    data = request.json
    if data:
        data_storage.update_lead_data(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_arbitrage', methods=['POST'])
def update_arbitrage_data():
    data = request.json
    if data:
        data_storage.update_arbitrage_data(data)
        socketio.emit('all_data', data_storage.get_all_data())
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/get_data', methods=['GET'])
def get_data():
    return jsonify(data_storage.get_all_data())

@app.route('/api/update_strategy_status', methods=['POST'])
def update_strategy_status():
    data = request.json
    if data and 'strategy' in data and 'status' in data:
        success = data_storage.update_strategy_status(data['strategy'], data['status'])
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_market_data', methods=['POST'])
def update_market_data():
    data = request.json
    if data:
        success = data_storage.update_market_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_top_bottom', methods=['POST'])
def update_top_bottom_data():
    data = request.json
    if data:
        success = data_storage.update_top_bottom_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/add_top_bottom_trade', methods=['POST'])
def add_top_bottom_trade():
    data = request.json
    if data:
        success = data_storage.add_top_bottom_trade(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/update_spot', methods=['POST'])
def update_spot_data():
    data = request.json
    if data:
        success = data_storage.update_spot_data(data)
        if success:
            socketio.emit('all_data', data_storage.get_all_data())
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/add_spot_trade', methods=['POST'])
def add_spot_trade():
    data = request.json
    if data:
        success = data_storage.add_spot_trade(data)
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

# 为data目录添加静态文件路由
@app.route('/data/<path:filename>')
def serve_data_file(filename):
    return send_from_directory(data_dir, filename)

# 为static目录添加静态文件路由
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

            # 过滤含有控制字符的异常协议噪音行
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
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=False)
