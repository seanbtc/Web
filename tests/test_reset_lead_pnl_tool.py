# -*- coding: utf-8 -*-
"""策略模块盈亏归零工具：offset 计算 + 幂等 + dry-run（2026-10-18 用户裁定）。"""
import json
import os
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import importlib.util

spec = importlib.util.spec_from_file_location(
    'reset_lead_pnl_baseline', str(WEB_DIR / 'tools' / 'reset_lead_pnl_baseline.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_compute_reset_offset_uses_displayed_and_offset():
    assert tool.compute_reset_offset({'total_realized_pnl': -2024.2923, 'pnl_offset': 0.0}) == 2024.2923
    assert tool.compute_reset_offset(
        {'total_realized_pnl': 0.0, 'pnl_offset': 2024.2923, 'raw_total_realized_pnl': -2024.2923}) == 2024.2923
    assert tool.compute_reset_offset({}) == 0.0
    assert tool.compute_reset_offset({'total_realized_pnl': 'bad'}) is None


def test_reset_tool_idempotent_and_dry_run(tmp_path, capsys):
    path = tmp_path / 'lead_trades.json'
    path.write_text(json.dumps({
        'summary': {'total_realized_pnl': -100.0, 'pnl_offset': 0.0, 'initial_funds': 10000.0},
        'trade_records': [],
    }), encoding='utf-8')

    assert tool.main(['--file', str(path), '--dry-run']) == 0
    assert json.loads(path.read_text(encoding='utf-8'))['summary']['pnl_offset'] == 0.0

    assert tool.main(['--file', str(path)]) == 0
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['summary']['pnl_offset'] == 100.0
    assert list(tmp_path.glob('lead_trades.json.bak-*'))                 # 备份存在

    assert tool.main(['--file', str(path)]) == 0                         # 幂等：不再写盘
    assert json.loads(path.read_text(encoding='utf-8'))['summary']['pnl_offset'] == 100.0
    assert '已归零（幂等）' in capsys.readouterr().out
