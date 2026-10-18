# -*- coding: utf-8 -*-
"""策略模块实际账务（2026-10-18）：actual_* 归一化保留 / 回填 / 汇总口径（实际优先 + 基线偏移）。"""
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402


def _close_record(order_id='o1', account_id='binance.um', **overrides):
    record = {
        'order_id': order_id,
        'account_id': account_id,
        'account_label': 'um',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'quantity': 0.02,
        'price': 81000,
        'trade_type': '平仓',
        'action': 'close',
        'realized_pnl': 10.0,
        'gross_pnl': 11.2,
        'open_fee': 0.7,
        'close_fee': 0.5,
        'timestamp': '2026-10-18 09:00:00',
    }
    record.update(overrides)
    return record


def _total_profit_stub(baseline_days_ago=1):
    baseline_date = (datetime.now() - timedelta(days=baseline_days_ago)).strftime('%Y-%m-%d')
    return {
        'trade_records': [],
        'symbol_profit_tracker': {},
        'profit_curve_data': {
            'data_points': [
                {'date': '2025-03', 'principal': 10000, 'total_funds': 10000},
                {'date': baseline_date, 'principal': 12000, 'total_funds': 13000},
            ]
        },
    }


def test_normalize_preserves_actual_fields():
    record = web._normalize_lead_trade_record(_close_record(
        actual_net_pnl=9.25, actual_commission=0.55, actual_realized_pnl=9.8,
        actual_avg_price=81005.0, actual_fills=1, actual_source='binance_userTrades'))
    assert record['actual_net_pnl'] == pytest.approx(9.25)
    assert record['actual_commission'] == pytest.approx(0.55)
    assert record['actual_realized_pnl'] == pytest.approx(9.8)
    assert record['actual_avg_price'] == pytest.approx(81005.0)
    assert record['actual_source'] == 'binance_userTrades'


def test_summary_prefers_actual_and_applies_offset():
    records = [
        web._normalize_lead_trade_record(_close_record()),                      # 模型 10.0
        web._normalize_lead_trade_record(_close_record(
            order_id='o2', actual_net_pnl=-3.0, actual_commission=0.6,
            actual_realized_pnl=-2.4)),                                         # 实际 -3.0
    ]
    summary = web._build_lead_summary(records)
    assert summary['raw_total_realized_pnl'] == pytest.approx(7.0)
    assert summary['total_realized_pnl'] == pytest.approx(7.0)
    assert summary['actual_commission_total'] == pytest.approx(0.6)
    assert summary['actual_coverage'] == pytest.approx(0.5)

    offset_summary = web._build_lead_summary(records, pnl_offset=-7.0)
    assert offset_summary['total_realized_pnl'] == pytest.approx(0.0)          # 盈亏归零
    assert offset_summary['raw_total_realized_pnl'] == pytest.approx(7.0)      # 原始值留痕


def test_apply_lead_actuals_patches_record_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    storage = web.DataStorage()
    storage.lead_data = {'summary': {}, 'trade_records': []}
    storage.total_profit_data = _total_profit_stub()
    storage.update_lead_data({'trade_records': [_close_record()]})

    matched = storage.apply_lead_actuals({
        'order_id': 'o1', 'account_id': 'binance.um', 'commission_quote': 0.55,
        'realized_pnl': 9.8, 'actual_net_pnl': 9.25, 'filled_qty': 0.02,
        'avg_price': 81005.0, 'fills': 1, 'source': 'binance_userTrades',
    })
    assert matched == 1
    saved = json.loads((tmp_path / 'lead_trades.json').read_text(encoding='utf-8'))
    record = saved['trade_records'][0]
    assert record['actual_net_pnl'] == pytest.approx(9.25)
    assert record['actual_commission'] == pytest.approx(0.55)
    assert record['actual_source'] == 'binance_userTrades'
    assert saved['summary']['total_realized_pnl'] == pytest.approx(9.25)
    assert saved['summary']['actual_commission_total'] == pytest.approx(0.55)

    assert storage.apply_lead_actuals({'order_id': 'missing'}) == 0           # 未命中
    assert storage.apply_lead_actuals({}) == 0                                # 缺 order_id
