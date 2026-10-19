#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性工具：把 Hexo 博客文章与附件导入 Web 站内内容结构。

源（只读）：`<hexo>/source/_posts/` —— `*.md` + 同名附件夹（post_asset_folder）。
目标：`<out>/posts/*.md`（转换后） + `<out>/assets/<slug>/*`（附件原样复制）。

转换规则（与迁移方案一致，2026-10-19）：
- front matter：保留 title/date/tags；其余键丢弃并记录；
- `{% asset_img FILE [title] %}` → `![title](/blog/assets/<slug>/<FILE>)`；
  * **代码块（```/~~~ 围栏）内的原样保留**（如教学文章里的语法示例）；
  * 标题为脚手架占位 "This is an example image" 时置空；
  * 路径片段 percent-encode（中文/特殊字符/括号等）；
- 引用完整性：每个 asset_img 目标必须存在于同名词附件夹，缺失 → 报错退出（绝不静默）；
- 未出现的附件文件照常复制，报告列出（info）；
- slug = 文件名（去 .md），全量唯一性校验（大小写不敏感）。

只依赖标准库。用法::

    python3 tools/import_hexo_blog.py --source /path/to/hexo/source/_posts --out blog [--dry-run] [--force]

退出码：0 成功；1 致命错误（源目录/输出目录问题）；2 存在缺失引用。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from urllib.parse import quote

PLACEHOLDER_TITLE = 'this is an example image'
KEEP_KEYS = ('title', 'date', 'tags', 'categories')

FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')
ASSET_IMG_RE = re.compile(
    r'\{%\s*asset_img\s+(?P<file>\S+)(?:\s+(?P<title>.*?))?\s*%\}'
)
# 畸形变体（源站笔误，缺 "%}"）：整行恰为 `{% asset_img FILE)` 形态
MALFORMED_RE = re.compile(r'^\s*\{%\s*asset_img\s+(?P<file>\S+?)\s*\)\s*$')


def read_text(path):
    with open(path, 'r', encoding='utf-8-sig') as handle:
        return handle.read()


def split_front_matter(text):
    """返回 (front_matter_block 或 None, body)。仅识别文件开头的 '---' 块。"""
    text = text.lstrip('\ufeff')
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == '---':
            return '\n'.join(lines[1:index]), '\n'.join(lines[index + 1:])
    return None, text


def _strip_quotes(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_front_matter(block):
    """解析 Hexo 常见 front matter 子集；返回 (meta, warnings)。

    支持 `key: scalar`、空值、以及 `key:` 后的 `- item` 列表行；其余形态记警告。
    """
    meta = {}
    warnings = []
    current_key = None
    for raw_line in (block or '').split('\n'):
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith('#'):
            continue
        if line.lstrip().startswith('- '):
            item = _strip_quotes(line.lstrip()[2:])
            if current_key is None:
                warnings.append(f'孤立列表项: {line!r}')
                continue
            existing = meta.get(current_key, '')
            if isinstance(existing, list):
                existing.append(item)
            elif existing:
                meta[current_key] = [existing, item]
            else:
                meta[current_key] = [item]
            continue
        if ':' not in line:
            warnings.append(f'无法解析的 front matter 行: {line!r}')
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = _strip_quotes(value)
        if value in ('>', '|', '>-', '|-'):
            warnings.append(f'多行块标量未支持（key={key}），按空处理')
            value = ''
        meta[key] = value
        current_key = key
    return meta, warnings


def normalize_tags(value):
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).split(',')
    tags = []
    for item in raw:
        item = str(item).strip()
        if item and item not in tags:
            tags.append(item)
    return tags


def resolve_asset_file(file_name, available):
    """解析引用：返回 (实际文件名, 修正说明或 None)；无法解析返回 (None, 'missing')。

    修正策略：引用名不存在、但同名词不同扩展名的唯一候选存在 → 视为笔误修正
    （实测源站有 8 处 .png/.jpg 写反；多个候选视为歧义，不猜）。
    """
    if file_name in available:
        return file_name, None
    stem, _ = os.path.splitext(file_name)
    candidates = sorted(
        name for name in available
        if os.path.splitext(name)[0] == stem and name != file_name
    )
    if len(candidates) == 1:
        return candidates[0], f'扩展名修正 {file_name} → {candidates[0]}'
    return None, 'missing'


def convert_body(body, slug, available, report, slug_name):
    """围栏感知地替换 asset_img；返回 (新 body, 统计)。

    - 代码块（```/~~~）内原样保留（教学示例）；
    - 不可解析引用：整行独立成标签 → 移除该行并记录；行内嵌入 → 保留并记录（触发退出码 2）。
    """
    stats = {'replaced': 0, 'captions_dropped': 0, 'referenced': set(),
             'code_examples': 0, 'fixed': [], 'malformed': [], 'removed': [], 'unresolved': []}
    out_lines = []
    fence_char = None

    def repl(match):
        file_name = match.group('file').strip()
        while file_name.startswith('./'):
            file_name = file_name[2:]
        resolved, fix_note = resolve_asset_file(file_name, available)
        title = (match.groupdict().get('title') or '').strip()
        if title.lower() == PLACEHOLDER_TITLE:
            title = ''
            stats['captions_dropped'] += 1
        if resolved is None:
            report['missing_refs'].append(f'{slug_name} → {file_name}')
            return match.group(0)  # 原样保留，由外层决定移除/残留
        if fix_note:
            stats['fixed'].append(f'{file_name} → {resolved}')
        stats['replaced'] += 1
        stats['referenced'].add(resolved)
        return f'![{title}](/blog/assets/{quote(slug, safe="")}/{quote(resolved, safe="")})'

    for line in body.split('\n'):
        fence_match = FENCE_RE.match(line)
        if fence_match:
            char = fence_match.group(1)[0]
            if fence_char is None:
                fence_char = char
            elif char == fence_char:
                fence_char = None
            out_lines.append(line)
            continue
        if fence_char is not None:
            if '{%' in line:
                stats['code_examples'] += 1
            out_lines.append(line)
            continue
        if '{%' in line:
            line = ASSET_IMG_RE.sub(repl, line)
            if '{%' in line:
                replaced_line = MALFORMED_RE.sub(repl, line)
                if replaced_line != line:
                    stats['malformed'].append(line.strip())
                line = replaced_line
            if '{%' in line:
                stripped = line.strip()
                if (stripped.count('{%') == 1 and stripped.startswith('{%')
                        and stripped.endswith('%}')):
                    stats['removed'].append(stripped)
                    continue
                stats['unresolved'].append(stripped)
        out_lines.append(line)
    return '\n'.join(out_lines), stats


def build_front_matter(meta, warnings, slug):
    title = str(meta.get('title') or '').strip() or slug
    if not str(meta.get('title') or '').strip():
        warnings.append('缺少 title，回退文件名为标题')
    lines = ['---', f'title: {title}']
    date = str(meta.get('date') or '').strip()
    if date:
        lines.append(f'date: {date}')
    else:
        warnings.append('缺少 date')
    tags = normalize_tags(meta.get('tags'))
    if tags:
        lines.append('tags: ' + ', '.join(tags))
    categories = normalize_tags(meta.get('categories'))
    if categories:
        lines.append('categories: ' + ', '.join(categories))
    lines.append('---')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Hexo 博客 → Web 站内内容导入（一次性）')
    parser.add_argument('--source', required=True, help='Hexo source/_posts 目录')
    parser.add_argument('--out', default='blog', help='输出目录（默认 ./blog）')
    parser.add_argument('--dry-run', action='store_true', help='只报告，不写任何文件')
    parser.add_argument('--force', action='store_true', help='输出目录已有内容时覆盖')
    parser.add_argument('--report', default='', help='报告 JSON 路径（默认 <out>/import_report.json）')
    args = parser.parse_args(argv)

    source = os.path.abspath(args.source)
    out = os.path.abspath(args.out)
    posts_out = os.path.join(out, 'posts')
    assets_out = os.path.join(out, 'assets')

    if not os.path.isdir(source):
        print(f'[错误] 源目录不存在: {source}', file=sys.stderr)
        return 1
    if not args.dry_run and os.path.isdir(posts_out) and os.listdir(posts_out) and not args.force:
        print(f'[错误] 输出目录已有内容: {posts_out}（如确认覆盖请加 --force）', file=sys.stderr)
        return 1

    report = {
        'source': source, 'out': out, 'dry_run': bool(args.dry_run),
        'posts_total': 0, 'posts_converted': 0, 'posts_without_asset_dir': 0,
        'asset_dirs': 0, 'asset_files_copied': 0,
        'asset_img_replaced': 0, 'captions_dropped': 0, 'code_block_examples_kept': 0,
        'missing_refs': [], 'fixed_refs': [], 'removed_refs': [], 'unresolved_refs': [],
        'unreferenced_files': [], 'dropped_meta_keys': {},
        'warnings': [], 'posts': [],
    }
    seen_slugs = {}

    names = sorted(
        name for name in os.listdir(source)
        if name.endswith('.md') and os.path.isfile(os.path.join(source, name))
    )
    unexpected = sorted(
        name for name in os.listdir(source)
        if not name.startswith('.') and not name.endswith('.md')
        and not os.path.isdir(os.path.join(source, name))
    )
    for name in unexpected:
        report['warnings'].append(f'源目录顶层出现非 md 文件: {name}')

    for name in names:
        slug = name[:-3]
        lower = slug.lower()
        if lower in seen_slugs:
            report['warnings'].append(f'slug 冲突: {slug} vs {seen_slugs[lower]}')
        seen_slugs[lower] = slug

    for name in names:
        slug = name[:-3]
        report['posts_total'] += 1
        text = read_text(os.path.join(source, name))
        meta_block, body = split_front_matter(text)
        meta, warnings = parse_front_matter(meta_block)
        for key in meta:
            if key not in KEEP_KEYS:
                report['dropped_meta_keys'][key] = report['dropped_meta_keys'].get(key, 0) + 1
        for warning in warnings:
            report['warnings'].append(f'{name}: {warning}')

        asset_dir = os.path.join(source, slug)
        asset_files = []
        if os.path.isdir(asset_dir):
            report['asset_dirs'] += 1
            for root, _, files in os.walk(asset_dir):
                for file_name in files:
                    if file_name == '.DS_Store':
                        continue
                    rel = os.path.relpath(os.path.join(root, file_name), asset_dir)
                    asset_files.append(rel.replace(os.sep, '/'))
        else:
            report['posts_without_asset_dir'] += 1
        available = set(asset_files)

        new_body, stats = convert_body(body, slug, available, report, name)
        report['asset_img_replaced'] += stats['replaced']
        report['captions_dropped'] += stats['captions_dropped']
        report['code_block_examples_kept'] += stats['code_examples']
        for item in stats['fixed']:
            report['fixed_refs'].append(f'{slug}: {item}')
        for item in stats['malformed']:
            report['fixed_refs'].append(f'{slug}: 畸形语法修正: {item}')
        for item in stats['removed']:
            report['removed_refs'].append(f'{slug}: {item}')
        for item in stats['unresolved']:
            report['unresolved_refs'].append(f'{slug}: {item}')
        for file_name in sorted(available):
            if file_name not in stats['referenced']:
                report['unreferenced_files'].append(f'{slug}/{file_name}')

        post_meta = {'slug': slug, 'title': str(meta.get('title') or slug),
                     'date': str(meta.get('date') or ''), 'tags': normalize_tags(meta.get('tags')),
                     'categories': normalize_tags(meta.get('categories')),
                     'assets': len(asset_files), 'replaced': stats['replaced']}
        report['posts'].append(post_meta)

        if not args.dry_run:
            os.makedirs(posts_out, exist_ok=True)
            front = build_front_matter(meta, warnings, slug)
            target = os.path.join(posts_out, f'{slug}.md')
            with open(target, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(front + '\n' + new_body)
            if asset_files:
                shutil.copytree(asset_dir, os.path.join(assets_out, slug), dirs_exist_ok=True)
                report['asset_files_copied'] += len(asset_files)
            report['posts_converted'] += 1

    print('=' * 64)
    print(f"源目录: {source}")
    print(f"输出目录: {out}{'（dry-run，未写入）' if args.dry_run else ''}")
    print(f"文章: {report['posts_total']} 篇；asset_img 替换 {report['asset_img_replaced']} 处"
          f"（代码块内保留 {report['code_block_examples_kept']} 处；占位标题置空 {report['captions_dropped']}）")
    print(f"附件夹: {report['asset_dirs']} 个；附件文件复制 {report['asset_files_copied']}"
          f"（dry-run 为 0）；无附件夹文章 {report['posts_without_asset_dir']} 篇")
    print(f"未引用附件: {len(report['unreferenced_files'])} 个")
    for item in report['unreferenced_files']:
        print(f"  - {item}")
    if report['fixed_refs']:
        print(f"引用修正: {len(report['fixed_refs'])} 处（扩展名笔误/畸形语法）")
        for item in report['fixed_refs']:
            print(f"  - {item}")
    if report['missing_refs']:
        print(f"缺失引用: {len(report['missing_refs'])} 处")
        for item in report['missing_refs']:
            print(f"  - {item}")
    if report['removed_refs']:
        print(f"不可解析引用（独立行，已移除并留痕）: {len(report['removed_refs'])} 处")
        for item in report['removed_refs']:
            print(f"  - {item}")
    if report['unresolved_refs']:
        print(f"未解析引用（行内，保留原样）: {len(report['unresolved_refs'])} 处 → 退出码 2")
        for item in report['unresolved_refs']:
            print(f"  - {item}")
    if report['dropped_meta_keys']:
        print('丢弃的 front matter 键: ' + ', '.join(
            f'{key}×{count}' for key, count in sorted(report['dropped_meta_keys'].items())))
    if report['warnings']:
        print(f"警告: {len(report['warnings'])} 条")
        for item in report['warnings'][:20]:
            print(f"  - {item}")
    print('=' * 64)

    if not args.dry_run:
        report_path = args.report or os.path.join(out, 'import_report.json')
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f'报告已写入: {report_path}')

    if report['unresolved_refs']:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
