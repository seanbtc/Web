# -*- coding: utf-8 -*-
"""AHR999 数据源优先级与每日刷新调度测试（不依赖网络）。

实现已统一到 ``commons/ahr999.py``；这里验证 Web 侧调用与兜底行为。
"""
import os
import sys
from datetime import datetime, timezone

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(WEB_DIR)
for _path in (WEB_DIR, WORKSPACE_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import web  # noqa: E402
from commons import ahr999 as ahr999_impl  # noqa: E402


def _bars(count=200):
    start = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [
        [start + i * 86_400_000, '1', '1', '1', '100', '0',
         start + i * 86_400_000 + 86_399_999, '0', 0, '0', '0', '0']
        for i in range(count)
    ]


_BARS = _bars(200)
_DATAFEED_URL = f'{ahr999_impl._datafeed_url()}/klines'


def test_prefers_binance_spot_and_fetches_once(monkeypatch):
    calls = []

    def fake_get(url, params=None):
        calls.append(url)
        return _BARS

    monkeypatch.setattr(ahr999_impl, '_http_get_json', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert bars == _BARS
    assert source == 'binance_spot'
    assert stale is False
    assert calls == [ahr999_impl.SPOT_KLINES_URL]


def test_falls_back_to_datafeed_when_spot_fails(monkeypatch):
    calls = []

    def fake_get(url, params=None):
        calls.append(url)
        if url == ahr999_impl.SPOT_KLINES_URL:
            raise RuntimeError('spot down')
        if url == _DATAFEED_URL:
            return {'ok': True, 'stale': False, 'bars': _BARS}
        raise AssertionError(f'unexpected URL: {url}')

    monkeypatch.setattr(ahr999_impl, '_http_get_json', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert bars == _BARS
    assert source == 'datafeed'
    assert stale is False
    assert calls == [ahr999_impl.SPOT_KLINES_URL, _DATAFEED_URL]


def test_stale_datafeed_prefers_futures_fallback(monkeypatch):
    calls = []

    def fake_get(url, params=None):
        calls.append(url)
        if url == ahr999_impl.SPOT_KLINES_URL:
            raise RuntimeError('spot down')
        if url == _DATAFEED_URL:
            return {'ok': True, 'stale': True, 'bars': _BARS}
        if url == ahr999_impl.FUTURES_KLINES_URL:
            return _BARS
        raise AssertionError(f'unexpected URL: {url}')

    monkeypatch.setattr(ahr999_impl, '_http_get_json', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert source == 'binance_futures'
    assert stale is False
    assert calls == [
        ahr999_impl.SPOT_KLINES_URL,
        _DATAFEED_URL,
        ahr999_impl.FUTURES_KLINES_URL,
    ]


def test_insufficient_spot_bars_falls_back_to_datafeed(monkeypatch):
    def fake_get(url, params=None):
        if url == ahr999_impl.SPOT_KLINES_URL:
            return _bars(150)
        if url == _DATAFEED_URL:
            return {'ok': True, 'stale': False, 'bars': _BARS}
        raise AssertionError(f'unexpected URL: {url}')

    monkeypatch.setattr(ahr999_impl, '_http_get_json', fake_get)

    bars, source, stale = web._fetch_ahr999_bars()

    assert len(bars) == 200
    assert source == 'datafeed'
    assert stale is False


def test_web_uses_common_implementation():
    assert web.fetch_daily_klines is ahr999_impl.fetch_daily_klines
    assert web.fetch_ahr999 is ahr999_impl.fetch_ahr999


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
