"""带单记录净头寸调整：单侧语义展示 + 回放账务修正 + total_profit 自动更新。

真实 payload 依据 2026-10-08 实盘 btc.lead 两笔（平空 0.01@83281.9 / 开多 0.173@83281.9）构造；
含 BStrategy 同批新增单侧字段（leg_direction/leg_action/leg_reason/mechanism/mechanism_label），
并覆盖字段缺失时的历史旧记录回退口径。
"""
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

TOOLS_DIR = os.path.join(WEB_DIR, 'tools')
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import backfill_legacy_decision as backfill_tool  # noqa: E402


def _timestamp_at(offset_days=0, hour=8, minute=0, second=5):
    moment = datetime.now() + timedelta(days=offset_days)
    return moment.strftime(f'%Y-%m-%d {hour:02d}:{minute:02d}:{second:02d}')


def _raw_close_record(**overrides):
    """记录 A：执行平空 0.01@83281.9（净头寸调整），含 BStrategy 同批新增单侧字段。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': 'today-a',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.01,
        'price': 83281.9,
        'trade_type': '开仓',
        'execution_trade_type': '平仓',
        'execution_action': 'close',
        'net_adjustment': True,
        'attribution': {},
        'leg_direction': 'short',
        'leg_action': 'close',
        'leg_reason': '信号平仓',
        'mechanism': 'net_position_alignment',
        'mechanism_label': '净头寸调整执行',
        'reason': '双向信号净头寸调整',
        'realized_pnl': -21.9545,
        'gross_pnl': -21.379,
        'timestamp': _timestamp_at(0, 8, 0, 5),
        'display_trade_type': '开多仓',
        'display_direction': '多头',
        'display_note': '净头寸调整',
    }
    record.update(overrides)
    return record


def _raw_open_long_record(**overrides):
    """记录 B：执行开多 0.173@83281.9（净调开仓），含 BStrategy 同批新增单侧字段。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': 'today-b',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.173,
        'price': 83281.9,
        'trade_type': '开仓',
        'execution_trade_type': '开仓',
        'execution_action': 'open',
        'net_adjustment': True,
        'attribution': {
            'leg': 'long',
            'action': 'open',
            'quantity': 0.173,
            'label': '多头开仓',
            'net_position_before': -0.01,
            'net_position_after': 0.163,
        },
        'leg_direction': 'long',
        'leg_action': 'open',
        'leg_reason': '信号开仓',
        'mechanism': 'net_position_alignment',
        'mechanism_label': '净头寸调整执行',
        'reason': '双向信号净头寸调整',
        'timestamp': _timestamp_at(0, 8, 0, 6),
    }
    record.update(overrides)
    return record


LEGACY_LEG_FIELD_KEYS = ('leg_direction', 'leg_action', 'leg_reason', 'mechanism', 'mechanism_label')


def _without_leg_fields(record):
    """剔除 BStrategy 新增单侧字段，模拟历史旧记录 payload。"""
    legacy = dict(record)
    for key in LEGACY_LEG_FIELD_KEYS:
        legacy.pop(key, None)
    return legacy


def _raw_short_open_record(**overrides):
    """更早的虚拟空头开仓 0.01@81144，供回放重建平空成本。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': 'old-short-1',
        'symbol': 'BTCUSDT.P',
        'side': 'SELL',
        'quantity': 0.01,
        'price': 81144.0,
        'trade_type': '开仓',
        'reason': '开仓',
        'timestamp': _timestamp_at(-2, 12, 0, 0),
    }
    record.update(overrides)
    return record


def _normalized(records):
    normalized = [web._normalize_lead_trade_record(record) for record in records]
    web._replay_trade_records_with_pnl(normalized)
    return normalized


def _bucket_of(records, account='binance.lead', symbol='BTCUSDT.P'):
    buckets = web._replay_trade_records_with_pnl(records)
    return buckets[f'{account}:{symbol}']


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


def _month_baseline_stub():
    """月末结算基线（真实 data/total_profit.json 的 2026-08 点）。"""
    return {
        'trade_records': [],
        'symbol_profit_tracker': {},
        'profit_curve_data': {
            'data_points': [
                {'date': '2025-03', 'principal': 10000, 'total_funds': 10000},
                {'date': '2026-08', 'principal': 42486, 'total_funds': 54500},
            ]
        },
    }


def _close_record_at(timestamp, realized_pnl, order_id):
    return web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': order_id,
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.01,
        'price': 83281.9,
        'trade_type': '平仓',
        'realized_pnl': realized_pnl,
        'reason': '空头平仓 | 触发: 手动平仓',
        'timestamp': timestamp,
    })


def _raw_legacy_1006_record(**overrides):
    """10-06 00:00:03 服务器真实记录（旧 payload，无 leg_*/execution_*；order 1155109993906）。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': '1155109993906',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.187,
        'price': 85220.3,
        'trade_type': '平仓',
        'reason': (
            '空头平仓 | 触发: 双向信号净头寸调整 '
            'virtual_short=0.197000 virtual_long=0.187000 net=-0.010000 | 结果: 亏损'
        ),
        'realized_pnl': -762.29,
        'timestamp': '2026-10-06 00:00:03',
    }
    record.update(overrides)
    return record


def _backfilled_1006_record(**overrides):
    """回填工具产物：仅补决策腿三字段，其余保持。"""
    record = _raw_legacy_1006_record(
        decision_leg_direction='long',
        decision_leg_action='open',
        net_adjustment=True,
    )
    record.update(overrides)
    return record


