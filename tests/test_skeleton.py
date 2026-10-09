# -*- coding: utf-8 -*-
"""系统功能骨架页（/skeleton）测试：门禁保护 / 页面渲染 / 数据完整性 / 导航入口。"""
import os
import pathlib
import sys
from urllib.parse import unquote

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402
import system_map  # noqa: E402


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv('WEB_LOGIN_USERNAME', 'admin')
    monkeypatch.setenv('WEB_LOGIN_PASSWORD', 'test123')
    monkeypatch.delenv('WEB_LOGIN_PASSWORD_SHA256', raising=False)
    web._login_failures.clear()
    yield
    web._login_failures.clear()


@pytest.fixture()
def client():
    web.app.config['TESTING'] = True
    with web.app.test_client() as test_client:
        yield test_client


def _login(client):
    return client.post('/login', data={'username': 'admin', 'password': 'test123'})


def test_unauthenticated_skeleton_redirects_to_login(client):
    resp = client.get('/skeleton')
    assert resp.status_code == 302
    assert unquote(resp.headers['Location']).startswith('/login?next=/skeleton')


def test_authenticated_skeleton_renders(client):
    _login(client)
    resp = client.get('/skeleton')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for marker in ('系统功能骨架', '研究链路', 'BStrategy', 'Sentinel',
                   '规划中', '已退役', '返回面板', '主要链路',
                   'mermaid', 'flowchart TB', 'skSwitchView',
                   'sk-zoom-label', 'skZoomFit', 'flow-scroll',
                   'skInitPan', 'max-content'):
        assert marker in html, f'页面缺少标记: {marker}'


def test_system_map_integrity():
    assert system_map.validate() == []
    vm = system_map.view_model()
    assert vm['total_nodes'] > 0
    assert sum(item['count'] for item in vm['counts']) == vm['total_nodes']
    # 关键节点存在
    node_ids = {node['id'] for layer in vm['layers'] for node in layer['nodes']}
    for required in ('opencode', 'dingtalk', 'stage_a', 'bstrategy', 'sentinel', 'web'):
        assert required in node_ids
    # Mermaid 源码生成（含分层子图与边）
    mermaid = vm['mermaid']
    assert mermaid.startswith('%%{init')
    assert 'flowchart TB' in mermaid
    assert 'subgraph research' in mermaid
    assert 'stage_a --> stage_b' in mermaid
    assert 'classDef live' in mermaid


def test_index_links_to_skeleton():
    index_html = (pathlib.Path(WEB_DIR) / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'href="/skeleton"' in index_html
