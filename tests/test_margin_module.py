# -*- coding: utf-8 -*-
"""仓位健康（保证金监控只读）模块测试：状态投影 / 新鲜度 / 接口门禁 / 页面标记。"""
import json
import os
import sys
import time
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


REPORT = {
    'ts': '2026-11-16T00:00:00Z',
    'metrics': {
        'btc_price': 64780.1, 'equity': 70928.12, 'available': 61528.51,
        'futures_notional': 25214.81, 'futures_leverage': 0.3555,
        'gross_leverage': 1.4624, 'equity_beta': 1.404,
        'margin_ratio_pct': 0.1632, 'maintenance_margin': 115.75,
        'mm_source': 'tiered', 'liquidation_price_estimate': 18680.0,
        'liquidation_distance_pct': 71.16, 'btc_collateral': 1.20952525,
        'net_btc_delta': 1.59832525,
        'positions': [
            {'symbol': 'BTCUSD1', 'side': 'LONG', 'qty': 0.2263,
             'entry': 72934.44, 'mark': 64823.0, 'notional': 14669.44,
             'unrealized_pnl': -1835.62, 'leverage': 2.0},
            {'symbol': 'BTCUSDC', 'side': 'LONG', 'qty': 0.168,
             'entry': 70541.85, 'mark': 64745.1, 'notional': 10877.18,
             'unrealized_pnl': -973.85, 'leverage': 5.0},
        ],
    },
    'risk': {'level': 'watch', 'reasons': ['F&G=10 极度恐慌'], 'price_levels_hit': []},
    'stress': [
        {'price': 64780.1, 'is_current': True, 'equity': 70928.0,
         'margin_ratio_pct': 0.16, 'liquidation_distance_pct': 71.2,
         'position_pnl': {'BTCUSD1': -1835.0, 'BTCUSDC': -974.0}},
        {'price': 40000.0, 'is_current': False, 'equity': 32000.0,
         'margin_ratio_pct': 0.22, 'liquidation_distance_pct': 53.0,
         'position_pnl': {'BTCUSD1': -7450.0, 'BTCUSDC': -5130.0}},
    ],
    'stress_ahr_filled': [
        {'price': 40000.0, 'is_current': False, 'equity': 30000.0,
         'margin_ratio_pct': 0.3, 'liquidation_distance_pct': 45.0,
         'position_pnl': {}},
    ],
    'attribution': {
        'ahr999': {'name': 'ahr999', 'symbols': ['BTCUSD1'], 'qty': 0.2263,
                   'notional': 14669.44, 'unrealized_pnl': -1835.62,
                   'margin_est': 7334.72, 'beta_contribution': 0.2068,
                   'breaches': [], 'budget': {'max_notional': 40000}},
        'spot': {'name': 'spot', 'symbols': ['BTC'], 'qty': 1.20952525,
                 'notional': 78352.0, 'unrealized_pnl': 0.0, 'margin_est': 0.0,
                 'beta_contribution': 1.1047, 'breaches': [], 'budget': {}},
    },
    'sentiment': {'value': 10, 'classification': 'Fear',
                  'throttle': {'factor': 0.5, 'reason': 'F&G 10 ≤ 10'}},
    'income': {'funding_7d': -1.5, 'interest_7d': 0.0, 'commission_7d': -3.2},
    'trend': {'window_days': 7, 'beta_change': 0.2, 'margin_ratio_change': 0.05,
              'liq_distance_change': -5.0, 'price_change_pct': -3.2},
    'var': {'n': 999, 'var95_pct': 5.0, 'cvar95_pct': 7.0},
    'episodes': [{'date': '2020-03-12', 'return_pct': -39.5}],
    'recommendations': ['F&G=10 极度恐慌；建议 AHR 节流 0.50x（仅建议）'],
}