def _live_0921_short_open():
    """现网记录 1：2026-09-21 08:00:05 空头开仓 0.197@81143.9（订单 1141560706678）。"""
    return {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': '1141560706678',
        'symbol': 'BTCUSDT.P',
        'side': 'SELL',
        'quantity': 0.197,
        'price': 81143.9,
        'trade_type': '开仓',
        'reason': '开仓',
        'timestamp': '2026-09-21 08:00:05',
    }


def _live_1008_close_short(**overrides):
    """现网记录 3：2026-10-08 08:00:05 平空 0.01@83281.9（空头腿自身离场）。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': '1144960000001',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.01,
        'price': 83281.9,
        'trade_type': '开仓',
        'execution_trade_type': '平仓',
        'execution_action': 'close',
        'net_adjustment': True,
        'leg_direction': 'short',
        'leg_action': 'close',
        'leg_reason': '信号平仓',
        'mechanism': 'net_position_alignment',
        'mechanism_label': '净头寸调整执行',
        'decision_leg_direction': 'short',
        'decision_leg_action': 'close',
        'reason': '双向信号净头寸调整',
        'realized_pnl': -21.379,
        'timestamp': '2026-10-08 08:00:05',
    }
    record.update(overrides)
    return record


def _live_1008_open_long(**overrides):
    """现网记录 4：2026-10-08 08:00:06 多头腿开仓 0.173@83281.9（净调执行）。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': '1144960000002',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.173,
        'price': 83281.9,
        'trade_type': '开仓',
        'execution_trade_type': '开仓',
        'execution_action': 'open',
        'net_adjustment': True,
        'leg_direction': 'long',
        'leg_action': 'open',
        'leg_reason': '信号开仓',
        'mechanism': 'net_position_alignment',
        'mechanism_label': '净头寸调整执行',
        'decision_leg_direction': 'long',
        'decision_leg_action': 'open',
        'reason': '双向信号净头寸调整',
        'timestamp': '2026-10-08 08:00:06',
    }
    record.update(overrides)
    return record


def _live_1008_add_long(**overrides):
    """现网记录 5：2026-10-08 12:00:05 多头加仓（决策腿 long/add）。"""
    record = {
        'account_id': 'binance.lead',
        'account_label': 'binance.lead',
        'order_id': '1144960000003',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 0.05,
        'price': 84000.0,
        'trade_type': '加仓',
        'execution_trade_type': '加仓',
        'execution_action': 'add',
        'decision_leg_direction': 'long',
        'decision_leg_action': 'add',
        'timestamp': '2026-10-08 12:00:05',
    }
    record.update(overrides)
    return record


def _live_five_records():
    """现网五条记录（09-21 空头开仓 / 10-06 决策腿多头开仓 / 10-08 平空 / 10-08 开多 / 12:00 加多）。"""
    return [
        _live_0921_short_open(),
        _backfilled_1006_record(realized_pnl=-762.2868),
        _live_1008_close_short(),
        _live_1008_open_long(),
        _live_1008_add_long(),
    ]


def _finalized(records):
    normalized = [web._normalize_lead_trade_record(record) for record in records]
    web._finalize_lead_records(normalized)
    return normalized


def _buy_close_with_decision(timestamp, realized_pnl, direction, action, order_id):
    return _raw_close_record(
        order_id=order_id,
        timestamp=timestamp,
        realized_pnl=realized_pnl,
        gross_pnl=realized_pnl,
        decision_leg_direction=direction,
        decision_leg_action=action,
    )


# ---------------------------------------------------------------------------
# display 派生矩阵（close/open/add、多/空、新单侧字段有无）
# ---------------------------------------------------------------------------

def test_execution_close_buy_displays_ping_kong_with_pnl():
    record = web._normalize_lead_trade_record(_raw_close_record())
    # 配对口径不变（trade_type 保持原值），仅展示派生
    assert record['trade_type'] == '开仓'
    assert record['net_adjustment'] is True
    assert record['execution_action'] == 'close'
    assert record['display_trade_type'] == '空头平仓'
    assert record['display_direction'] == '空头'
    assert record['realized_pnl'] == pytest.approx(-21.9545)
    assert record['order_pnl'] == pytest.approx(-21.9545)
    # 备注单侧：该侧自身原因优先，机制作次要说明；不再出现归因叙事
    assert record['display_note'] == '信号平仓（净头寸调整执行）'
    assert '归因' not in record['display_note']


def test_execution_close_sell_displays_ping_duo():
    record = web._normalize_lead_trade_record(_raw_close_record(
        order_id='close-long-1',
        side='SELL',
        execution_action='close',
        execution_trade_type='平仓',
    ))
    assert record['display_trade_type'] == '多头平仓'
    assert record['display_direction'] == '多头'


def test_execution_open_short_displays_kai_kong():
    record = web._normalize_lead_trade_record(_raw_close_record(
        order_id='open-short-1',
        side='SELL',
        execution_action='open',
        execution_trade_type='开仓',
        trade_type='开仓',
    ))
    assert record['display_trade_type'] == '空头开仓'
    assert record['display_direction'] == '空头'


def test_execution_add_long_displays_jia_duo():
    record = web._normalize_lead_trade_record(_raw_close_record(
        order_id='add-long-1',
        side='BUY',
        execution_action='add',
        execution_trade_type='加仓',
        trade_type='加仓',
    ))
    assert record['display_trade_type'] == '多头加仓'
    assert record['display_direction'] == '多头'


