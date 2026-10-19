# -*- coding: utf-8 -*-
"""博客路由：公开面 / 门禁边界 / 渲染 / 分页 / 降级（2026-10-19）。"""
import os
import sys
from urllib.parse import quote

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402


POST_A = """---
title: 第一篇
date: 2024-01-02 03:04:05
tags: pine, quant
categories: Android
---

第一段内容。

| 列 | 值 |
| --- | --- |
| a | 1 |

```python
print('hi')
```

![](/blog/assets/%E7%AC%AC%E4%B8%80%E7%AF%87/1.jpg)
"""

POST_B = """---
title: 第二篇
date: 2025-06-07 08:09:10
---

第二篇正文。
"""

POST_XSS = """---
title: <script>alert(1)</script>
date: 2023-05-05 05:05:05
---

正文。
"""


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv('WEB_LOGIN_USERNAME', 'admin')
    monkeypatch.setenv('WEB_LOGIN_PASSWORD', 'test123')
    monkeypatch.delenv('WEB_LOGIN_PASSWORD_SHA256', raising=False)
    monkeypatch.delenv('WEB_API_TOKEN', raising=False)
    web._login_failures.clear()
    yield
    web._login_failures.clear()


@pytest.fixture()
def client():
    web.app.config['TESTING'] = True
    with web.app.test_client() as test_client:
        yield test_client


def _make_blog(tmp_path, posts, assets=None):
    root = tmp_path / 'blog'
    (root / 'posts').mkdir(parents=True)
    for name, text in posts.items():
        (root / 'posts' / name).write_text(text, encoding='utf-8')
    for slug, files in (assets or {}).items():
        folder = root / 'assets' / slug
        folder.mkdir(parents=True)
        for file_name, data in files.items():
            (folder / file_name).write_bytes(data)
    return root


@pytest.fixture()
def blog(tmp_path, monkeypatch):
    root = _make_blog(tmp_path, {'第一篇.md': POST_A, '第二篇.md': POST_B},
                      assets={'第一篇': {'1.jpg': b'fake-jpg'}})
    monkeypatch.setattr(web, 'blog_dir', str(root))
    web._reset_blog_cache()
    yield root
    web._reset_blog_cache()


def _login(client):
    return client.post('/login', data={'username': 'admin', 'password': 'test123'})


# --- 公开访问（匿名） -------------------------------------------------------

def test_blog_list_public_and_sorted(client, blog):
    resp = client.get('/blog')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '共 2 篇' in html
    assert html.index('第二篇') < html.index('第一篇')  # 新的在前


def test_blog_post_public_renders(client, blog):
    resp = client.get('/blog/' + quote('第一篇'))
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<table>' in html                              # 表格
    assert 'codehilite' in html                           # 代码高亮容器
    assert '/blog/assets/%E7%AC%AC%E4%B8%80%E7%AF%87/1.jpg' in html  # 图片引用
    assert '第二篇' in html                                # 上/下篇导航（older）


def test_blog_asset_public(client, blog):
    resp = client.get('/blog/assets/' + quote('第一篇') + '/1.jpg')
    assert resp.status_code == 200
    assert resp.data == b'fake-jpg'


def test_blog_unknown_slug_404(client, blog):
    assert client.get('/blog/' + quote('不存在')).status_code == 404
    assert client.get('/blog/assets/' + quote('不存在') + '/1.jpg').status_code == 404


def test_blog_asset_traversal_rejected(client, blog):
    resp = client.get('/blog/assets/' + quote('第一篇') + '/../secret.txt')
    assert resp.status_code == 404


# --- 门禁边界 ---------------------------------------------------------------

def test_login_gate_boundaries_anonymous(client, blog):
    assert client.get('/').status_code == 302
    assert client.get('/data/x.json').status_code == 302
    assert client.get('/api/get_data').status_code == 401
    assert client.get('/blog').status_code == 200            # 公开
    assert client.get('/blog/' + quote('第一篇')).status_code == 200
    assert client.get('/blogfoo').status_code == 302          # 前缀边界：不放行


def test_blog_list_dashboard_link_requires_login(client, blog):
    assert '看板' not in client.get('/blog').get_data(as_text=True)

    _login(client)
    assert '看板' in client.get('/blog').get_data(as_text=True)


def test_dashboard_header_has_blog_link(client, blog):
    _login(client)
    html = client.get('/').get_data(as_text=True)
    assert 'href="/blog"' in html


# --- 分页 / 边界 ------------------------------------------------------------

def test_blog_pagination(client, tmp_path, monkeypatch):
    posts = {}
    for index in range(1, 26):
        posts[f'P{index:02d}.md'] = (
            f'---\ntitle: P{index:02d}\ndate: 2024-01-{index:02d} 00:00:00\n---\n正文\n')
    root = _make_blog(tmp_path, posts)
    monkeypatch.setattr(web, 'blog_dir', str(root))
    web._reset_blog_cache()

    page1 = client.get('/blog').get_data(as_text=True)
    assert '第 1 / 2 页' in page1 and 'P25' in page1
    page2 = client.get('/blog?page=2').get_data(as_text=True)
    assert '第 2 / 2 页' in page2
    # 越界与非法参数收敛
    assert '第 2 / 2 页' in client.get('/blog?page=99').get_data(as_text=True)
    assert '第 1 / 2 页' in client.get('/blog?page=abc').get_data(as_text=True)


def test_blog_empty_state(client, tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'blog_dir', str(tmp_path / 'empty-blog'))
    web._reset_blog_cache()
    resp = client.get('/blog')
    assert resp.status_code == 200
    assert '还没有文章' in resp.get_data(as_text=True)


# --- 转义 / 降级 ------------------------------------------------------------

def test_blog_title_escaped(client, tmp_path, monkeypatch):
    root = _make_blog(tmp_path, {'x.md': POST_XSS})
    monkeypatch.setattr(web, 'blog_dir', str(root))
    web._reset_blog_cache()
    html = client.get('/blog').get_data(as_text=True)
    assert '&lt;script&gt;' in html
    assert '<script>alert(1)</script>' not in html


def test_missing_markdown_dependency_raises(client, blog, monkeypatch):
    monkeypatch.setattr(web, '_markdown_module', None)
    with pytest.raises(RuntimeError):
        client.get('/blog/' + quote('第一篇'))
