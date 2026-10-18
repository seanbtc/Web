# -*- coding: utf-8 -*-
"""策略模块历史订单清空工具（clear_lead_records）：清空/备份/幂等/--yes 门槛（2026-10-18）。"""
import importlib.util
import json
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    'clear_lead_records', str(WEB_DIR / 'tools' / 'clear_lead_records.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def _write_lead(path, records=3):
    rows = [{'order_id': f'o{i}', 'realized_pnl': 10.0 * i} for i in range(records)]
    path.write_text(json.dumps({
        'summary': {
            'initial_funds': 10000.0,
            'archived_realized_pnl': -100.0,
            'pnl_offset': 250.0,
            'total_realized_pnl': 120.0,
        },
        'trade_records': rows,
    }), encoding='utf-8')


def test_requires_yes_and_dry_run_does_not_write(tmp_path):
    path = tmp_path / 'lead_trades.json'
    _write_lead(path, records=2)
    assert tool.main(['--file', str(path), '--dry-run']) == 0
    assert tool.count_records(json.loads(path.read_text(encoding='utf-8'))) == 2
    assert tool.main(['--file', str(path)]) == 2                 # 缺 --yes 拒绝
    assert tool.count_records(json.loads(path.read_text(encoding='utf-8'))) == 2


def test_clear_records_and_summary_with_backup(tmp_path, capsys):
    path = tmp_path / 'lead_trades.json'
    _write_lead(path, records=3)
    assert tool.main(['--file', str(path), '--yes']) == 0
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['trade_records'] == []
    assert payload['summary'] == tool.EMPTY_SUMMARY
    backups = list((tmp_path / 'backups').glob('lead_trades.json.*.json'))
    assert len(backups) == 1
    assert '已清空' in capsys.readouterr().out

    assert tool.main(['--file', str(path), '--yes']) == 0        # 幂等
    assert len(list((tmp_path / 'backups').glob('lead_trades.json.*.json'))) == 1
    assert '已是初始态' in capsys.readouterr().out


def test_missing_file_returns_error(tmp_path):
    assert tool.main(['--file', str(tmp_path / 'nope.json'), '--yes']) == 1
