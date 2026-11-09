# -*- coding: utf-8 -*-
"""把旧 top_trades.json / bottom_trades.json 拆分为：

- spot_trades.json        现货模块（手工现货持仓 + 现货记录）
- bottom_top_trades.json  摸顶摸底模块：top=摸顶，bottom=摸底/AHR999

背景（2026-11-09）：旧 bottom_trades.json 同时承载「现货」和「AHR999/摸底」，
AHR999 数据只是被前端引用到摸顶摸底模块，数据本身仍混在现货文件里。
本脚本做一次真实归档/拆分：

1. 读取旧 top_trades.json / bottom_trades.json；
2. 旧文件移动到 data/archive/<UTC 时间>-pre-trades-split/（不删除）；
3. 写 spot_trades.json（现货字段 + 非 AHR999 记录）；
4. 写 bottom_top_trades.json（top=旧摸顶；bottom=ahr999 摘要 + AHR999 记录）；
5. 原子替换，权限 600；重复执行时若新文件已存在则 no-op。

用法（Web 目录）：
  python3 tools/migrate_trades_split.py --yes
  python3 tools/migrate_trades_split.py --data-dir data --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TOP = {
    'position_status': '空仓', 'position_side': '', 'position_quantity': 0.0,
    'position_avg_price': 0.0, 'position_symbol': 'BTCUSDT', 'trade_records': [],
}
DEFAULT_SPOT = {
    'position_status': '现货', 'position_quantity': 0.0, 'position_avg_price': 0.0,
    'position_symbol': 'BTCUSDT', 'status': '清仓', 'trade_records': [],
}
DEFAULT_BOTTOM = {'status': '清仓', 'ahr999': None, 'trade_records': []}


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(
        prefix=path.name + '.', suffix='.tmp', dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def _records(data: dict) -> list:
    records = data.get('trade_records')
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def is_ahr999_record(record: dict) -> bool:
    source = str(record.get('source') or '').strip().lower()
    plan_id = str(record.get('plan_id') or '').strip().lower()
    return source == 'ahr999_dca' or plan_id.startswith('ahr999_')


def split_payloads(top_old: dict, bottom_old: dict) -> tuple[dict, dict]:
    """返回 (spot, bottom_top)。"""
    spot = {key: bottom_old[key] for key in (
        'position_status', 'position_quantity', 'position_avg_price',
        'position_symbol', 'status',
    ) if key in bottom_old}
    spot.setdefault('position_status', DEFAULT_SPOT['position_status'])
    spot.setdefault('position_quantity', DEFAULT_SPOT['position_quantity'])
    spot.setdefault('position_avg_price', DEFAULT_SPOT['position_avg_price'])
    spot.setdefault('position_symbol', DEFAULT_SPOT['position_symbol'])
    spot.setdefault('status', DEFAULT_SPOT['status'])
    spot['trade_records'] = [r for r in _records(bottom_old) if not is_ahr999_record(r)]

    ahr999 = bottom_old.get('ahr999')
    ahr999 = dict(ahr999) if isinstance(ahr999, dict) else None
    bottom = {
        'status': (ahr999 or {}).get('status') or DEFAULT_BOTTOM['status'],
        'ahr999': ahr999,
        'trade_records': [r for r in _records(bottom_old) if is_ahr999_record(r)],
    }

    top = dict(DEFAULT_TOP)
    if isinstance(top_old, dict):
        for key, value in top_old.items():
            top[key] = value
    bottom_top = {'top': top, 'bottom': bottom}
    return spot, bottom_top


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='拆分 top/bottom 数据为 spot + bottom_top')
    default_data_dir = Path(__file__).resolve().parent.parent / 'data'
    parser.add_argument('--data-dir', default=str(default_data_dir))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--yes', action='store_true', help='确认写入并移动旧文件')
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    top_path = data_dir / 'top_trades.json'
    bottom_path = data_dir / 'bottom_trades.json'
    spot_path = data_dir / 'spot_trades.json'
    bottom_top_path = data_dir / 'bottom_top_trades.json'

    if not args.yes and not args.dry_run:
        print('需要 --yes 才会写入/移动文件（可先用 --dry-run 预览）', file=sys.stderr)
        return 2

    if spot_path.exists() and bottom_top_path.exists() and not top_path.exists() and not bottom_path.exists():
        print('已迁移：spot_trades.json + bottom_top_trades.json 已存在，旧文件不在 data 根目录')
        return 0

    top_old = _read_json(top_path)
    bottom_old = _read_json(bottom_path)
    spot, bottom_top = split_payloads(top_old, bottom_old)

    print(f'数据目录: {data_dir}')
    print(f'现货记录: {len(spot["trade_records"])} | AHR999/摸底记录: {len(bottom_top["bottom"]["trade_records"])} | '
          f'摸顶记录: {len(bottom_top["top"].get("trade_records") or [])} | '
          f'AHR999 摘要: {"有" if bottom_top["bottom"]["ahr999"] else "无"}')

    if args.dry_run:
        print('[dry-run] 未写文件、未移动旧文件')
        return 0

    archive_dir = data_dir / 'archive' / (
        datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-pre-trades-split'
    )
    archive_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    for old_path in (top_path, bottom_path):
        if old_path.exists():
            shutil.move(str(old_path), str(archive_dir / old_path.name))
            moved.append(old_path.name)

    _write_json_atomic(spot_path, spot)
    _write_json_atomic(bottom_top_path, bottom_top)
    print(f'已写入: {spot_path.name} ({spot_path.stat().st_size} bytes), '
          f'{bottom_top_path.name} ({bottom_top_path.stat().st_size} bytes)')
    if moved:
        print(f'旧文件已归档: {archive_dir} -> {moved}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