def test_open_long_net_alignment_note_not_rendered_as_signal_open():
    record = web._normalize_lead_trade_record(_raw_open_long_record())
    assert record['display_trade_type'] == '多头开仓'
    assert record['display_direction'] == '多头'
    # 净头寸对齐开仓不呈现为新信号开仓（即便 leg_reason 为“信号开仓”）
    assert record['display_note'] == '多头仓位对齐（净头寸调整执行）'
    assert '归因' not in record['display_note']
    assert '信号开仓' not in record['display_note']


def test_legacy_close_falls_back_to_trade_type_not_side():
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': 'legacy-close-1',
        'symbol': 'BTCUSDT.P',
        'side': 'BUY',
        'quantity': 2.0,
        'price': 100.0,
        'trade_type': '平仓',
        'reason': (
            '空头平仓 | 触发: 双向信号净头寸调整 '
            'virtual_short=0.197000 virtual_long=0.187000 net=-0.010000 | 结果: 亏损'
        ),
        'realized_pnl': -762.8,
        'timestamp': '2026-10-06 00:00:03',
    })
    assert record['net_adjustment'] is True
    assert record['display_trade_type'] == '空头平仓'
    assert record['display_direction'] == '空头'


def test_legacy_add_uses_trade_type_action():
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': 'legacy-add-1',
        'symbol': 'BTCUSDT.P',
        'side': 'SELL',
        'quantity': 0.05,
        'price': 90000.0,
        'trade_type': '加仓',
        'net_adjustment': True,
        'attribution': {'leg': 'short', 'action': 'add', 'quantity': 0.05},
        'alert_message': '空头加仓（净头寸调整）',
    })
    assert record['display_trade_type'] == '空头加仓'
    assert record['display_direction'] == '空头'


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
    assert record['display_trade_type'] == '空头平仓'
    assert record['display_direction'] == '空头'
    assert record['display_note'] == ''


def test_stale_display_fields_overwritten_before_after():
    raw = _raw_close_record()
    assert (raw['display_trade_type'], raw['display_direction'], raw['display_note']) == (
        '开多仓', '多头', '净头寸调整',
    )
    record = web._normalize_lead_trade_record(raw)
    assert (record['display_trade_type'], record['display_direction']) == ('空头平仓', '空头')
    assert record['display_note'] == '信号平仓（净头寸调整执行）'


def test_normalize_is_idempotent():
    first = web._normalize_lead_trade_record(_raw_close_record())
    second = web._normalize_lead_trade_record(first)
    assert first == second


def test_leg_fields_preserved_for_recompute():
    record = web._normalize_lead_trade_record(_raw_close_record())
    assert record['leg_direction'] == 'short'
    assert record['leg_action'] == 'close'
    assert record['leg_reason'] == '信号平仓'
    assert record['mechanism'] == 'net_position_alignment'
    assert record['mechanism_label'] == '净头寸调整执行'
    # 归一化产物落盘后再次归一化：备注/徽章一致（不因字段丢失退化）
    assert web._normalize_lead_trade_record(record) == record


def test_mechanism_field_marks_net_adjustment_without_flag_or_keyword():
    record = web._normalize_lead_trade_record(_raw_close_record(
        net_adjustment=False,
        reason='行情反转',
    ))
    assert record['net_adjustment'] is True
    assert record['display_note'] == '信号平仓（净头寸调整执行）'


def test_new_payload_close_without_leg_reason_uses_mechanism_label():
    record = web._normalize_lead_trade_record(_raw_close_record(leg_reason=''))
    assert record['display_note'] == '净头寸调整执行'
    assert '归因' not in record['display_note']


def test_other_mechanism_is_not_net_adjustment():
    raw = _without_leg_fields(_raw_close_record(net_adjustment=False, reason='止损'))
    raw['mechanism'] = 'signal_exit'
    record = web._normalize_lead_trade_record(raw)
    assert record['net_adjustment'] is False
    assert record['display_note'] == ''


def test_legacy_close_without_new_fields_keeps_execution_note():
    record = web._normalize_lead_trade_record(_without_leg_fields(_raw_close_record()))
    assert record['net_adjustment'] is True
    assert record['display_trade_type'] == '空头平仓'
    assert record['display_note'] == '净头寸调整（原因：双向信号净头寸调整）'
    assert '归因' not in record['display_note']


def test_legacy_close_with_attribution_drops_attribution_narrative():
    legacy = _without_leg_fields(_raw_close_record(attribution={
        'leg': 'long',
        'action': 'open',
        'quantity': 0.187,
        'net_position_before': -0.197,
        'net_position_after': -0.010,
    }))
    record = web._normalize_lead_trade_record(legacy)
    assert record['display_trade_type'] == '空头平仓'
    assert '归因' not in record['display_note']
    assert record['display_note'] == '净头寸调整（净头寸：空 0.197→空 0.01；原因：双向信号净头寸调整）'


def test_legacy_open_with_attribution_uses_alignment_note():
    record = web._normalize_lead_trade_record(_without_leg_fields(_raw_open_long_record()))
    assert record['display_trade_type'] == '多头开仓'
    assert record['display_direction'] == '多头'
    assert record['display_note'] == '多头仓位对齐（净头寸调整执行）'
    assert '归因' not in record['display_note']


