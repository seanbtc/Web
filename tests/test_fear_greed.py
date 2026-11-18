# -*- coding: utf-8 -*-
"""恐惧与贪婪指数（Alternative.me）展示与回退测试。"""
import json
import os
import sys
import time

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.setattr(web, '_FEAR_GREED_CACHE', {'ts': 0.0, 'data': None})
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
    client.post('/login', data={'username': 'admin', 'password': 'test123'})


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_labels_and_css_bands():
    assert web.fear_greed_label(10, 'Extreme Fear') == '极度恐惧'
    assert web.fear_greed_label(30, 'Fear') == '恐惧'
    assert web.fear_greed_label(50, 'Neutral') == '中性'
    assert web.fear_greed_label(70, 'Greed') == '贪婪'
    assert web.fear_greed_label(90, 'Extreme Greed') == '极度贪婪'
    assert web.fear_greed_label(10) == '极度恐惧'
    assert web.fear_greed_label(90) == '极度贪婪'
    assert web.fear_greed_css_class(10) == 'fng-extreme-fear'
    assert web.fear_greed_css_class(30) == 'fng-fear'
    assert web.fear_greed_css_class(50) == 'fng-neutral'
    assert web.fear_greed_css_class(70) == 'fng-greed'
    assert web.fear_greed_css_class(90) == 'fng-extreme-greed'


def test_load_fear_greed_from_api(monkeypatch):
    calls = []

    def fetcher(url, timeout=4):
        calls.append((url, timeout))
        return _Response({'data': [{
            'value': '10', 'value_classification': 'Extreme Fear',
            'timestamp': '1700000000',
        }]})

    result = web.load_fear_greed(force=True, fetcher=fetcher)
    assert result['value'] == 10
    assert result['label'] == '极度恐惧'
    assert result['source'] == 'alternative.me'
    assert result['stale'] is False
    assert result['css_class'] == 'fng-extreme-fear'
    assert result['as_of'] == '2023-11-14'
    assert calls

    # 缓存命中：不再请求
    before = len(calls)
    again = web.load_fear_greed(fetcher=fetcher)
    assert again == result
    assert len(calls) == before


def test_load_fear_greed_falls_back_to_margin_state(tmp_path, monkeypatch):
    state = tmp_path / 'margin_monitor.json'
    state.write_text(json.dumps({
        'last_report': {'sentiment': {
            'value': 10, 'classification': 'Extreme Fear',
            'as_of': '2026-11-16', 'source': 'alternative.me',
        }}
    }), encoding='utf-8')
    monkeypatch.setattr(web, 'FEAR_GREED_MARGIN_STATE_FILE', str(state))
    monkeypatch.setattr(web, 'FEAR_GREED_CACHE_FILE', str(tmp_path / 'missing.csv.gz'))

    def failing(url, timeout=4):
        raise RuntimeError('network down')

    result = web.load_fear_greed(force=True, fetcher=failing)
    assert result['value'] == 10
    assert result['label'] == '极度恐惧'
    assert result['source'] == 'alternative.me'
    assert result['stale'] is True
    assert result['as_of'] == '2026-11-16'


def test_load_fear_greed_no_data_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'FEAR_GREED_MARGIN_STATE_FILE', str(tmp_path / 'missing.json'))
    monkeypatch.setattr(web, 'FEAR_GREED_CACHE_FILE', str(tmp_path / 'missing.csv.gz'))

    def failing(url, timeout=4):
        raise RuntimeError('network down')

    assert web.load_fear_greed(force=True, fetcher=failing) is None
    # 失败缓存 5 分钟内不再重试
    before = time.time()
    assert web.load_fear_greed(fetcher=failing) is None
    assert time.time() - before < 1


def test_fear_greed_api_requires_login(client):
    assert client.get('/api/fear_greed').status_code in (302, 401)


def test_fear_greed_api_returns_value(client, monkeypatch):
    monkeypatch.setattr(web, 'load_fear_greed', lambda *args, **kwargs: {
        'value': 10, 'label': '极度恐惧', 'css_class': 'fng-extreme-fear',
        'as_of': '2026-11-16', 'source': 'alternative.me', 'stale': False,
    })
    _login(client)
    response = client.get('/api/fear_greed')
    assert response.status_code == 200
    assert response.get_json()['value'] == 10


def test_index_contains_fear_greed_badge(client, tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'load_fear_greed', lambda *args, **kwargs: {
        'value': 10, 'label': '极度恐惧', 'css_class': 'fng-extreme-fear',
        'as_of': '2026-11-16', 'source': 'alternative.me', 'stale': False,
    })
    monkeypatch.setattr(web, 'MARGIN_STATE_FILE', str(tmp_path / 'missing.json'))
    monkeypatch.setattr(web, 'MARGIN_HEARTBEAT_FILE', str(tmp_path / 'missing.hb'))
    _login(client)
    html = client.get('/').get_data(as_text=True)
    assert 'id="fear-greed-value"' in html
    assert '10 · 极度恐惧' in html
    assert 'F&amp;G:' in html or 'F&G:' in html
