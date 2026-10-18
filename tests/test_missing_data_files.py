# -*- coding: utf-8 -*-
"""R3（2026-10-18）：数据文件不入库后，全新克隆（data/ 为空）各加载器按默认空态返回。"""
import os
import sys

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402


@pytest.fixture()
def empty_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    return tmp_path


def test_lead_loaders_default_when_missing(empty_data_dir):
    lead = web.load_lead_data()
    assert lead['trade_records'] == []
    assert isinstance(lead['summary'], dict)
    # strict 模式在缺文件时同样返回默认（None 仅用于解析失败路径）
    assert web.load_lead_data(strict=True)['trade_records'] == []


def test_other_loaders_default_when_missing(empty_data_dir):
    assert web.load_total_profit_data()['trade_records'] == []
    assert web.load_triangle_data()['trade_records'] == []
    assert web.load_arbitrage_data()['trade_records'] == []
    assert web.load_top_data()['trade_records'] == []
    assert web.load_bottom_data()['trade_records'] == []
    assert web.load_promo_posts() == []