def test_legacy_close_record_recompute_idempotent():
    legacy = _without_leg_fields(_raw_close_record())
    first = web._normalize_lead_trade_record(legacy)
    second = web._normalize_lead_trade_record(first)
    assert first == second
    assert first['display_note'] == '净头寸调整（原因：双向信号净头寸调整）'


# ---------------------------------------------------------------------------
# 回放账务（今日两笔真实 payload）
# ---------------------------------------------------------------------------

def test_replay_net_adjustment_close_uses_execution_semantics():
    records = _normalized([_raw_short_open_record(), _raw_close_record(), _raw_open_long_record()])
    bucket = _bucket_of(records)

    assert bucket['SELL']['quantity'] == pytest.approx(0.0)
    assert bucket['BUY']['quantity'] == pytest.approx(0.173)
    assert bucket['BUY']['avg_price'] == pytest.approx(83281.9)

    close_record = next(record for record in records if record['order_id'] == 'today-a')
    assert close_record['order_pnl'] == pytest.approx(-21.9545)  # 显式 PnL 保留
    assert close_record['realized_pnl'] == pytest.approx(-21.9545)
    assert close_record['entry_price'] == pytest.approx(81144.0)
    assert close_record['exit_price'] == pytest.approx(83281.9)

    summary = web._build_lead_summary(records, initial_funds=10000.0)
    assert summary['total_realized_pnl'] == pytest.approx(-21.9545)
    assert summary['close_trade_count'] == 1


def test_replay_without_explicit_pnl_computes_from_bucket():
    records = _normalized([
        _raw_short_open_record(),
        _raw_close_record(realized_pnl=None, gross_pnl=None),
        _raw_open_long_record(),
    ])
    close_record = next(record for record in records if record['order_id'] == 'today-a')
    assert close_record['order_pnl'] == pytest.approx((81144.0 - 83281.9) * 0.01, abs=1e-4)
    assert close_record['realized_pnl'] == pytest.approx(close_record['order_pnl'])


def test_replay_open_record_not_treated_as_close():
    # 净调开仓（execution open）：即使带 net_adjustment 标记也按开仓计入多头桶
    records = _normalized([_raw_open_long_record()])
    bucket = _bucket_of(records)
    assert bucket['BUY']['quantity'] == pytest.approx(0.173)
    assert bucket['SELL']['quantity'] == pytest.approx(0.0)


