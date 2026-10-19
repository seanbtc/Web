# -*- coding: utf-8 -*-
"""Hexo 博客导入工具（import_hexo_blog）：front matter / 围栏感知替换 / 引用修正 / 端到端（2026-10-19）。

另含「站内博客内容不变量」测试：对已导入的 blog/ 目录做 fence 感知的残留标签检查
与图片引用完整性检查（防后续人工新增文章时引入坏引用）。
"""
import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

WEB_DIR = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    'import_hexo_blog', str(WEB_DIR / 'tools' / 'import_hexo_blog.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def _write_source(tmp_path, posts, assets=None):
    src = tmp_path / 'source'
    src.mkdir(parents=True, exist_ok=True)
    for name, text in posts.items():
        (src / name).write_text(text, encoding='utf-8')
    for name, files in (assets or {}).items():
        folder = src / name
        folder.mkdir(exist_ok=True)
        for file_name, data in files.items():
            (folder / file_name).write_bytes(data)
    return src


def _post(title='标题', date='2024-01-02 03:04:05', tags='', categories='', body='正文'):
    lines = ['---', f'title: {title}', f'date: {date}']
    if tags:
        lines.append(f'tags: {tags}')
    if categories:
        lines.append(f'categories: {categories}')
    lines.extend(['---', body])
    return '\n'.join(lines)


# ---------- front matter ----------

def test_split_and_parse_front_matter():
    block, body = tool.split_front_matter('---\ntitle: T\ndate: 2024-01-01 00:00:00\n---\n正文')
    assert body == '正文'
    meta, warnings = tool.parse_front_matter(block)
    assert meta['title'] == 'T' and meta['date'] == '2024-01-01 00:00:00'
    assert warnings == []

    # 无 front matter
    block, body = tool.split_front_matter('直接正文')
    assert block is None and body == '直接正文'

    # 列表式 tags / 注释 / 空值
    meta, warnings = tool.parse_front_matter('tags:\n  - pine\n  - quant\nempty:\n# 注释')
    assert meta['tags'] == ['pine', 'quant']
    assert meta['empty'] == ''
    assert warnings == []


def test_normalize_tags():
    assert tool.normalize_tags('pine') == ['pine']
    assert tool.normalize_tags('pine, quant') == ['pine', 'quant']
    assert tool.normalize_tags(['a', 'b', 'a']) == ['a', 'b']
    assert tool.normalize_tags('') == []
    assert tool.normalize_tags(None) == []


# ---------- asset_img 替换 ----------

def _report():
    return {'missing_refs': []}


def test_convert_body_basic_and_placeholder():
    body = ('{% asset_img 1.jpg This is an example image %}\n'
            '{% asset_img 2.png 真实题注 %}\n')
    new, stats = tool.convert_body(body, '中文目录', {'1.jpg', '2.png'}, _report(), 'x.md')
    assert '![](/blog/assets/%E4%B8%AD%E6%96%87%E7%9B%AE%E5%BD%95/1.jpg)' in new
    assert '![真实题注](/blog/assets/%E4%B8%AD%E6%96%87%E7%9B%AE%E5%BD%95/2.png)' in new
    assert stats['replaced'] == 2
    assert stats['captions_dropped'] == 1
    assert stats['referenced'] == {'1.jpg', '2.png'}


def test_convert_body_fence_keeps_example():
    body = '```\n{% asset_img img1.png This is an example image %}\n```\n{% asset_img a.jpg %}\n'
    new, stats = tool.convert_body(body, 's', {'a.jpg'}, _report(), 'x.md')
    assert '{% asset_img img1.png' in new          # 围栏内原样保留
    assert '![](/blog/assets/s/a.jpg)' in new
    assert stats['replaced'] == 1
    assert stats['code_examples'] == 1


def test_convert_body_extension_fix_and_ambiguous():
    report = _report()
    # 唯一候选 → 扩展名修正
    new, stats = tool.convert_body('{% asset_img 1.png %}\n', 's', {'1.jpg'}, report, 'x.md')
    assert '![](/blog/assets/s/1.jpg)' in new
    assert stats['fixed'] == ['1.png → 1.jpg']
    # 多候选 → 歧义，独立行 → 移除并记录
    new, stats = tool.convert_body(
        '{% asset_img 2.png %}\n', 's', {'2.jpg', '2.gif'}, report, 'x.md')
    assert '2.png' not in new
    assert stats['removed'] and not stats['unresolved']
    # 行内嵌入 → 保留原样并记 unresolved
    new, stats = tool.convert_body('前文 {% asset_img 3.png %} 后文\n', 's', set(), report, 'x.md')
    assert '{% asset_img 3.png %}' in new
    assert stats['unresolved']
    assert report['missing_refs']


def test_convert_body_malformed_line():
    body = ('{% asset_img img1.jpg)\n'
            '运行结果：\n')
    new, stats = tool.convert_body(body, 's', {'img1.jpg'}, _report(), 'x.md')
    assert '![](/blog/assets/s/img1.jpg)' in new
    assert stats['malformed'] == ['{% asset_img img1.jpg)']
    assert stats['replaced'] == 1


# ---------- 端到端 ----------

def test_main_end_to_end(tmp_path, capsys):
    src = _write_source(
        tmp_path,
        {'第一篇.md': _post(title='第一篇', tags='pine', categories='Android',
                          body='{% asset_img 1.jpg This is an example image %}'),
         '第二篇.md': _post(title='第二篇', body='无图正文')},
        assets={'第一篇': {'1.jpg': b'fake-jpg'}},
    )
    out = tmp_path / 'blog'
    assert tool.main(['--source', str(src), '--out', str(out)]) == 0
    posts = sorted(p.name for p in (out / 'posts').glob('*.md'))
    assert posts == ['第一篇.md', '第二篇.md']
    text = (out / 'posts' / '第一篇.md').read_text(encoding='utf-8')
    assert 'title: 第一篇' in text
    assert 'tags: pine' in text
    assert 'categories: Android' in text
    assert '![](/blog/assets/%E7%AC%AC%E4%B8%80%E7%AF%87/1.jpg)' in text
    assert (out / 'assets' / '第一篇' / '1.jpg').read_bytes() == b'fake-jpg'
    report = json.loads((out / 'import_report.json').read_text(encoding='utf-8'))
    assert report['posts_total'] == 2 and report['posts_converted'] == 2
    assert report['asset_img_replaced'] == 1
    assert report['unresolved_refs'] == []
    assert '丢弃的 front matter 键' not in capsys.readouterr().out


def test_main_dry_run_writes_nothing(tmp_path):
    src = _write_source(tmp_path, {'a.md': _post(body='{% asset_img x.jpg %}')},
                        assets={'a': {'x.jpg': b'1'}})
    out = tmp_path / 'blog'
    assert tool.main(['--source', str(src), '--out', str(out), '--dry-run']) == 0
    assert not out.exists()


def test_main_refuses_nonempty_out_without_force(tmp_path):
    src = _write_source(tmp_path, {'a.md': _post()})
    out = tmp_path / 'blog'
    (out / 'posts').mkdir(parents=True)
    (out / 'posts' / 'old.md').write_text('old', encoding='utf-8')
    assert tool.main(['--source', str(src), '--out', str(out)]) == 1
    assert tool.main(['--source', str(src), '--out', str(out), '--force']) == 0


def test_main_unresolved_inline_returns_2(tmp_path):
    src = _write_source(tmp_path, {'a.md': _post(body='文字 {% asset_img nope.jpg %} 文字')})
    out = tmp_path / 'blog'
    assert tool.main(['--source', str(src), '--out', str(out)]) == 2
    report = json.loads((out / 'import_report.json').read_text(encoding='utf-8'))
    assert len(report['unresolved_refs']) == 1


# ---------- 站内内容不变量（对已导入的 blog/ 目录） ----------

BLOG_POSTS_DIR = WEB_DIR / 'blog' / 'posts'
BLOG_ASSETS_DIR = WEB_DIR / 'blog' / 'assets'


@pytest.mark.skipif(not BLOG_POSTS_DIR.is_dir(), reason='blog 内容未导入')
def test_imported_content_invariants():
    posts = sorted(BLOG_POSTS_DIR.glob('*.md'))
    assert len(posts) >= 90

    problems = []
    for path in posts:
        fence = None
        for number, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
            fence_match = tool.FENCE_RE.match(line)
            if fence_match:
                char = fence_match.group(1)[0]
                if fence is None:
                    fence = char
                elif char == fence:
                    fence = None
                continue
            if fence is None and '{%' in line:
                problems.append(f'{path.name}:{number} 残留标签: {line.strip()[:80]}')
    assert problems == [], '\n'.join(problems)


@pytest.mark.skipif(not BLOG_POSTS_DIR.is_dir(), reason='blog 内容未导入')
def test_imported_asset_links_resolve():
    missing = []
    for path in sorted(BLOG_POSTS_DIR.glob('*.md')):
        text = path.read_text(encoding='utf-8')
        for url in re.findall(r'\]\(/blog/assets/([^)\s]+)\)', text):
            rel = unquote(url)
            if not (BLOG_ASSETS_DIR / rel).is_file():
                missing.append(f'{path.name}: {rel}')
    assert missing == [], '\n'.join(missing)
