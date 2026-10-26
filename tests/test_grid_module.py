# -*- coding: utf-8 -*-
"""网格策略模块（GridBot 只读展示）测试：状态读取 / 新鲜度 / 浮盈 / 接口门禁 / 页面标记。"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv('WEB_LOGIN_USERNAME', 'admin')
    monkeypatch.setenv('WEB_LOGIN_PASSWORD', 'test123')
    monkeypatch.delenv('WEB_LOGIN_PASSWORD_SHA256', raising=False)
    web._login_failures.clear()
    yield
    web._login_failures.clear()


@pytest.fixture()
def client():
    web.app.config['TESTING'] = True
    with web.app.test_client() as test_client:
        yield test_client


def _login(client):
    client.post('/login', data={'username': 'admin', 'password': 'test123'})


def _write_state(tmp_path, monkeypatch, **overrides):
    state = {
        'symbol': 'BTCUSDC',
        'baseline': 81000.0,
        'grid_distance': 500.0,
        'order_qty': 0.004,
        'max_levels': 5,
        'paused': False,
        'started': True,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'lots': [],
        'active_buy': {'level': 2, 'price': 80000.0, 'order_id': 1},
        'last_buy_fill_ts': 0,
    }
    state.update(overrides)
    path = tmp_path / 'live_state.json'
    path.write_text(json.dumps(state), encoding='utf-8')
    monkeypatch.setattr(web, 'GRIDBOT_STATE_FILE', str(path))
    return path


def test_load_grid_state_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'GRIDBOT_STATE_FILE', str(tmp_path / 'missing.json'))
    view = web.load_grid_state()
    assert view['available'] is False
    assert view['status'] == '未启用'
    assert view['lots'] == []
    assert view['inventory'] == 0.0


def test_load_grid_state_paused(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch, paused=True)
    view = web.load_grid_state()
    assert view['available'] is True
    assert view['status'] == '已暂停'
    assert view['paused'] is True


def test_load_grid_state_stale(tmp_path, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    _write_state(tmp_path, monkeypatch, updated_at=old)
    view = web.load_grid_state()
    assert view['status'] == '数据过期'
    assert view['age_seconds'] is not None and view['age_seconds'] > 60


def test_load_grid_state_running_with_lots(tmp_path, monkeypatch):
    lots = [
        {'level': 1, 'entry': 80500.0, 'qty': 0.004, 'sell_order_id': 101},
        {'level': 2, 'entry': 80000.0, 'qty': 0.004, 'sell_order_id': 102},
    ]
    _write_state(tmp_path, monkeypatch, lots=lots)
    monkeypatch.setattr(web, '_grid_price', lambda timeout=5.0: 81000.0)

    view = web.load_grid_state()
    assert view['status'] == '运行中'
    assert view['lot_count'] == 2
    assert view['inventory'] == pytest.approx(0.008)
    # 默认止盈价 = 基准 - (层-1)*间距
    assert view['lots'][0]['tp'] == pytest.approx(81000.0)
    assert view['lots'][1]['tp'] == pytest.approx(80500.0)
    # 浮盈 = (81000-80500)*0.004 + (81000-80000)*0.004
    assert view['unrealized'] == pytest.approx(6.0)
    assert view['next_buy']['level'] == 2


def test_load_grid_state_without_price_has_no_unrealized(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch, lots=[{'level': 1, 'entry': 80500.0, 'qty': 0.004}])
    monkeypatch.setattr(web, '_grid_price', lambda timeout=5.0: None)
    view = web.load_grid_state()
    assert view['price'] is None
    assert view['unrealized'] is None


def test_load_grid_state_realized_profit(tmp_path, monkeypatch):
    """已套利盈利：GridBot 平仓累加的 realized_pnl / 轮数 / 毛费透出。"""
    _write_state(tmp_path, monkeypatch, realized_pnl=1.9139, realized_cycles=1,
                 realized_gross=2.0, realized_fees=0.0861)
    monkeypatch.setattr(web, '_grid_price', lambda timeout=5.0: 80000.0)
    view = web.load_grid_state()
    assert view['realized'] == pytest.approx(1.9139)
    assert view['cycles'] == 1
    assert view['realized_gross'] == pytest.approx(2.0)
    assert view['realized_fees'] == pytest.approx(0.0861)


def test_load_grid_state_last_realized_from_ledger(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch, realized_pnl=10.0, realized_cycles=5)
    ledger = tmp_path / 'realized.jsonl'
    ledger.write_text(json.dumps({
        'ts': '2026-10-26T14:19:30Z', 'level': 3, 'entry': 79500.0,
        'exit': 80000.0, 'qty': 0.004, 'gross': 2.0, 'fee': 0.0,
        'net': 2.0, 'closes': True, 'realized_total': 10.0,
    }) + '\n', encoding='utf-8')
    view = web.load_grid_state()
    assert view['last_realized']['level'] == 3
    assert view['last_realized']['exit'] == pytest.approx(80000.0)
    assert view['last_realized']['net'] == pytest.approx(2.0)
    assert view['last_realized']['ts'] == '10-26 22:19'


def test_load_grid_state_warning_fields(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch, paused=True, rearm_pending=True,
                 position_shortfall=2)
    view = web.load_grid_state()
    assert view['paused'] is True
    assert view['rearm_pending'] is True
    assert view['position_shortfall'] == 2
    assert '已暂停' in view['warning']
    assert '待补挂' in view['warning']
    assert '成交未覆盖持仓' in view['warning']


def test_load_grid_state_realized_missing_is_none(tmp_path, monkeypatch):
    """旧 state 没有 realized 字段 → None（页面显示 —，不谎报 0）；损坏值也按 None 处理。"""
    _write_state(tmp_path, monkeypatch)
    monkeypatch.setattr(web, '_grid_price', lambda timeout=5.0: 80000.0)
    view = web.load_grid_state()
    assert view['realized'] is None
    assert view['cycles'] == 0

    _write_state(tmp_path, monkeypatch, realized_pnl='not-a-number', realized_cycles='x')
    view = web.load_grid_state()
    assert view['realized'] is None
    assert view['cycles'] == 0


def test_grid_api_requires_login(client):
    response = client.get('/api/grid_status')
    assert response.status_code == 401
    assert response.get_json()['status'] == 'error'


def test_grid_api_returns_view_when_logged_in(client, tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch)
    monkeypatch.setattr(web, '_grid_price', lambda timeout=5.0: 81000.0)
    _login(client)
    response = client.get('/api/grid_status')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['available'] is True
    assert payload['symbol'] == 'BTCUSDC'
    assert payload['price'] == pytest.approx(81000.0)


def test_index_contains_grid_section(client, tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch)
    monkeypatch.setattr(web, '_grid_price', lambda timeout=5.0: 81000.0)
    _login(client)
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="grid-section"' in html
    assert '网格策略' in html
    assert 'id="grid-lots-body"' in html
    assert 'id="grid-realized"' in html
    assert 'id="grid-warning"' in html
    assert 'id="grid-last-realized"' in html
    assert 'id="grid-next-buy-id"' in html
    assert '已套利盈利' in html
    assert '/api/grid_status' in html