def test_load_lead_data_recomputes_stale_display(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    payload = {
        'summary': {'initial_funds': 10000.0},
        'trade_records': [_raw_short_open_record(), _raw_close_record(), _raw_open_long_record()],
    }
    (tmp_path / 'lead_trades.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8'
    )

    loaded = web.load_lead_data()
    close_record = next(
        record for record in loaded['trade_records'] if record['order_id'] == 'today-a'
    )
    assert close_record['display_trade_type'] == '空头平仓'
    assert close_record['display_direction'] == '空头'
    assert close_record['realized_pnl'] == pytest.approx(-21.9545)

    on_disk = json.loads((tmp_path / 'lead_trades.json').read_text(encoding='utf-8'))
    assert on_disk['trade_records'][1]['display_trade_type'] == '开多仓'  # 加载只重算内存


# ---------------------------------------------------------------------------
# 决策腿（decision_leg_*）显示优先级 + 历史回填
# ---------------------------------------------------------------------------

def test_legacy_1006_backfilled_displays_decision_leg_open_long():
    record = web._normalize_lead_trade_record(_backfilled_1006_record())
    assert record['display_trade_type'] == '多头开仓'
    assert record['display_direction'] == '多头'
    assert '净头寸调整' in record['display_note']
    assert '实际执行' in record['display_note']
    assert '减少空头' in record['display_note']
    assert '0.187' in record['display_note']
    assert '归因' not in record['display_note']
    # 盈亏照常显示
    assert record['order_pnl'] == pytest.approx(-762.29)
    assert record['realized_pnl'] == pytest.approx(-762.29)


def test_1008_close_falls_back_to_ping_kong():
    record = web._normalize_lead_trade_record(_raw_close_record())
    assert record['decision_leg_direction'] == ''
    assert record['decision_leg_action'] == ''
    assert record['display_trade_type'] == '空头平仓'
    assert record['display_direction'] == '空头'
    assert record['display_note'] == '信号平仓（净头寸调整执行）'
    assert record['order_pnl'] == pytest.approx(-21.9545)


def test_decision_leg_priority_over_leg_and_execution():
    # 决策腿（long/open）与 leg_*/执行语义（short/close）冲突时，以决策腿为准
    record = web._normalize_lead_trade_record(_raw_close_record(
        decision_leg_direction='long',
        decision_leg_action='open',
    ))
    assert record['display_trade_type'] == '多头开仓'
    assert record['display_direction'] == '多头'
    assert '实际执行' in record['display_note']
    assert '归因' not in record['display_note']


def test_decision_missing_falls_back_to_leg_fields():
    # 无 decision_leg_* 时回退 leg_*（开仓备注沿用仓位对齐口径；执行语义给徽章）
    raw = _raw_open_long_record()
    raw.pop('execution_action', None)
    raw.pop('execution_trade_type', None)
    record = web._normalize_lead_trade_record(raw)
    assert record['decision_leg_direction'] == ''
    assert record['decision_leg_action'] == ''
    assert record['display_trade_type'] == '多头开仓'
    assert record['display_direction'] == '多头'
    assert record['display_note'] == '多头仓位对齐（净头寸调整执行）'


def test_backfill_tool_backfills_and_is_idempotent(tmp_path, monkeypatch):
    data_path = tmp_path / 'lead_trades.json'
    payload = {
        'summary': {'initial_funds': 10000.0},
        'trade_records': [_raw_legacy_1006_record()],
    }
    data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    result = backfill_tool.backfill_file(str(data_path))
    assert result['ok'] is True
    assert result['found'] is True
    assert result['changed'] is True
    assert result['backup'] and os.path.exists(result['backup'])
    saved = json.loads(data_path.read_text(encoding='utf-8'))
    saved_record = saved['trade_records'][0]
    assert saved_record['decision_leg_direction'] == 'long'
    assert saved_record['decision_leg_action'] == 'open'
    assert saved_record['net_adjustment'] is True

    # 幂等：第二次运行不再写盘、不新增备份
    files_before = sorted(os.listdir(tmp_path))
    result2 = backfill_tool.backfill_file(str(data_path))
    assert result2['changed'] is False
    assert sorted(os.listdir(tmp_path)) == files_before

    # 模拟重启：Web 归一化 → 多头开仓；落盘后重载仍稳定（字段持久化）
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    loaded = web.load_lead_data()
    reloaded_record = loaded['trade_records'][0]
    assert reloaded_record['display_trade_type'] == '多头开仓'
    assert reloaded_record['display_direction'] == '多头'
    assert reloaded_record['decision_leg_direction'] == 'long'
    assert reloaded_record['decision_leg_action'] == 'open'
    assert '实际执行' in reloaded_record['display_note']
    web.save_lead_data(loaded)
    loaded_again = web.load_lead_data()
    assert loaded_again['trade_records'][0]['display_trade_type'] == '多头开仓'
    renormalized = web._normalize_lead_trade_record(loaded_again['trade_records'][0])
    web._finalize_lead_records([renormalized])
    assert renormalized == loaded_again['trade_records'][0]


def test_backfill_tool_dry_run_writes_nothing(tmp_path):
    data_path = tmp_path / 'lead_trades.json'
    payload = {
        'summary': {'initial_funds': 10000.0},
        'trade_records': [_raw_legacy_1006_record()],
    }
    data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    before = data_path.read_text(encoding='utf-8')

    result = backfill_tool.backfill_file(str(data_path), dry_run=True)
    assert result['changed'] is True
    assert result['backup'] == ''
    assert data_path.read_text(encoding='utf-8') == before
    assert sorted(os.listdir(tmp_path)) == ['lead_trades.json']


# ---------------------------------------------------------------------------
# 现网五条记录：方向在前文案 + 盈亏方向归属（display_pnl 结转）
# ---------------------------------------------------------------------------

def test_live_five_records_direction_labels_and_pnl_attribution():
    records = _finalized(_live_five_records())
    by_id = {record['order_id']: record for record in records}

    short_open = by_id['1141560706678']
    assert short_open['display_trade_type'] == '空头开仓'
    assert short_open['display_direction'] == '空头'
    assert short_open['display_pnl'] is None

    decision_open = by_id['1155109993906']
    assert decision_open['display_trade_type'] == '多头开仓'
    assert decision_open['display_direction'] == '多头'
    assert decision_open['display_pnl'] is None  # 不显示在多头开仓行
    assert decision_open['order_pnl'] == pytest.approx(-762.2868)  # 原始账务保留
    assert '实际执行' in decision_open['display_note']
    assert '归因' not in decision_open['display_note']

    close_short = by_id['1144960000001']
    assert close_short['display_trade_type'] == '空头平仓'
    assert close_short['display_direction'] == '空头'
    # -762.2868（10-06 结转）+ -21.379（本行）= -783.6658（前端 2 位显示 -783.67）
    assert close_short['display_pnl'] == pytest.approx(-783.6658)
    assert round(close_short['display_pnl'], 2) == pytest.approx(-783.67)
    assert close_short['display_pnl_note'] == '含 10-06 结转'
    assert close_short['display_note'] == '信号平仓（净头寸调整执行）'

    open_long = by_id['1144960000002']
    assert open_long['display_trade_type'] == '多头开仓'
    assert open_long['display_direction'] == '多头'
    assert open_long['display_pnl'] is None

    add_long = by_id['1144960000003']
    assert add_long['display_trade_type'] == '多头加仓'
    assert add_long['display_direction'] == '多头'
    assert add_long['display_pnl'] is None

    # 总账不变：展示盈亏合计 == 原始已实现盈亏合计
    display_total = sum(
        record['display_pnl'] for record in records if record['display_pnl'] is not None
    )
    raw_total = sum(
        value for value in (web._extract_lead_realized_pnl(record) for record in records)
        if value is not None
    )
    assert display_total == pytest.approx(raw_total)


def test_display_pnl_carry_accumulates_multiple_sources():
    records = _finalized([
        _buy_close_with_decision('2026-10-06 00:00:03', -100.0, 'long', 'open', 'carry-a'),
        _buy_close_with_decision('2026-10-07 00:00:03', -50.0, 'long', 'open', 'carry-b'),
        _buy_close_with_decision('2026-10-08 00:00:03', -20.0, 'short', 'close', 'carry-close'),
    ])
    assert records[0]['display_trade_type'] == '多头开仓'
    assert records[0]['display_pnl'] is None
    assert records[1]['display_pnl'] is None
    assert records[2]['display_trade_type'] == '空头平仓'
    assert records[2]['display_pnl'] == pytest.approx(-170.0)
    assert records[2]['display_pnl_note'] == '含 10-06、10-07 结转'


def test_display_pnl_without_later_close_row_stays_hidden():
    records = _finalized([
        _buy_close_with_decision('2026-10-05 00:00:03', -10.0, 'short', 'close', 'edge-close'),
        _buy_close_with_decision('2026-10-06 00:00:03', -100.0, 'long', 'open', 'edge-park'),
        _live_1008_open_long(order_id='edge-open'),
    ])
    assert records[0]['display_pnl'] == pytest.approx(-10.0)  # 更早的平仓行不受影响
    assert records[1]['display_pnl'] is None  # 挂起
    assert records[2]['display_pnl'] is None  # 非平仓行不承接
    assert records[1].get('display_pnl_note') is None


def test_display_pnl_idempotent_across_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    payload = {
        'summary': {'initial_funds': 10000.0},
        'trade_records': _live_five_records(),
    }
    (tmp_path / 'lead_trades.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8'
    )

    loaded = web.load_lead_data()
    close_row = next(
        record for record in loaded['trade_records'] if record['order_id'] == '1144960000001'
    )
    assert close_row['display_pnl'] == pytest.approx(-783.6658)
    assert close_row['display_pnl_note'] == '含 10-06 结转'

    web.save_lead_data(loaded)
    reloaded = web.load_lead_data()
    assert reloaded['trade_records'] == loaded['trade_records']

    # 二次收尾重算幂等
    web._finalize_lead_records(loaded['trade_records'])
    assert loaded['trade_records'] == reloaded['trade_records']


def test_legacy_record_without_display_pnl_field_falls_back():
    # 旧记录（未经收尾/旧调用）：无 display_pnl 字段，normalize 仍给方向在前文案
    record = web._normalize_lead_trade_record({
        'account_id': 'binance.lead',
        'order_id': 'legacy-fallback-1',
        'symbol': 'BTCUSDT.P',
        'side': 'SELL',
        'quantity': 0.5,
        'price': 90000.0,
        'trade_type': '平仓',
        'realized_pnl': 12.5,
        'timestamp': '2026-09-15 12:00:00',
    })
    assert record['display_trade_type'] == '多头平仓'
    assert record['display_direction'] == '多头'
    assert 'display_pnl' not in record
    # 收尾后（新管线）自平行显示原始盈亏
    finalized = _finalized([record])
    assert finalized[0]['display_pnl'] == pytest.approx(12.5)
    assert finalized[0].get('display_pnl_note') is None


def test_total_profit_sync_uses_display_pnl_attribution_date():
    records = _finalized(_live_five_records())
    total_profit = {
        'trade_records': [],
        'symbol_profit_tracker': {},
        'profit_curve_data': {
            'data_points': [
                {'date': '2025-03', 'principal': 10000, 'total_funds': 10000},
                {'date': '2026-10-05', 'principal': 12000, 'total_funds': 13000},
            ]
        },
    }
    # 10-06 当天：该笔亏损挂在多头开仓行（display_pnl=None）→ 不计入
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 6, 12, 0, 0),
    ) is False
    assert all(
        point['date'] != '2026-10-06'
        for point in total_profit['profit_curve_data']['data_points']
    )

    # 10-08：结转亏损随空头平仓行落 10-08
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is True
    point = total_profit['profit_curve_data']['data_points'][-1]
    assert point['date'] == '2026-10-08'
    assert point['total_funds'] == pytest.approx(13000.0 - 783.6658)


