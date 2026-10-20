# -*- coding: utf-8 -*-
"""AHR999 独立估值指数（只读展示，不参与 AlphaEngine 决策）。

公式（社区标准口径）::

    币龄 = 估值日 - 2009-01-03
    指数增长估值 = 10 ** (5.84 * log10(币龄) - 17.01)
    200 日定投成本 = 最近 200 个已收盘日线收盘价的几何平均
    AHR999 = (收盘价 / 200 日成本) * (收盘价 / 指数增长估值)

说明：
- 仅使用 **已收盘** 的 UTC 日线，避免把当天未完成 K 线算进去；
- 200 日成本采用几何平均（社区多数实现口径）；同时返回 SMA 供核对；
- 数据不足 200 根、价格非法或日期异常时返回 ``available=False``，不抛异常。
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Iterable

GENESIS_DATE = date(2009, 1, 3)
COST_WINDOW = 200

# (上界, zone_key, 中文标签)；下界由上一档隐含，最小档为 <0.45。
_ZONE_DEFS = (
    (0.45, "bottom", "抄底区"),
    (1.2, "dca", "定投区"),
    (5.0, "caution", "等待起飞区"),
    (float("inf"), "bubble", "泡沫区"),
)


def zone_for(value: float) -> tuple[str, str]:
    """返回 (zone_key, 中文标签)。"""
    for upper, key, label in _ZONE_DEFS:
        if value < upper:
            return key, label
    return "bubble", "泡沫区"


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_ms(value: Any) -> int | None:
    """兼容秒/毫秒时间戳与数字字符串，返回毫秒。"""
    number = _to_float(value)
    if number is None or number <= 0:
        return None
    # 2001-09-09 之后的时间戳按毫秒处理；更小的按秒处理。
    if number < 10**11:
        number *= 1000
    return int(number)


def _bar_parts(bar: Any) -> tuple[int, int | None, float] | None:
    """把 DataFeed bar / Binance 12 列数组 / (ts, close) 统一成 (open_ms, close_ms, close)。"""
    if isinstance(bar, dict):
        open_ms = _to_ms(bar.get("open_time", bar.get("timestamp", bar.get("ts"))))
        close_ms = _to_ms(bar.get("close_time"))
        close = _to_float(bar.get("close"))
    elif isinstance(bar, (list, tuple)):
        if len(bar) >= 7:
            # Binance 12 列：open_time, open, high, low, close, volume, close_time...
            open_ms = _to_ms(bar[0])
            close = _to_float(bar[4])
            close_ms = _to_ms(bar[6])
        elif len(bar) >= 5:
            open_ms = _to_ms(bar[0])
            close = _to_float(bar[4])
            close_ms = None
        elif len(bar) == 2:
            open_ms = _to_ms(bar[0])
            close = _to_float(bar[1])
            close_ms = None
        else:
            return None
    else:
        return None

    if open_ms is None or close is None or close <= 0:
        return None
    return open_ms, close_ms, close


def compute_ahr999(
    bars: Iterable[Any],
    *,
    cost_mode: str = "gmean",
    now: datetime | None = None,
) -> dict:
    """从日线 bars 计算最新 AHR999。

    ``bars`` 支持 ``DataFeed /klines`` 的 bar dict、Binance 12 列数组或
    ``(timestamp, close)`` 二元组；仅保留已收盘日线，按 UTC 日期去重。

    返回字段：available/value/zone/zone_key/as_of/price/cost_200/fitted/
    ratio_cost/ratio_fit/cost_mode/samples/stale/error。
    """
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    now_ms = int(now_dt.timestamp() * 1000)

    by_date: dict[date, float] = {}
    for bar in bars or []:
        parts = _bar_parts(bar)
        if parts is None:
            continue
        open_ms, close_ms, close = parts
        # 未完成的当日 K 线：优先用 close_time，缺失时用 open_time + 1d。
        effective_close_ms = close_ms if close_ms is not None else open_ms + 86_400_000
        if effective_close_ms > now_ms:
            continue
        bar_date = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).date()
        if bar_date >= now_dt.date():
            continue
        by_date[bar_date] = close

    ordered = sorted(by_date.items())
    if len(ordered) < COST_WINDOW:
        return {
            "available": False,
            "error": f"日线不足 ({len(ordered)} < {COST_WINDOW})",
            "samples": len(ordered),
        }

    window = ordered[-COST_WINDOW:]
    closes = [item[1] for item in window]
    as_of_date = window[-1][0]
    price = closes[-1]

    logs = [math.log(value) for value in closes]
    gmean = math.exp(sum(logs) / COST_WINDOW)
    sma = sum(closes) / COST_WINDOW
    age_days = (as_of_date - GENESIS_DATE).days
    if age_days <= 0:
        return {
            "available": False,
            "error": f"币龄异常 ({age_days})",
            "samples": len(ordered),
        }
    fitted = 10 ** (5.84 * math.log10(age_days) - 17.01)

    mode = cost_mode if cost_mode in ("gmean", "sma") else "gmean"
    cost = gmean if mode == "gmean" else sma
    if cost <= 0 or fitted <= 0:
        return {
            "available": False,
            "error": "估值分母非法",
            "samples": len(ordered),
        }

    ratio_cost = price / cost
    ratio_fit = price / fitted
    value = ratio_cost * ratio_fit
    zone_key, zone = zone_for(value)
    stale = (now_dt.date() - as_of_date).days > 2

    return {
        "available": True,
        "value": round(value, 4),
        "zone": zone,
        "zone_key": zone_key,
        "as_of": as_of_date.isoformat(),
        "price": round(price, 2),
        "cost_200": round(cost, 2),
        "cost_200_sma": round(sma, 2),
        "fitted": round(fitted, 2),
        "ratio_cost": round(ratio_cost, 4),
        "ratio_fit": round(ratio_fit, 4),
        "cost_mode": mode,
        "samples": len(ordered),
        "window": COST_WINDOW,
        "stale": bool(stale),
        "error": "",
    }
