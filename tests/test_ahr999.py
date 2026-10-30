# -*- coding: utf-8 -*-
"""AHR999 纯计算测试（不依赖网络/Web 进程）。"""
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from ahr999 import GENESIS_DATE, compute_ahr999, zone_for  # noqa: E402


def _bar(day: date, close: float) -> dict:
    open_ms = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
    return {
        'open_time': open_ms,
        'close_time': open_ms + 86_400_000 - 1,
        'close': str(close),
    }


def _bars(count: int, close: float = 100.0, start: date = date(2020, 1, 1)):
    return [_bar(start + timedelta(days=i), close) for i in range(count)]


def test_zone_boundaries():
    assert zone_for(0.44) == ('bottom', '抄底区')
    assert zone_for(0.45) == ('dca', '定投区')
    assert zone_for(1.19) == ('dca', '定投区')
    assert zone_for(1.2) == ('caution', '等待起飞区')
    assert zone_for(4.99) == ('caution', '等待起飞区')
    assert zone_for(5.0) == ('bubble', '泡沫区')


def test_compute_constant_close_matches_formula():
    bars = _bars(260)
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    result = compute_ahr999(bars, now=now)

    assert result['available'] is True
    assert result['samples'] == 260
    assert result['window'] == 200
    assert result['as_of'] == '2020-09-16'  # 2020-01-01 + 259 天
    assert result['price'] == 100.0
    assert result['cost_200'] == 100.0
    assert result['cost_mode'] == 'gmean'

    age = (date(2020, 9, 16) - GENESIS_DATE).days
    fitted = 10 ** (5.84 * math.log10(age) - 17.01)
    assert result['fitted'] == pytest.approx(round(fitted, 2), abs=0.01)
    assert result['value'] == pytest.approx(round(100.0 / fitted, 4), abs=0.0001)


def test_insufficient_bars_unavailable():
    result = compute_ahr999(_bars(199))
    assert result['available'] is False
    assert '199' in result['error']


def test_current_unfinished_bar_is_excluded():
    bars = _bars(200, close=100.0)
    today = date(2021, 1, 1)
    bars.append(_bar(today, 999.0))
    now = datetime(2021, 1, 1, 12, 0, tzinfo=timezone.utc)

    result = compute_ahr999(bars, now=now)
    assert result['available'] is True
    assert result['as_of'] == '2020-07-18'  # 200 根中的最后一根已完成日线
    assert result['price'] == 100.0


def test_binance_row_format_supported():
    bars = []
    for index in range(200):
        day = date(2020, 1, 1) + timedelta(days=index)
        open_ms = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
        close_ms = open_ms + 86_400_000 - 1
        bars.append([open_ms, '1', '1', '1', '100', '0', close_ms, '0', 0, '0', '0', '0'])

    result = compute_ahr999(bars, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert result['available'] is True
    assert result['as_of'] == '2020-07-18'
    assert result['cost_200'] == 100.0


def test_invalid_and_duplicate_bars_are_ignored():
    bars = _bars(200)
    bars.append({'open_time': 'bad', 'close': '100'})
    bars.append({'open_time': bars[0]['open_time'], 'close': '999'})  # 同日重复，后值覆盖
    result = compute_ahr999(bars, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert result['available'] is True
    assert result['samples'] == 200


def test_web_shim_uses_common_implementation():
    import ahr999 as shim
    from commons.ahr999 import compute_ahr999 as common_compute

    assert shim.compute_ahr999 is common_compute