# ---------------------------------------------------------------------------
# total_profit.json 自动更新
# ---------------------------------------------------------------------------

def test_total_profit_sync_appends_today_point():
    records = _normalized([_raw_short_open_record(), _raw_close_record(), _raw_open_long_record()])
    total_profit = _total_profit_stub()

    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records}
    ) is True
    point = total_profit['profit_curve_data']['data_points'][-1]
    assert point['date'] == datetime.now().strftime('%Y-%m-%d')
    assert point['principal'] == pytest.approx(12000.0)
    assert point['total_funds'] == pytest.approx(13000.0 - 21.9545)

    # 幂等：重复同步不再变化
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records}
    ) is False


def test_total_profit_sync_same_day_incremental_not_double_counted():
    records = _normalized([_raw_short_open_record(), _raw_close_record(), _raw_open_long_record()])
    total_profit = _total_profit_stub()
    web._sync_total_profit_from_lead(total_profit, {'summary': {}, 'trade_records': records})

    records.append(web._normalize_lead_trade_record(_raw_close_record(
        order_id='today-c',
        side='SELL',
        quantity=0.005,
        price=84000.0,
        realized_pnl=5.0,
        gross_pnl=5.2,
        timestamp=_timestamp_at(0, 9, 0, 0),
    )))
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records}
    ) is True
    point = total_profit['profit_curve_data']['data_points'][-1]
    assert point['total_funds'] == pytest.approx(13000.0 - 21.9545 + 5.0)


def test_total_profit_sync_ignores_pre_baseline_records():
    old_close = web._normalize_lead_trade_record(_raw_close_record(
        order_id='old-close-1',
        realized_pnl=-50.0,
        gross_pnl=-50.0,
        timestamp=_timestamp_at(-5, 8, 0, 0),
    ))
    total_profit = _total_profit_stub()
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': [old_close]}
    ) is False
    assert len(total_profit['profit_curve_data']['data_points']) == 2


