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
