# -*- coding: utf-8 -*-
"""「策略模块」盈亏归零（2026-10-18 用户裁定：盈亏归 0、只记盈亏）。

做法：在 lead_trades.json 的 summary 写入 `pnl_offset = -raw_total`，使展示口径的
`total_realized_pnl = raw_total + pnl_offset = 0`，此后新记录从 0 起累计；
历史记录与 archived 字段一律不动（可追溯、可逆：把 pnl_offset 改回 0 即恢复原口径）。

用法（在 Web 目录）：
  python3 tools/reset_lead_pnl_baseline.py [--dry-run] [--file data/lead_trades.json]

特性：离线、幂等（第二次运行不再写盘）、写盘前自动备份 `<file>.bak-<UTC>`、原子替换。
退出码：0=已归零/无需变更；1=失败。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def compute_reset(summary):
    """返回 {offset, raw}：写入后展示口径归零，且字段自洽（幂等）。"""
    summary = summary if isinstance(summary, dict) else {}
    try:
        displayed = float(summary.get('total_realized_pnl') or 0.0)
        offset = float(summary.get('pnl_offset') or 0.0)
    except (TypeError, ValueError):
        return None
    raw = summary.get('raw_total_realized_pnl')
    if raw is None:
        raw = displayed - offset
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None
    return {'offset': round(-raw, 4), 'raw': round(raw, 4)}


def compute_reset_offset(summary):
    """兼容旧接口：仅返回 offset。"""
    result = compute_reset(summary)
    return None if result is None else result['offset']


def _atomic_write(path, payload):
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description='策略模块盈亏归零（写入 pnl_offset）')
    parser.add_argument('--file', default=os.path.join('data', 'lead_trades.json'))
    parser.add_argument('--dry-run', action='store_true')
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
    summary = payload.get('summary') if isinstance(payload, dict) else None
    if not isinstance(summary, dict):
        print('summary 缺失或非法', file=sys.stderr)
        return 1

    target = compute_reset(summary)
    if target is None:
        print('无法解析 summary 数值字段', file=sys.stderr)
        return 1
    current = float(summary.get('pnl_offset') or 0.0)
    displayed = float(summary.get('total_realized_pnl') or 0.0)
    print(f'当前: 展示累计 {displayed:+.4f} | pnl_offset {current:+.4f} → 目标 offset {target["offset"]:+.4f}（raw {target["raw"]:+.4f}）')
    if abs(target['offset'] - current) < 1e-9:
        print('已归零（幂等），无需变更。')
        return 0
    if args.dry_run:
        print('[dry-run] 将写入 pnl_offset（不写盘）。')
        return 0

    backup = path.with_name(path.name + '.bak-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    shutil.copyfile(path, backup)
    summary['pnl_offset'] = target['offset']
    summary['raw_total_realized_pnl'] = target['raw']
    summary['total_realized_pnl'] = 0.0        # 自洽：展示归零（加载时按 raw + offset 重算）
    _atomic_write(path, payload)
    print(f'已写入 {path.name}（备份 {backup.name}）：展示累计将变为 0，后续记录从 0 起累计。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