def test_total_profit_sync_requires_baseline_point():
    total_profit = {
        'trade_records': [],
        'symbol_profit_tracker': {},
        'profit_curve_data': {
            'data_points': [{'date': datetime.now().strftime('%Y-%m-%d'), 'principal': 1, 'total_funds': 1}]
        },
    }
    records = _normalized([_raw_close_record()])
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records}
    ) is False


def test_profit_curve_window_start_month_and_day():
    assert web._profit_curve_window_start('2026-08') == (2026, 9, 1)
    assert web._profit_curve_window_start('2026-12') == (2027, 1, 1)
    assert web._profit_curve_window_start('2026-2') == (2026, 3, 1)
    assert web._profit_curve_window_start('2026-08-31') == (2026, 9, 1)
    assert web._profit_curve_window_start('2026-02-28') == (2026, 3, 1)
    assert web._profit_curve_window_start('2026-02-31') is None
    assert web._profit_curve_window_start('2026-08-01-extra') is None
    assert web._profit_curve_window_start('bad') is None
    assert web._profit_curve_window_start(None) is None


def test_total_profit_sync_month_baseline_does_not_recount_same_month_records():
    total_profit = _month_baseline_stub()
    records = [
        _close_record_at('2026-08-22 12:00:03', -2170.5735, 'month-a'),
        _close_record_at('2026-08-23 12:00:03', 1773.0, 'month-b'),
    ]
    snapshot = json.dumps(total_profit, ensure_ascii=False, sort_keys=True)
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is False
    assert json.dumps(total_profit, ensure_ascii=False, sort_keys=True) == snapshot
    assert len(total_profit['profit_curve_data']['data_points']) == 2


def test_total_profit_sync_month_baseline_window_starts_next_month():
    total_profit = _month_baseline_stub()
    records = [
        _close_record_at('2026-08-31 23:59:59', 500.0, 'month-edge-a'),
        _close_record_at('2026-09-01 00:00:01', 123.5, 'month-edge-b'),
    ]
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is True
    point = total_profit['profit_curve_data']['data_points'][-1]
    assert point['date'] == '2026-10-08'
    assert point['principal'] == pytest.approx(42486.0)
    assert point['total_funds'] == pytest.approx(54500.0 + 123.5)


def test_total_profit_sync_real_data_month_baseline_no_change():
    data_dir = os.path.join(WEB_DIR, 'data')
    with open(os.path.join(data_dir, 'total_profit.json'), encoding='utf-8') as handle:
        total_profit = json.load(handle)
    with open(os.path.join(data_dir, 'lead_trades.json'), encoding='utf-8') as handle:
        lead_payload = json.load(handle)
    records = [
        web._normalize_lead_trade_record(raw)
        for raw in lead_payload.get('trade_records', [])
        if isinstance(raw, dict)
    ]
    web._replay_trade_records_with_pnl(records)
    snapshot = json.dumps(total_profit, ensure_ascii=False, sort_keys=True)
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is False
    assert json.dumps(total_profit, ensure_ascii=False, sort_keys=True) == snapshot


def test_total_profit_sync_day_baseline_starts_next_day():
    total_profit = {
        'trade_records': [],
        'symbol_profit_tracker': {},
        'profit_curve_data': {
            'data_points': [
                {'date': '2025-03', 'principal': 10000, 'total_funds': 10000},
                {'date': '2026-10-07', 'principal': 12000, 'total_funds': 13000},
            ]
        },
    }
    records = [
        _close_record_at('2026-10-07 23:59:59', 999.0, 'day-same'),
        _close_record_at('2026-10-08 08:00:05', 20.0, 'day-next'),
    ]
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is True
    point = total_profit['profit_curve_data']['data_points'][-1]
    assert point['date'] == '2026-10-08'
    assert point['total_funds'] == pytest.approx(13020.0)


def test_total_profit_sync_empty_window_does_not_write_point():
    total_profit = _month_baseline_stub()
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': []},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is False
    assert all(
        point['date'] != '2026-10-08'
        for point in total_profit['profit_curve_data']['data_points']
    )


def test_total_profit_sync_unknown_baseline_format_skipped_with_warning(capsys):
    total_profit = {
        'trade_records': [],
        'symbol_profit_tracker': {},
        'profit_curve_data': {
            'data_points': [
                {'date': '2025-03', 'principal': 10000, 'total_funds': 10000},
                {'date': '2026-08-01-extra', 'principal': 42486, 'total_funds': 54500},
            ]
        },
    }
    records = [_close_record_at('2026-09-15 12:00:00', 50.0, 'guard-a')]
    snapshot = json.dumps(total_profit, ensure_ascii=False, sort_keys=True)
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is False
    assert '无法判定基线点日期格式' in capsys.readouterr().out
    assert json.dumps(total_profit, ensure_ascii=False, sort_keys=True) == snapshot


def test_total_profit_sync_tiny_window_pnl_not_written():
    total_profit = _month_baseline_stub()
    records = [{
        'order_id': 'tiny-1',
        'trade_type': '平仓',
        'order_pnl': 1e-10,
        'timestamp': '2026-09-15 12:00:00',
    }]
    count = len(total_profit['profit_curve_data']['data_points'])
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is False
    assert len(total_profit['profit_curve_data']['data_points']) == count


