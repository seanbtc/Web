import hashlib
import os
import sys
import time
from urllib.parse import quote, unquote, urlsplit

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402


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


def _login(client, username='admin', password='test123', **kwargs):
    return client.post('/login', data={'username': username, 'password': password}, **kwargs)


# --- 未登录访问 -------------------------------------------------------------

def test_unauthenticated_root_redirects_to_login(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/login')


def test_unauthenticated_data_file_redirects_with_next(client):
    resp = client.get('/data/x.json')
    assert resp.status_code == 302
    location = unquote(resp.headers['Location'])
    assert location.startswith('/login?next=/data/x.json')


def test_unauthenticated_read_api_returns_401_json(client):
    resp = client.get('/api/get_data')
    assert resp.status_code == 401
    assert resp.get_json()['status'] == 'error'


def test_unauthenticated_post_feed_api_returns_401(client):
    assert client.get('/api/get_post_feed').status_code == 401


# --- 免登录白名单 -----------------------------------------------------------

def test_health_and_static_are_not_redirected(client):
    health = client.get('/health')
    assert health.status_code == 200
    assert health.get_json()['ok'] is True

    static = client.get('/static/not-exists.css')
    assert static.status_code in (200, 404)


# --- 登录 / 登出 ------------------------------------------------------------

def test_login_wrong_credentials_returns_401(client):
    resp = _login(client, password='wrong')
    assert resp.status_code == 401
    assert '用户名或密码错误' in resp.get_data(as_text=True)
    assert client.get('/').status_code == 302


def test_login_success_sets_session_cookie_and_allows_root(client):
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/')
    assert 'session=' in resp.headers.get('Set-Cookie', '')

    assert client.get('/').status_code == 200
    assert client.get('/api/get_data').status_code == 200


def test_login_with_sha256_password(client, monkeypatch):
    monkeypatch.delenv('WEB_LOGIN_PASSWORD')
    monkeypatch.setenv(
        'WEB_LOGIN_PASSWORD_SHA256', hashlib.sha256(b'test123').hexdigest()
    )
    resp = _login(client)
    assert resp.status_code == 302
    assert client.get('/').status_code == 200


def test_login_next_safe_redirect(client):
    resp = client.post('/login?next=/data/x.json', data={'username': 'admin', 'password': 'test123'})
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/data/x.json'


UNSAFE_NEXT_VARIANTS = (
    '/\t/evil.com',
    '/\n/evil.com',
    '/\r/evil.com',
    '/\r\n/X:1',
    '/\x00/x',
    '/\x7f/x',
    '//evil.com',
    '/\\evil.com',
)


def test_login_next_rejects_control_char_variants(client):
    for variant in UNSAFE_NEXT_VARIANTS:
        resp = client.post(
            f'/login?next={quote(variant, safe="")}',
            data={'username': 'admin', 'password': 'test123'},
        )
        assert resp.status_code == 302, variant
        location = resp.headers['Location']
        assert location == '/', f'{variant!r} -> {location!r}'


def test_login_next_rejects_control_char_in_form(client):
    resp = client.post(
        '/login',
        data={'username': 'admin', 'password': 'test123', 'next': '/\n/evil.com'},
    )
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/'


def test_login_next_rejects_literal_encoded_crlf(client):
    resp = client.post(
        '/login',
        data={'username': 'admin', 'password': 'test123', 'next': '/%0D%0A%2FX:1'},
    )
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert not location.startswith('//')
    assert urlsplit(location).netloc == ''
    assert urlsplit(location).path.startswith('/')


def test_login_clears_previous_session_keys(client):
    with client.session_transaction() as sess:
        sess['pre_login'] = 'attacker'
    assert _login(client).status_code == 302
    with client.session_transaction() as sess:
        assert 'pre_login' not in sess
        assert sess['auth'] is True
        assert sess['user'] == 'admin'


def test_invalid_sha256_falls_back_to_plain(client, monkeypatch):
    monkeypatch.setenv('WEB_LOGIN_PASSWORD_SHA256', 'not-a-hex')
    assert _login(client).status_code == 302


def test_invalid_sha256_without_password_disables_login(client, monkeypatch):
    monkeypatch.delenv('WEB_LOGIN_PASSWORD')
    monkeypatch.setenv('WEB_LOGIN_PASSWORD_SHA256', 'not-a-hex')
    assert client.get('/').status_code == 200


def test_logout_clears_session(client):
    assert _login(client).status_code == 302
    assert client.get('/').status_code == 200

    resp = client.get('/logout')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/login')
    assert client.get('/').status_code == 302


# --- 登录节流 ---------------------------------------------------------------

def test_login_throttle_locks_after_5_failures(client):
    statuses = [_login(client, password='wrong').status_code for _ in range(5)]
    assert statuses == [401] * 5

    locked = _login(client, password='wrong')
    assert locked.status_code == 429
    assert '尝试次数过多' in locked.get_data(as_text=True)

    assert _login(client).status_code == 429


def test_login_lock_expires(client):
    for _ in range(5):
        _login(client, password='wrong')
    assert _login(client, password='wrong').status_code == 429

    ip = '127.0.0.1'
    web._login_failures[ip]['locked_until'] = time.time() - 1
    assert _login(client).status_code == 302


# --- 写接口衔接（保持各自 token 鉴权） ---------------------------------------

def test_unknown_api_add_route_is_not_released(client, monkeypatch):
    monkeypatch.setenv('WEB_API_TOKEN', 'test-token')
    resp = client.get('/api/add_bogus')
    assert resp.status_code == 401
    assert resp.get_json()['message'] == 'login required'


def test_write_api_without_token_uses_own_auth(client, monkeypatch):
    monkeypatch.setenv('WEB_API_TOKEN', 'test-token')
    resp = client.post('/api/update_market_data', json={})
    assert resp.status_code == 401
    assert resp.get_json()['message'] == 'unauthorized'


def test_write_api_with_token_passes_guard(client, monkeypatch):
    monkeypatch.setenv('WEB_API_TOKEN', 'test-token')
    resp = client.post(
        '/api/update_market_data', json={}, headers={'X-Webhook-Token': 'test-token'}
    )
    assert resp.status_code == 400
    assert resp.status_code not in (302, 401)


# --- 未配置密码保持旧行为 ---------------------------------------------------

def test_login_disabled_keeps_open_access(client, monkeypatch):
    monkeypatch.delenv('WEB_LOGIN_PASSWORD')
    monkeypatch.delenv('WEB_LOGIN_PASSWORD_SHA256', raising=False)
    assert client.get('/').status_code == 200
    assert client.get('/api/get_data').status_code == 200
    assert client.get('/data/whatever.json').status_code in (200, 404)


# --- Socket.IO 门禁 ---------------------------------------------------------

def test_socket_requires_login(client):
    anon = web.socketio.test_client(web.app)
    assert not anon.is_connected()

    assert _login(client).status_code == 302
    authed = web.socketio.test_client(web.app, flask_test_client=client)
    try:
        assert authed.is_connected()
        received = authed.get_received()
        assert any(message['name'] == 'all_data' for message in received)
    finally:
        authed.disconnect()
