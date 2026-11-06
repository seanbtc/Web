# -*- coding: utf-8 -*-
"""AutoDCA 计划摘要 → Web 摸顶摸底：AHR999 定投仓位独立展示。

背景（2026-11-06）：AutoDCA 每轮都会 POST /api/update_top_bottom，但该端点
原为占位实现；AHR999 实盘开仓后 Web 摸顶摸底模块看不到持仓。修复后只把
ahr999_ 计划的摘要写入 bottom_data['ahr999'] 子块，手工维护的现货持仓字段
（position_* / status / trade_records）保持不变。
"""
import json
import os
import sys

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')
os.environ.pop('WEB_API_TOKEN', None)

import web  # noqa: E402

import pytest  # noqa: E402


PAYLOAD = {
    'source': 'spot_dca',
    'plan_id': 'ahr999_bottom_btcusd1',
    'position_status': 'AHR999条件定投中 (剩余目标 2%/次)',
    'position_quantity': 0.0241,
    'position_avg_price': 76224.7,
    'position_symbol': 'BTCUSD1',
    'direction': 'long',
    'execution_mode': 'live',
    'execution_mode_text': '实盘运行',
    'dca_progress': 1.99,
    'remaining_quantity': 1.18532525,
    'next_due_time': '2026-11-07 08:10:00',
}

SPOT_BOTTOM = {
    'position_status': '现货',
    'position_quantity': 1.21,
    'position_avg_price': 80807,
    'position_symbol': 'BTCUSDT',
    'status': '满仓',
    'trade_records': [],
}


@pytest.fixture()
def client():
    web.app.config['TESTING'] = True
    with web.app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    return tmp_path


def test_summary_writes_ahr999_subblock_without_touching_spot(client, isolated_data_dir):
    web.data_storage.bottom_data = dict(SPOT_BOTTOM)

    resp = client.post('/api/update_top_bottom', json=PAYLOAD)

    assert resp.get_json() == {'status': 'success', 'updated': 1}
    bottom = web.data_storage.bottom_data
    assert bottom['position_status'] == '现货'
    assert bottom['position_quantity'] == pytest.approx(1.21)
    assert bottom['position_avg_price'] == pytest.approx(80807)
    assert bottom['status'] == '满仓'
    ahr999 = bottom['ahr999']
    assert ahr999['plan_id'] == 'ahr999_bottom_btcusd1'
    assert ahr999['position_quantity'] == pytest.approx(0.0241)
    assert ahr999['position_avg_price'] == pytest.approx(76224.7)
    assert ahr999['position_side'] == 'long'
    assert ahr999['symbol'] == 'BTCUSD1'
    assert ahr999['status'] == 'AHR999条件定投中 (剩余目标 2%/次)'
    assert ahr999['updated_at']

    saved = json.loads((isolated_data_dir / 'bottom_trades.json').read_text(encoding='utf-8'))
    assert saved['ahr999']['position_quantity'] == pytest.approx(0.0241)
    assert saved['position_quantity'] == pytest.approx(1.21)


def test_summary_ignores_non_ahr999_plan(client, isolated_data_dir):
    web.data_storage.bottom_data = dict(SPOT_BOTTOM)
    payload = dict(PAYLOAD, plan_id='btcusdc_dca', position_quantity=9.9)

    resp = client.post('/api/update_top_bottom', json=payload)

    assert resp.get_json() == {'status': 'success', 'updated': 0}
    assert 'ahr999' not in web.data_storage.bottom_data
    assert web.data_storage.bottom_data['position_quantity'] == pytest.approx(1.21)


def test_summary_dedupes_unchanged_payload(client, isolated_data_dir):
    web.data_storage.bottom_data = dict(SPOT_BOTTOM)

    assert client.post('/api/update_top_bottom', json=PAYLOAD).get_json()['updated'] == 1
    first = dict(web.data_storage.bottom_data['ahr999'])
    assert client.post('/api/update_top_bottom', json=PAYLOAD).get_json()['updated'] == 0
    assert web.data_storage.bottom_data['ahr999'] == first


def test_summary_rejects_non_object(client, isolated_data_dir):
    web.data_storage.bottom_data = dict(SPOT_BOTTOM)
    resp = client.post('/api/update_top_bottom', json=[PAYLOAD])
    assert resp.status_code == 400
    assert 'ahr999' not in web.data_storage.bottom_data


def test_template_places_ahr999_block_in_top_module(client):
    html = client.get('/').get_data(as_text=True)
    top_start = html.index('id="top-section"')
    bottom_start = html.index('id="bottom-section"')
    top_slice = html[top_start:bottom_start]
    legacy_start = html.index('id="top-bottom-section"')
    bottom_slice = html[bottom_start:legacy_start]

    assert '摸底策略 · AHR999 定投仓位' in top_slice
    assert 'bottom-ahr999-block' in top_slice
    for marker in (
        'bottom-ahr999-quantity',
        'bottom-ahr999-avg-price',
        'bottom-ahr999-float-profit',
        'bottom-ahr999-status',
        'bottom-ahr999-detail',
    ):
        assert marker in top_slice
    # 现货模块不再展示 AHR999 仓位
    assert 'bottom-ahr999-block' not in bottom_slice
    assert 'function updateAhr999Position' in html


def test_template_moves_ahr999_records_to_top_table(client):
    """AHR999 记录在摸顶摸底模块表格渲染，现货表格过滤掉。"""
    html = client.get('/').get_data(as_text=True)
    assert 'function isAhr999Record' in html
    assert "((data.bottom || {}).trade_records || []).filter(isAhr999Record)" in html
    assert ".filter(record => !isAhr999Record(record))" in html
    assert "source === 'ahr999_dca' || planId.startsWith('ahr999_')" in html
