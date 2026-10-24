# -*- coding: utf-8 -*-
"""/api/update_network：relationships 推送数据文件，无需重启 Web。"""
import json
import os
import sys

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)
for key in ('WEB_LOGIN_PASSWORD', 'WEB_LOGIN_PASSWORD_SHA256'):
    os.environ.pop(key, None)

import web  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    monkeypatch.delenv('NETWORK_GRAPH_FILE', raising=False)
    return tmp_path


def sample(nodes=2):
    return {
        'generated_at': '2026-10-24T00:00:00+08:00',
        'nodes': [{'id': i, 'name': f'P{i}'} for i in range(nodes)],
        'edges': [],
    }


def test_update_network_writes_file(data_dir):
    client = web.app.test_client()
    resp = client.post('/api/update_network', json=sample(3))
    assert resp.status_code == 200
    assert resp.get_json()['nodes'] == 3
    saved = json.loads((data_dir / 'network.json').read_text(encoding='utf-8'))
    assert len(saved['nodes']) == 3
    # /network/data.json 立刻可读（无需重启）
    data = client.get('/network/data.json').get_json()
    assert len(data['nodes']) == 3


def test_update_network_rejects_invalid_payload(data_dir):
    client = web.app.test_client()
    assert client.post('/api/update_network', json={'foo': 1}).status_code == 400
    assert client.post('/api/update_network', data='not json',
                       content_type='application/json').status_code == 400


def test_update_network_requires_token(data_dir, monkeypatch):
    client = web.app.test_client()
    monkeypatch.setenv('WEB_API_TOKEN', 'secret-token')
    assert client.post('/api/update_network', json=sample()).status_code == 401
    ok = client.post('/api/update_network', json=sample(),
                     headers={'Authorization': 'Bearer secret-token'})
    assert ok.status_code == 200
    assert (data_dir / 'network.json').exists()
