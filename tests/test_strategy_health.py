# -*- coding: utf-8 -*-
"""策略健康页（/strategy_health）：Sentinel 快照只读渲染 + 登录门禁。"""
import json
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


def _snapshot(pair='btc.um.long', direction='long', status='yellow'):
    return {
        'schema_version': 'sentinel.snapshot.v1',
        'pair': pair,
        'mode': 'event',
        'generated_at': '2026-10-18T06:00:00+00:00',
        'health': {'status': status, 'recommendation': '观察：存在偏离迹象',
                   'reasons': ['long 观察项：开仓对齐'],
                   'suggested_commands': ['python3 ops/params_anchor.py check --pair btc.um.long']},
        'directions': {direction: {
            'overall_status': status,
            'gates': {'g0_order_diff': {'status': 'ok', 'evidence': []},
                      'g6_alignment': {'status': 'yellow', 'evidence': ['多单 1（实盘多出于回放）']}},
            'distribution_health': {'status': 'observe',
                                    'metrics': {'n_legs': 3, 'win_rate_pct': 66.67, 'profit_factor': 1.5,
                                                'legs_per_year': 12.0, 'max_losing_streak': 1},
                                    'sample': {'months': 0.5, 'adequate': False}},
            'params_guard': {'status': 'ok'},
            'alignment': {'pairs_n': 3, 'replay_missing_n': 0, 'live_extra_n': 1,
                          'latency_seconds': {'p90': 30}, 'price_bps': {'p95': 4.2}},
        }},
        'portfolio': {
            'status': 'observe', 'mode': 'observe', 'symbol': 'BTCUSDT',
            'mark_price': 80000.0, 'net_size': -0.01, 'gross_size': 0.03,
            'net_notional': -800.0, 'gross_notional': 2400.0,
            'combined_equity': 10000.0, 'net_ratio': -0.08, 'gross_ratio': 0.24,
            'legs': {'long': {'exchange_size': 0.02}, 'short': {'exchange_size': -0.03}},
            'reasons': ['mode=observe：超阈仅记录'],
        },
    }


def _login(client):
    client.post('/login', data={'username': 'admin', 'password': 'test123'})


def test_strategy_health_page_renders_snapshot(tmp_path, monkeypatch, client):
    snap = tmp_path / 'snap.json'
    snap.write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding='utf-8')
    monkeypatch.setenv('SENTINEL_SNAPSHOT_PATHS', str(snap))
    _login(client)
    resp = client.get('/strategy_health')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for marker in ('策略健康', 'btc.um.long', '开仓对齐', '参数一致性',
                   'params_anchor.py', '多单 1', '组合净敞口'):
        assert marker in html, f'缺少标记: {marker}'


def test_strategy_health_empty_state(tmp_path, monkeypatch, client):
    monkeypatch.setenv('SENTINEL_SNAPSHOT_PATHS', str(tmp_path / 'missing.json'))
    _login(client)
    resp = client.get('/strategy_health')
    assert resp.status_code == 200
    assert '暂无 Sentinel 快照' in resp.get_data(as_text=True)


def test_strategy_health_requires_login(client):
    resp = client.get('/strategy_health')
    assert resp.status_code in (301, 302)


def test_index_has_health_link(client):
    _login(client)
    html = client.get('/').get_data(as_text=True)
    assert '/strategy_health' in html
