# -*- coding: utf-8 -*-
"""一次性历史回填：为旧净头寸调整记录补“决策腿”字段（离线、幂等、自动备份）。

目标：order_id=1155109993906（2026-10-06 00:00:03 实盘平空 0.187@85220.3，
实为多头虚拟腿开仓驱动的净头寸缩仓；补 decision_leg_direction=long /
decision_leg_action=open / net_adjustment=true，其余字段保持）。

用法（在 Web 目录）：
  .venv\\Scripts\\python.exe tools\\backfill_legacy_decision.py [--dry-run] [--file data\\lead_trades.json]

特性：
- 不联网、不依赖 Web 服务；仅读写目标 JSON 文件。
- 幂等：字段已存在且值一致时不做任何修改（不写盘、不备份）。
- 写盘前自动备份原文件为 `<file>.bak-<UTC 时间戳>`；写盘为原子替换。
- --dry-run 仅打印将变更的字段，零写盘（不备份）。
退出码：0=已完成/已是最新；1=失败（文件缺失/解析失败/未找到 order_id）。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TARGET_ORDER_ID = '1155109993906'
TARGET_FIELDS = {
    'decision_leg_direction': 'long',
    'decision_leg_action': 'open',
    'net_adjustment': True,
}
WEB_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FILE = WEB_DIR / 'data' / 'lead_trades.json'


def apply_backfill(payload, order_id=TARGET_ORDER_ID, fields=None):
    """就地应用回填，返回 (changed, record, diffs)；record 为命中记录或 None。"""
    target_fields = dict(TARGET_FIELDS if fields is None else fields)
    if not isinstance(payload, dict):
        return False, None, {}
    records = payload.get('trade_records')
    if not isinstance(records, list):
        return False, None, {}
    record = next(
        (
            item for item in records
            if isinstance(item, dict) and str(item.get('order_id') or '') == str(order_id)
        ),
        None,
    )
    if record is None:
        return False, None, {}
    diffs = {}
    for key, value in target_fields.items():
        if record.get(key) != value:
            diffs[key] = (record.get(key), value)
    if not diffs:
        return False, record, {}
    for key, (_, new_value) in diffs.items():
        record[key] = new_value
    return True, record, diffs


def _backup_path(path):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    return path.with_name(f'{path.name}.bak-{stamp}')


def _write_json_atomic(path, payload):
    directory = str(path.parent) or '.'
    handle, temp_path = tempfile.mkstemp(prefix=f'{path.name}.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, str(path))
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise


def backfill_file(path, order_id=TARGET_ORDER_ID, dry_run=False, backup=True):
    """回填单个文件，返回结果 dict：ok/found/changed/backup/diffs/error。"""
    result = {'ok': False, 'found': False, 'changed': False, 'backup': '', 'diffs': {}, 'error': ''}
    path = Path(path)
    if not path.exists():
        result['error'] = f'文件不存在: {path}'
        return result
    try:
        with open(path, 'r', encoding='utf-8') as stream:
            payload = json.load(stream)
    except Exception as exc:
        result['error'] = f'读取失败: {exc}'
        return result

    changed, record, diffs = apply_backfill(payload, order_id=order_id)
    result['ok'] = True
    result['found'] = record is not None
    result['changed'] = changed
    result['diffs'] = diffs
    if record is None:
        result['error'] = f'未找到 order_id={order_id}'
        return result
    if not changed or dry_run:
        return result

    if backup:
        backup_path = _backup_path(path)
        shutil.copy2(path, backup_path)
        result['backup'] = str(backup_path)
    try:
        _write_json_atomic(path, payload)
    except Exception as exc:
        result['ok'] = False
        result['error'] = f'写盘失败: {exc}'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='一次性历史回填：为旧净头寸调整记录补决策腿字段（幂等、自动备份）。'
    )
    parser.add_argument('--file', default=str(DEFAULT_FILE), help='目标 lead_trades.json 路径')
    parser.add_argument('--order-id', default=TARGET_ORDER_ID, help=f'目标订单号（默认 {TARGET_ORDER_ID}）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不写盘不备份')
    args = parser.parse_args(argv)

    result = backfill_file(args.file, order_id=args.order_id, dry_run=args.dry_run)
    if not result['ok']:
        reason = result['error'] or ('未找到目标记录' if not result['found'] else '未知错误')
        print(f"[回填] 失败：{reason} (file={args.file})")
        return 1
    if not result['found']:
        print(f"[回填] 未找到 order_id={args.order_id}，未做修改 (file={args.file})")
        return 1
    if not result['changed']:
        print(f"[回填] 已是最新（幂等）：order_id={args.order_id} 无需修改")
        return 0
    for key in sorted(result['diffs']):
        old_value, new_value = result['diffs'][key]
        print(f"[回填]   {key}: {old_value!r} -> {new_value!r}")
    if args.dry_run:
        print(f"[回填] [dry-run] 仅预览，未写盘 (order_id={args.order_id})")
        return 0
    print(f"[回填] 完成：order_id={args.order_id}；备份：{result['backup']}")
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    sys.exit(main())
