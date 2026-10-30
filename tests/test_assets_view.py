# -*- coding: utf-8 -*-
"""资产视图（帖子/盈亏/资产 三视图）测试：页面标记 / 数据载荷 / 切换逻辑。"""
import os
import sys

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


def test_index_has_assets_view_markup(client):
    _login(client)
    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for marker in ('data-performance-view="assets"', 'performance-assets-view',
                   'asset-spot-value', 'asset-lead-fee', 'asset-lead-realized',
                   '抄底现货资产', '策略模块资产',
                   'asset-top-asset', '摸顶摸底策略资产',
                   'updateTopAssetCard',
                   'assetCompositionChart', 'asset-composition-legend',
                   'asset-total-value', 'updateAssetCompositionChart'):
        assert marker in html, f'页面缺少标记: {marker}'
    assert html.count('data-performance-view=') == 3
    assert html.count('class="asset-card"') == 4
    assert 'is-assets' in html and 'updateAssetsView' in html
    # 2026-10-20：抄底/摸顶资产卡去掉「持仓均价」小卡与整块交易记录表（与策略模块重复）
    assert 'asset-spot-avg' not in html
    assert 'asset-top-avg' not in html
    assert 'asset-spot-records' not in html
    assert 'asset-top-records' not in html
    assert 'renderAssetRecords' not in html
    assert '<th>数量</th><th>状态</th><th>平仓均价</th><th>盈亏</th>' not in html


def test_get_data_payload_contains_assets_sources(client):
    _login(client)
    resp = client.get('/api/get_data')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert 'bottom' in payload and 'lead' in payload
    bottom = payload['bottom'] or {}
    assert 'position_quantity' in bottom and 'trade_records' in bottom
    lead = payload['lead'] or {}
    assert isinstance(lead.get('summary'), dict)


def test_unauthenticated_index_redirects(client):
    resp = client.get('/')
    assert resp.status_code == 302
