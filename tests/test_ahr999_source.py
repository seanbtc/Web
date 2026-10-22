# -*- coding: utf-8 -*-
"""AHR999 数据源优先级与每日刷新调度测试（不依赖网络）。"""
import os
import sys
from datetime import datetime, timezone

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

import web  # noqa: E402


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


_BARS = [[
    1792454400000, '82000', '83000', '81000', '82984.8', '1',
    1792540799999, '0', 0, '0', '0', '0',
]]


def test_prefers_binance_spot_and_fetches_once(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        calls.append(url)
        return _Response(200, _BARS)

    monkeypatch.setattr(web.requests, 'get', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert bars == _BARS
    assert source == 'binance_spot'
    assert stale is False
    assert calls == [web.AHR999_SPOT_KLINES_URL]


def test_falls_back_to_datafeed_when_spot_fails(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        calls.append(url)
        if url == web.AHR999_SPOT_KLINES_URL:
            return _Response(503, {'msg': 'unavailable'})
        if url == f'{web._ahr999_datafeed_url}/klines':
            return _Response(200, {'ok': True, 'stale': False, 'bars': _BARS})
        raise AssertionError(f'unexpected URL: {url}')

    monkeypatch.setattr(web.requests, 'get', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert bars == _BARS
    assert source == 'datafeed'
    assert stale is False
    assert calls[0] == web.AHR999_SPOT_KLINES_URL
    assert calls[1] == f'{web._ahr999_datafeed_url}/klines'


def test_stale_datafeed_prefers_futures_fallback(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        calls.append(url)
        if url == web.AHR999_SPOT_KLINES_URL:
            return _Response(503, {'msg': 'unavailable'})
        if url == f'{web._ahr999_datafeed_url}/klines':
            return _Response(200, {'ok': True, 'stale': True, 'bars': _BARS})
        if url == web.AHR999_FUTURES_KLINES_URL:
            return _Response(200, _BARS)
        raise AssertionError(f'unexpected URL: {url}')

    monkeypatch.setattr(web.requests, 'get', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert bars == _BARS
    assert source == 'binance_futures'
    assert stale is False
    assert calls == [
        web.AHR999_SPOT_KLINES_URL,
        f'{web._ahr999_datafeed_url}/klines',
        web.AHR999_FUTURES_KLINES_URL,
    ]


@pytest.mark.parametrize(
    'now, expected',
    [
        (datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc), 300),
        (datetime(2026, 10, 21, 0, 5, tzinfo=timezone.utc), 86400),
        (datetime(2026, 10, 21, 23, 59, tzinfo=timezone.utc), 360),
    ],
)
def test_next_daily_refresh_is_utc_0005(now, expected):
    assert web._seconds_until_next_ahr999_refresh(now) == expected
