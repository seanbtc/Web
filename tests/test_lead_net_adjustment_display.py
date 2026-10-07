"""带单记录净头寸调整展示派生：开多仓/开空仓 + 历史 reason 兜底。"""
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


def test_new_record_uses_attribution_display():
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': '1155109993906',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.187,
        'price': 85220.3,
        'trade_type': '开仓',
        'net_adjustment': True,
        'attribution': {
            'leg': 'long',
            'action': 'open',
            'quantity': 0.187,
            'label': '多头开仓',
            'net_position_before': -0.197,
            'net_position_after': -0.010,
        },
        'alert_message': '多头开仓（净头寸调整） | 触发: 双向信号净头寸调整 | 净头寸 空 0.197→空 0.010 | 结果: 亏损',
        'timestamp': '2026-10-06 00:00:03',
    })
    assert record['trade_type'] == '开仓'
    assert record['net_adjustment'] is True
    assert record['display_trade_type'] == '开多仓'
    assert record['display_direction'] == '多头'
    assert '净头寸调整' in record['display_note']
    assert '多头开仓 0.187' in record['display_note']
    assert '净头寸 空 0.197→空 0.01' in record['display_note']


def test_new_record_short_leg_add_uses_add_display():
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': 'x-1',
        'symbol': 'BTCUSDT.P',
        'side': 'SELL',
        'quantity': 0.05,
        'price': 90000.0,
        'trade_type': '加仓',
        'net_adjustment': True,
        'attribution': {'leg': 'short', 'action': 'add', 'quantity': 0.05},
        'alert_message': '空头加仓（净头寸调整）',
    })
    assert record['display_trade_type'] == '加空仓'
    assert record['display_direction'] == '空头'


def test_legacy_record_derived_from_reason():
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': 'old-1',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.187,
        'price': 85220.3,
        'trade_type': '平仓',
        'reason': (
            '空头平仓 | 触发: 双向信号净头寸调整 '
            'virtual_short=0.197000 virtual_long=0.187000 net=-0.010000 | 结果: 亏损'
        ),
        'realized_pnl': -762.8,
        'timestamp': '2026-10-06 00:00:03',
    })
    # 配对口径不变（trade_type 保持原值），仅展示派生
    assert record['trade_type'] == '平仓'
    assert record['net_adjustment'] is True
    assert record['display_trade_type'] == '开多仓'
    assert record['display_direction'] == '多头'


def test_plain_close_record_unchanged():
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': 'old-2',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 2.0,
        'price': 100.0,
        'trade_type': '平仓',
        'reason': '空头平仓 | 触发: 止损',
    })
    assert record['net_adjustment'] is False
    assert record['display_trade_type'] == '平仓'
    assert record['display_direction'] == ''
    assert record['display_note'] == ''


def test_template_uses_display_fields():
    template_path = os.path.join(WEB_DIR, 'templates', 'index.html')
    with open(template_path, encoding='utf-8') as handle:
        html = handle.read()
    assert 'trade.display_trade_type || trade.trade_type' in html
    assert 'isNetAdjustment ? null' in html
    assert 'trade.display_note || trade.reason' in html
