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
                      'g1_single_leg': {'status': 'ok', 'evidence': []},
                      'g5_params_guard': {'status': 'yellow',
                                          'evidence': ['code_commit: anchor=cb623830eb current=bed37c2044']},
                      'g6_alignment': {'status': 'yellow', 'evidence': ['多单 1（实盘多出于回放）']}},
            'params_guard': {'status': 'yellow',
                             'checks': [{'name': 'params_sha256', 'ok': True,
                                         'detail': 'anchor=abc123… current=abc123…'},
                                        {'name': 'code_commit', 'ok': False,
                                         'detail': 'anchor=cb623830eb current=bed37c2044'},
                                        {'name': 'data_sha256', 'ok': False,
                                         'detail': 'anchor=f0c77797e4db… current=081c4b2c6161…'}]},
            'alignment_gate': {'status': 'yellow', 'evidence': ['多单 1（实盘多出于回放）'],
                               'metrics': {'pairs_n': 3, 'live_extra_n': 1, 'replay_missing_n': 0,
                                           'latency_p90_seconds': 30, 'latency_max_seconds': 45,
                                           'price_bps_p95': 4.2, 'price_bps_max': 6.0,
                                           'bar_minutes': 240}},
            'distribution_health': {'status': 'observe',
                                    'sample': {'n_legs': 3, 'months': 0.5, 'adequate': False,
                                               'min_legs': 10, 'min_months': 1.0},
                                    'metrics': {'n_legs': 3, 'months': 0.5, 'win_rate_pct': 66.67,
                                                'profit_factor': 1.5, 'legs_per_year': 12.0,
                                                'max_losing_streak': 1, 'median_holding_days': 2.1},
                                    'checks': [],
                                    'evidence': ['样本不足（腿数 3 < 10 且时长 0.50 月 < 1.0），降级 observe']},
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


def _observe_snapshot(pair='btc.um.long', direction='long'):
    """早期观察态（当前真实形态）：锚一致 / 无配对样本 / 无腿样本。"""
    return {
        'schema_version': 'sentinel.snapshot.v1',
        'pair': pair,
        'mode': 'event',
        'generated_at': '2026-10-18T06:00:00+00:00',
        'health': {'status': 'observe',
                   'recommendation': '观察（样本积累中）：参数与开仓对齐正常；分布判定待实盘腿样本达门槛后生效。',
                   'reasons': ['long 样本不足（腿数 0 / 时长 0 月），继续观察'],
                   'suggested_commands': []},
        'directions': {direction: {
            'overall_status': 'observe',
            'gates': {name: {'status': 'observe',
                             'evidence': ['窗口内无实盘数据（自 live 起点以来无订单）']}
                      for name in ('g0_order_diff', 'g1_single_leg', 'g2_streak_and_gap',
                                   'g3_cumulative_band', 'g4_float_and_drawdown')},
            'params_guard': {'status': 'ok',
                             'checks': [{'name': 'params_sha256', 'ok': True,
                                         'detail': 'anchor=x current=x'}]},
            'alignment_gate': {'status': 'observe', 'evidence': [],
                               'metrics': {'pairs_n': 0, 'live_extra_n': 0, 'replay_missing_n': 0,
                                           'latency_p90_seconds': None, 'price_bps_p95': None}},
            'distribution_health': {'status': 'observe',
                                    'sample': {'n_legs': 0, 'months': 0.0, 'adequate': False,
                                               'min_legs': 10, 'min_months': 1.0},
                                    'metrics': {'n_legs': 0, 'months': 0.0, 'win_rate_pct': None,
                                                'profit_factor': None, 'legs_per_year': None,
                                                'max_losing_streak': 0, 'median_holding_days': None},
                                    'checks': [],
                                    'evidence': ['样本不足（腿数 0 < 10 且时长 0.00 月 < 1.0），降级 observe']},
        }},
        'portfolio': {
            'status': 'observe', 'mode': 'observe', 'symbol': 'BTCUSDT',
            'mark_price': 80000.0, 'net_size': 0.0, 'gross_size': 0.0,
            'net_notional': 0.0, 'gross_notional': 0.0,
            'combined_equity': 10000.0, 'net_ratio': 0.0, 'gross_ratio': 0.0,
            'legs': {'long': {'exchange_size': 0.0}, 'short': {'exchange_size': 0.0}},
            'reasons': [],
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
    for marker in ('策略健康', 'btc.um.long', '参数一致性', '开仓对齐', '分布健康',
                   '引擎版本变化：锚 cb623830eb → 现 bed37c2044',
                   '数据文件变化：锚 f0c77797e4db… → 现 081c4b2c6161…',
                   '配对 3', '漏单 0', '多单 1',
                   '延迟 p90 30s', '偏差 p95 4.2bps',
                   '3/10 腿 · 0.50/1 月', '样本积累中',
                   '组合净敞口', '其他闸门', '全部正常', 'status-bg-yellow',
                   '快照 10-18 14:00', '多单 1（实盘多出于回放）',
                   'health-donut', 'health-gate-matrix', 'gate-cell',
                   'exposure-row', 'align-bars', 'health-ring'):
        assert marker in html, f'缺少标记: {marker}'
    assert 'None' not in html


def test_strategy_health_observe_state_no_noise(tmp_path, monkeypatch, client):
    """早期观察态：无配对样本/样本积累中；不出现 None 或占位符噪音。"""
    snap = tmp_path / 'snap.json'
    snap.write_text(json.dumps(_observe_snapshot(), ensure_ascii=False), encoding='utf-8')
    monkeypatch.setenv('SENTINEL_SNAPSHOT_PATHS', str(snap))
    _login(client)
    html = client.get('/strategy_health').get_data(as_text=True)
    for marker in ('暂无配对样本', '样本积累中', '0/10 腿 · 0.00/1 月',
                   '锚与生效参数一致', '未判定 5 项（暂无实盘数据，不作判定）'):
        assert marker in html, f'缺少标记: {marker}'
    assert '全部正常' not in html
    assert 'None' not in html
    assert '延迟 p90' not in html


def test_strategy_health_empty_state(tmp_path, monkeypatch, client):
    monkeypatch.setenv('SENTINEL_SNAPSHOT_PATHS', str(tmp_path / 'missing.json'))
    _login(client)
    resp = client.get('/strategy_health')
    assert resp.status_code == 200
    assert '暂无 Sentinel 快照' in resp.get_data(as_text=True)


def test_strategy_health_requires_login(client):
    resp = client.get('/strategy_health')
    assert resp.status_code in (301, 302)


def test_index_has_health_in_lead_section(tmp_path, monkeypatch, client):
    """策略健康并入「策略模块」区块（同区切换；中央切换器保持 帖子/盈亏/资产 三标签）。"""
    snap = tmp_path / 'snap.json'
    snap.write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding='utf-8')
    monkeypatch.setenv('SENTINEL_SNAPSHOT_PATHS', str(snap))
    _login(client)
    html = client.get('/').get_data(as_text=True)
    for marker in ('data-lead-view="module"', 'data-lead-view="health"',
                   'id="lead-module-view"', 'id="lead-health-view"',
                   'btc.um.long', '组合净敞口',
                   "get('view') === 'health'"):
        assert marker in html, f'缺少标记: {marker}'
    assert 'href="/strategy_health"' not in html
    assert html.count('data-performance-view=') == 3
