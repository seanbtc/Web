# -*- coding: utf-8 -*-
"""摸顶摸底策略：标题、做多/做空方向标志、盈亏计算适配（页面/JS 标记）。"""
import os
import sys

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture()
def client():
    web.app.config['TESTING'] = True
    with web.app.test_client() as test_client:
        yield test_client


def _login(client):
    client.post('/login', data={'username': 'admin', 'password': 'test123'})


def test_top_module_renamed_and_position_side_marker(client):
    web.app.config['TESTING'] = True
    _login(client)
    html = client.get('/').get_data(as_text=True)
    assert '摸顶摸底策略' in html
    assert 'id="top-position-side"' in html
    assert 'id="top-total-profit"' in html
    assert 'id="top-float-profit"' in html


def test_top_js_supports_long_short_direction_and_profit_fallback(client):
    web.app.config['TESTING'] = True
    _login(client)
    html = client.get('/').get_data(as_text=True)
    for marker in ('resolvePositionDirection', 'resolveTradeDirection',
                   'calculateRecordProfit', 'position_side'):
        assert marker in html, f'缺少 JS 标记: {marker}'


def test_add_top_bottom_trade_appends_and_dedupes(client, monkeypatch):
    """AutoDCA 同步记录：append-only，按 source+plan_id+cycle 去重。"""
    import copy
    original = copy.deepcopy(web.data_storage.bottom_data)
    saved = []
    monkeypatch.setattr(web, 'save_bottom_data', lambda data: saved.append(True))
    monkeypatch.setattr(web.data_storage, 'update_global_data', lambda: None)
    try:
        payload = {
            'source': 'ahr999_dca', 'plan_id': 'ahr999_bottom_btcusd1', 'cycle_id': 3,
            'symbol': 'BTCUSD1', 'side': 'BUY', 'mode': '定投开仓',
            'quantity': 0.024, 'avg_price': 80000, 'is_closed': False, 'profit': 0,
        }
        resp = client.post('/api/add_top_bottom_trade', json=payload)
        assert resp.status_code == 200
        assert resp.get_json()['added'] is True
        records = web.data_storage.bottom_data['trade_records']
        assert any(r.get('source') == 'ahr999_dca' and r.get('cycle_id') == 3 for r in records)

        resp2 = client.post('/api/add_top_bottom_trade', json=payload)
        assert resp2.get_json()['added'] is False       # 去重
    finally:
        web.data_storage.bottom_data = original


def test_add_top_bottom_trade_allowed_without_login(client, monkeypatch):
    """AutoDCA 无登录态：写接口走 token 鉴权，不被登录门禁拦（2026-11-05）。"""
    import copy
    original = copy.deepcopy(web.data_storage.bottom_data)
    monkeypatch.setattr(web, 'save_bottom_data', lambda data: None)
    monkeypatch.setattr(web.data_storage, 'update_global_data', lambda: None)
    try:
        resp = client.post('/api/add_top_bottom_trade', json={
            'source': 'ahr999_dca', 'plan_id': 'p1', 'cycle_id': 1,
            'quantity': 0.01, 'avg_price': 80000, 'is_closed': False,
        })
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'success'
    finally:
        web.data_storage.bottom_data = original
