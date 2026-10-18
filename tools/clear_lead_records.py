# -*- coding: utf-8 -*-
"""「策略模块」历史订单清空（2026-10-18 用户裁定：全部清除，初始态记录后续订单）。

做法：将 `lead_trades.json` 重置为初始态：
    {"summary": {"initial_funds": 0.0, "archived_realized_pnl": 0.0, "pnl_offset": 0.0},
     "trade_records": []}
——记录清零、盈亏偏移/归档归零；后续（um）订单从零开始记录。
- 写盘前自动备份到 `<file 所在目录>/backups/<name>.<UTC>.json`（目录不入库）；
- 原子替换；幂等（已初始态时不再写盘/不再新增备份）；
- 默认 dry-run 语义由 `--dry-run` 控制；真正写入需显式 `--yes`（防误清）。

用法（Web 目录）：
  python3 tools/clear_lead_records.py --yes [--dry-run] [--file data/lead_trades.json]

退出码：0=已清空/本就为空；1=失败；2=缺少 --yes。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EMPTY_SUMMARY = {
    'initial_funds': 0.0,
    'archived_realized_pnl': 0.0,
    'pnl_offset': 0.0,
}


def build_empty_payload():
    return {'summary': dict(EMPTY_SUMMARY), 'trade_records': []}


def count_records(payload):
    records = payload.get('trade_records') if isinstance(payload, dict) else None
    return len(records) if isinstance(records, list) else 0


def is_initial_state(payload):
    """已是初始态：无记录且 summary 已归零。"""
    if not isinstance(payload, dict) or count_records(payload) != 0:
        return False
    summary = payload.get('summary') if isinstance(payload.get('summary'), dict) else {}
    for key, expected in EMPTY_SUMMARY.items():
        try:
            if abs(float(summary.get(key) or 0.0) - expected) > 1e-9:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _atomic_write(path, payload):
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _backup(path, backup_dir=None):
    directory = Path(backup_dir) if backup_dir else (path.parent / 'backups')
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = directory / f'{path.name}.{stamp}.json'
    shutil.copyfile(path, backup)
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description='策略模块历史订单清空（初始态）')
    parser.add_argument('--file', default=os.path.join('data', 'lead_trades.json'))
    parser.add_argument('--backup-dir', default='')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--yes', action='store_true', help='确认清空（未给则拒绝写入）')
    args = parser.parse_args(argv)

    path = Path(args.file).expanduser()
    if not path.is_file():
        print(f'文件不存在: {path}', file=sys.stderr)
        return 1
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'读取失败: {exc}', file=sys.stderr)
        return 1

    records = count_records(payload)
    summary = payload.get('summary') if isinstance(payload, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    displayed = summary.get('total_realized_pnl')
    print(f'当前: 记录 {records} 条 | 展示累计 {displayed} | initial_funds {summary.get("initial_funds")} '
          f'| archived {summary.get("archived_realized_pnl")} | pnl_offset {summary.get("pnl_offset")}')

    if is_initial_state(payload):
        print('已是初始态（幂等），无需变更。')
        return 0
    if args.dry_run:
        print(f'[dry-run] 将清空 {records} 条记录并把 summary 归零（不写盘）。')
        return 0
    if not args.yes:
        print('拒绝写入：请显式加 --yes 确认清空。', file=sys.stderr)
        return 2

    backup = _backup(path, args.backup_dir or None)
    _atomic_write(path, build_empty_payload())
    print(f'已清空 {path.name}（原 {records} 条记录 → 0；summary 归零）；备份: {backup}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