def test_total_profit_sync_existing_point_within_tolerance_not_rewritten():
    total_profit = _month_baseline_stub()
    total_profit['profit_curve_data']['data_points'].append({
        'date': '2026-10-08',
        'principal': 42486.0,
        'total_funds': 54500.0 + 123.5 + 1e-10,
    })
    records = [_close_record_at('2026-09-15 12:00:00', 123.5, 'tol-a')]
    assert web._sync_total_profit_from_lead(
        total_profit, {'summary': {}, 'trade_records': records},
        now=datetime(2026, 10, 8, 12, 0, 0),
    ) is False


def test_save_json_if_changed_writes_atomically_without_tmp_leftover(tmp_path):
    target = tmp_path / 'sample.json'
    web._save_json_if_changed(str(target), {'a': 1}, '测试数据')
    assert json.loads(target.read_text(encoding='utf-8')) == {'a': 1}
    assert [entry.name for entry in tmp_path.iterdir()] == ['sample.json']


def test_save_json_if_changed_replace_failure_keeps_original(tmp_path, monkeypatch):
    target = tmp_path / 'sample.json'
    target.write_text('{"a": 1}', encoding='utf-8')

    def _boom(src, dst):
        raise OSError('disk full')

    monkeypatch.setattr(web.os, 'replace', _boom)
    web._save_json_if_changed(str(target), {'a': 2}, '测试数据')
    assert json.loads(target.read_text(encoding='utf-8')) == {'a': 1}
    assert [entry.name for entry in tmp_path.iterdir()] == ['sample.json']


def test_hot_reload_guard_keeps_memory_on_failure(tmp_path, monkeypatch, capsys):
    (tmp_path / 'total_profit.json').write_text('{broken', encoding='utf-8')
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    current = {'trade_records': ['keep-me']}
    reloaded = web._hot_reload_json(web.load_total_profit_data, '总盈利数据')
    assert reloaded is None
    assert current == {'trade_records': ['keep-me']}
    assert '总盈利数据热加载失败，保留现有内存数据' in capsys.readouterr().out


def test_load_total_profit_data_strict_returns_none_on_corrupt_file(tmp_path, monkeypatch):
    (tmp_path / 'total_profit.json').write_text('{broken', encoding='utf-8')
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    assert web.load_total_profit_data(strict=True) is None
    fallback = web.load_total_profit_data()
    assert fallback['trade_records'] == []


def test_load_total_profit_data_strict_missing_file_uses_default(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    fallback = web.load_total_profit_data(strict=True)
    assert fallback is not None
    assert fallback['trade_records'] == []


def test_load_lead_data_strict_returns_none_on_corrupt_file(tmp_path, monkeypatch):
    (tmp_path / 'lead_trades.json').write_text('not-json', encoding='utf-8')
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    assert web.load_lead_data(strict=True) is None
    assert web.load_lead_data()['trade_records'] == []


def test_update_lead_data_persists_corrections_and_total_profit(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    storage = web.DataStorage()
    storage.lead_data = {'summary': {}, 'trade_records': []}
    storage.total_profit_data = _total_profit_stub()

    storage.update_lead_data({
        'trade_records': [_raw_short_open_record(), _raw_close_record(), _raw_open_long_record()],
    })

    saved_lead = json.loads((tmp_path / 'lead_trades.json').read_text(encoding='utf-8'))
    close_record = next(
        record for record in saved_lead['trade_records'] if record['order_id'] == 'today-a'
    )
    assert close_record['display_trade_type'] == '空头平仓'
    assert close_record['display_direction'] == '空头'
    assert close_record['display_note'] == '信号平仓（净头寸调整执行）'
    assert close_record['leg_reason'] == '信号平仓'
    assert close_record['mechanism'] == 'net_position_alignment'
    assert close_record['order_pnl'] == pytest.approx(-21.9545)
    assert close_record['realized_pnl'] == pytest.approx(-21.9545)

    saved_profit = json.loads((tmp_path / 'total_profit.json').read_text(encoding='utf-8'))
    point = saved_profit['profit_curve_data']['data_points'][-1]
    assert point['date'] == datetime.now().strftime('%Y-%m-%d')
    assert point['total_funds'] == pytest.approx(13000.0 - 21.9545)
    assert 'profit_summary' not in saved_profit


# ---------------------------------------------------------------------------
# 前端模板
# ---------------------------------------------------------------------------

def test_template_uses_display_fields():
    template_path = os.path.join(WEB_DIR, 'templates', 'index.html')
    with open(template_path, encoding='utf-8') as handle:
        html = handle.read()
    assert 'trade.display_trade_type || trade.trade_type' in html
    assert 'isNetAdjustment ? null' not in html
    # 盈亏列优先 display_pnl（字段存在时 null 表示 "-"），结转备注随行展示
    assert "Object.prototype.hasOwnProperty.call(trade, 'display_pnl')" in html
    assert 'trade.display_pnl_note' in html
    assert 'formatSignedMoney(pnl, 2)' in html
    assert 'trade.order_pnl ?? trade.realized_pnl ?? trade.net_profit' in html
    assert 'trade.display_note || trade.reason' in html
    # 方向在前统一文案（新标签样式）
    assert "'多头平仓'" in html and "'空头平仓'" in html
    assert "'多头开仓'" in html and "'空头开仓'" in html
    assert "'多头加仓'" in html and "'空头加仓'" in html
