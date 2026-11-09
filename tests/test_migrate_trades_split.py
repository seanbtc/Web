# -*- coding: utf-8 -*-
"""旧 top/bottom 数据拆分迁移脚本测试。"""
import json
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = WEB_DIR / 'tools'
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import migrate_trades_split as migrate  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def _seed(data_dir: Path) -> None:
    _write(data_dir / 'top_trades.json', {
        'position_status': '空仓', 'position_quantity': 0.0,
        'position_avg_price': 0.0, 'position_symbol': 'BTCUSDT',
        'status': '空仓',
        'trade_records': [{'id': 1, 'mode': '做空', 'quantity': 0.27, 'is_closed': True}],
    })
    _write(data_dir / 'bottom_trades.json', {
        'position_status': '现货', 'position_quantity': 1.21,
        'position_avg_price': 80807, 'position_symbol': 'BTCUSDT',
        'status': '满仓',
        'ahr999': {
            'plan_id': 'ahr999_bottom_btcusd1', 'position_quantity': 0.0478,
            'position_avg_price': 76068.6, 'status': 'AHR999条件定投中',
        },
        'trade_records': [
            {'id': 1, 'mode': '现货', 'quantity': 1.206, 'avg_price': 81062.0, 'is_closed': False},
            {'id': 2, 'source': 'ahr999_dca', 'plan_id': 'ahr999_bottom_btcusd1',
             'cycle_id': 1, 'mode': '定投开仓', 'quantity': 0.0241,
             'avg_price': 76224.7, 'is_closed': False},
            {'id': 3, 'source': 'ahr999_dca', 'plan_id': 'ahr999_bottom_btcusd1',
             'cycle_id': 2, 'mode': '止盈平仓', 'quantity': 0.0241,
             'avg_price': 83430, 'is_closed': True, 'profit': 170},
        ],
    })


def test_split_moves_old_files_and_writes_new(tmp_path):
    _seed(tmp_path)

    assert migrate.main(['--data-dir', str(tmp_path), '--yes']) == 0

    spot = json.loads((tmp_path / 'spot_trades.json').read_text(encoding='utf-8'))
    bottom_top = json.loads((tmp_path / 'bottom_top_trades.json').read_text(encoding='utf-8'))
    assert spot['position_quantity'] == 1.21
    assert spot['status'] == '满仓'
    assert [r['mode'] for r in spot['trade_records']] == ['现货']
    assert bottom_top['top']['trade_records'][0]['mode'] == '做空'
    assert [r['mode'] for r in bottom_top['bottom']['trade_records']] == ['定投开仓', '止盈平仓']
    assert bottom_top['bottom']['ahr999']['position_quantity'] == 0.0478
    assert not (tmp_path / 'top_trades.json').exists()
    assert not (tmp_path / 'bottom_trades.json').exists()
    archives = list((tmp_path / 'archive').glob('*-pre-trades-split'))
    assert len(archives) == 1
    assert (archives[0] / 'top_trades.json').exists()
    assert (archives[0] / 'bottom_trades.json').exists()


def test_split_is_idempotent_after_migration(tmp_path):
    _seed(tmp_path)
    assert migrate.main(['--data-dir', str(tmp_path), '--yes']) == 0
    assert migrate.main(['--data-dir', str(tmp_path), '--yes']) == 0
    assert len(list((tmp_path / 'archive').glob('*-pre-trades-split'))) == 1


def test_split_requires_yes(tmp_path):
    _seed(tmp_path)
    assert migrate.main(['--data-dir', str(tmp_path)]) == 2
    assert not (tmp_path / 'spot_trades.json').exists()


def test_split_dry_run_does_not_write(tmp_path):
    _seed(tmp_path)
    assert migrate.main(['--data-dir', str(tmp_path), '--dry-run']) == 0
    assert not (tmp_path / 'spot_trades.json').exists()
    assert (tmp_path / 'top_trades.json').exists()
    assert (tmp_path / 'bottom_trades.json').exists()