def _write_state(tmp_path, monkeypatch, report=None, *, state_ts=None,
                 heartbeat_ts=None, raw=None):
    state = {
        'last_level': (report or {}).get('risk', {}).get('level', 'ok'),
        'last_success_ts': time.time() if state_ts is None else state_ts,
        'last_report': REPORT if report is None else report,
    }
    path = tmp_path / 'margin_monitor.json'
    path.write_text(raw if raw is not None else json.dumps(state), encoding='utf-8')
    heartbeat = tmp_path / 'margin_monitor.heartbeat'
    heartbeat.write_text(json.dumps({
        'ts': datetime.now(timezone.utc).isoformat() if heartbeat_ts is None else heartbeat_ts,
        'pid': 1, 'level': 'watch',
    }), encoding='utf-8')
    monkeypatch.setattr(web, 'MARGIN_STATE_FILE', str(path))
    monkeypatch.setattr(web, 'MARGIN_HEARTBEAT_FILE', str(heartbeat))
    return path


def test_load_margin_state_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'MARGIN_STATE_FILE', str(tmp_path / 'missing.json'))
    monkeypatch.setattr(web, 'MARGIN_HEARTBEAT_FILE', str(tmp_path / 'missing.hb'))
    view = web.load_margin_state()
    assert view['available'] is False
    assert view['status_label'] == '无数据'
    assert view['positions'] == []


def test_load_margin_state_projects_report(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch)
    view = web.load_margin_state()
    assert view['available'] is True
    assert view['stale'] is False
    assert view['status'] == 'watch'
    assert view['status_label'] == '关注'
    assert view['equity'] == pytest.approx(70928.12)
    assert view['liquidation_price'] == pytest.approx(18680.0)
    assert view['positions'][0]['symbol'] == 'BTCUSD1'
    assert view['stress'][1]['price'] == pytest.approx(40000.0)
    assert view['stress_ahr_filled'][0]['margin_ratio_pct'] == pytest.approx(0.3)
    assert [item['name'] for item in view['attribution']] == ['spot', 'ahr999']
    assert view['sentiment']['throttle']['factor'] == pytest.approx(0.5)
    assert view['trend']['beta_change'] == pytest.approx(0.2)
    assert view['reasons'] == ['F&G=10 极度恐慌']
    assert view['recommendations']


def test_load_margin_state_stale_when_old(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch,
                 state_ts=time.time() - 900,
                 heartbeat_ts=(datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat())
    view = web.load_margin_state()
    assert view['available'] is True
    assert view['stale'] is True
    assert view['status_label'].startswith('关注')


def test_load_margin_state_corrupt_file(tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch, raw='{not json')
    view = web.load_margin_state()
    assert view['available'] is False


def test_margin_status_api_requires_login(client):
    response = client.get('/api/margin_status')
    assert response.status_code in (302, 401)


def test_margin_status_api_returns_state(client, tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch)
    _login(client)
    response = client.get('/api/margin_status')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['available'] is True
    assert payload['status'] == 'watch'
    assert payload['equity_beta'] == pytest.approx(1.404)


def test_index_contains_margin_section(client, tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch)
    _login(client)
    html = client.get('/').get_data(as_text=True)
    assert '仓位健康' in html
    assert '/api/margin_status' in html
    assert 'AHR999 剩余全部加仓后的压力表' in html


def test_load_margin_state_uses_tiered_mm_when_available(tmp_path, monkeypatch):
    report = json.loads(json.dumps(REPORT))
    report['metrics'].update({'mm_source': 'tiered',
                              'maintenance_margin': 115.75,
                              'maintenance_margin_tiered': 118.2})
    _write_state(tmp_path, monkeypatch, report)
    view = web.load_margin_state()
    assert view['maintenance_margin'] == pytest.approx(118.2)
    assert view['maintenance_margin_account'] == pytest.approx(115.75)
    assert view['maintenance_margin_tiered'] == pytest.approx(118.2)


def test_load_margin_state_tolerates_list_attribution(tmp_path, monkeypatch):
    report = json.loads(json.dumps(REPORT))
    report['attribution'] = [{'name': 'ahr999', 'notional': 1000}]
    _write_state(tmp_path, monkeypatch, report)
    view = web.load_margin_state()
    assert view['available'] is True
    assert view['attribution'][0]['name'] == 'ahr999'


def test_index_stale_badge_is_gray(client, tmp_path, monkeypatch):
    _write_state(tmp_path, monkeypatch,
                 state_ts=time.time() - 900,
                 heartbeat_ts=(datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat())
    _login(client)
    html = client.get('/').get_data(as_text=True)
    assert 'bg-gray-200 text-gray-600' in html
    assert '数据过期' in html
