# -*- coding: utf-8 -*-
"""现货 / 摸顶摸底数据分文件（spot_trades.json + bottom_top_trades.json）。

2026-11-09 重构：
- 现货模块数据 → spot_trades.json
- 摸顶（top）+ 摸底/AHR999（bottom）→ bottom_top_trades.json
- AHR999 摘要/记录只写 bottom_top_trades.json 的 bottom 段，不再混在 spot
"""
import copy
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
    'position_quantity': 0.0478,
    'position_avg_price': 76068.61715481,
    'position_symbol': 'BTCUSD1',
    'direction': 'long',
    'execution_mode': 'live',
    'execution_mode_text': '实盘运行',
    'dca_progress': 3.95,
    'remaining_quantity': 1.16162525,
    'next_due_time': '2026-11-08 08:10:00',
}

SPOT_DATA = {
    'position_status': '现货',
    'position_quantity': 1.21,
    'position_avg_price': 80807,
    'position_symbol': 'BTCUSDT',
    'status': '满仓',
    'trade_records': [
        {'id': 1, 'mode': '现货', 'quantity': 1.206, 'avg_price': 81062.0,
         'is_closed': False, 'profit': 0.0},
    ],
}

BOTTOM_TOP_DATA = {
    'top': {
        'position_status': '空仓', 'position_side': '', 'position_quantity': 0.0,
        'position_avg_price': 0.0, 'position_symbol': 'BTCUSDT', 'trade_records': [],
    },
    'bottom': {'status': '清仓', 'ahr999': None, 'trade_records': []},
}


@pytest.fixture()
def client():
    web.app.config['TESTING'] = True
    with web.app.test_client() as test_client:
        yield test_client


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'data_dir', str(tmp_path))
    web.data_storage.spot_data = copy.deepcopy(SPOT_DATA)
    web.data_storage.bottom_top_data = copy.deepcopy(BOTTOM_TOP_DATA)
    yield tmp_path


def test_summary_writes_bottom_top_not_spot(client, isolated_data_dir):
    resp = client.post('/api/update_top_bottom', json=PAYLOAD)

    assert resp.get_json() == {'status': 'success', 'updated': 1}
    bottom = web.data_storage.bottom_top_data['bottom']
    assert bottom['ahr999']['plan_id'] == 'ahr999_bottom_btcusd1'
    assert bottom['ahr999']['position_quantity'] == pytest.approx(0.0478)
    assert bottom['ahr999']['position_avg_price'] == pytest.approx(76068.61715481)
    assert bottom['ahr999']['position_side'] == 'long'
    assert bottom['status'] == 'AHR999条件定投中 (剩余目标 2%/次)'
    # 现货、摸顶数据完全不动
    assert web.data_storage.spot_data == SPOT_DATA
    assert web.data_storage.bottom_top_data['top'] == BOTTOM_TOP_DATA['top']

    saved = json.loads((isolated_data_dir / 'bottom_top_trades.json').read_text(encoding='utf-8'))
    assert saved['bottom']['ahr999']['position_quantity'] == pytest.approx(0.0478)
    assert saved['top'] == BOTTOM_TOP_DATA['top']
    assert not (isolated_data_dir / 'spot_trades.json').exists()


def test_summary_ignores_non_ahr999_plan(client, isolated_data_dir):
    payload = dict(PAYLOAD, plan_id='btcusdc_dca', position_quantity=9.9)

    resp = client.post('/api/update_top_bottom', json=payload)

    assert resp.get_json() == {'status': 'success', 'updated': 0}
    assert web.data_storage.bottom_top_data['bottom']['ahr999'] is None
    assert web.data_storage.spot_data == SPOT_DATA


def test_summary_dedupes_unchanged_payload(client, isolated_data_dir):
    assert client.post('/api/update_top_bottom', json=PAYLOAD).get_json()['updated'] == 1
    first = dict(web.data_storage.bottom_top_data['bottom']['ahr999'])
    assert client.post('/api/update_top_bottom', json=PAYLOAD).get_json()['updated'] == 0
    assert web.data_storage.bottom_top_data['bottom']['ahr999'] == first


def test_add_ahr999_record_writes_bottom_top_only(client, isolated_data_dir):
    record = {
        'source': 'ahr999_dca', 'plan_id': 'ahr999_bottom_btcusd1', 'cycle_id': 1,
        'symbol': 'BTCUSD1', 'side': 'BUY', 'mode': '定投开仓',
        'quantity': 0.0241, 'avg_price': 76224.7, 'is_closed': False, 'profit': 0,
    }

    resp = client.post('/api/add_top_bottom_trade', json=record)
    assert resp.get_json() == {'status': 'success', 'added': True}
    assert len(web.data_storage.bottom_top_data['bottom']['trade_records']) == 1
    assert len(web.data_storage.spot_data['trade_records']) == 1  # 现货记录不变

    saved = json.loads((isolated_data_dir / 'bottom_top_trades.json').read_text(encoding='utf-8'))
    assert saved['bottom']['trade_records'][0]['source'] == 'ahr999_dca'
    assert not (isolated_data_dir / 'spot_trades.json').exists()
    # 重复记录去重
    assert client.post('/api/add_top_bottom_trade', json=record).get_json()['added'] is False


def test_update_spot_writes_spot_file_only(client, isolated_data_dir):
    resp = client.post('/api/update_spot', json={'status': '减仓', 'position_quantity': 1.0})

    assert resp.get_json() == {'status': 'success'}
    assert web.data_storage.spot_data['status'] == '减仓'
    assert web.data_storage.spot_data['position_quantity'] == pytest.approx(1.0)
    assert web.data_storage.bottom_top_data == BOTTOM_TOP_DATA
    saved = json.loads((isolated_data_dir / 'spot_trades.json').read_text(encoding='utf-8'))
    assert saved['status'] == '减仓'
    assert not (isolated_data_dir / 'bottom_top_trades.json').exists()


def test_update_top_writes_bottom_top_top(client, isolated_data_dir):
    resp = client.post('/api/update_top', json={
        'status': '持仓', 'position_quantity': 0.1, 'position_avg_price': 80000,
        'position_symbol': 'BTCUSDT', 'trade_records': [{'id': 1, 'mode': '做空'}],
    })

    assert resp.get_json() == {'status': 'success'}
    top = web.data_storage.bottom_top_data['top']
    assert top['status'] == '持仓'
    assert top['position_quantity'] == pytest.approx(0.1)
    assert web.data_storage.spot_data == SPOT_DATA
    saved = json.loads((isolated_data_dir / 'bottom_top_trades.json').read_text(encoding='utf-8'))
    assert saved['top']['status'] == '持仓'
    assert saved['top']['trade_records'][0]['mode'] == '做空'
    assert not (isolated_data_dir / 'spot_trades.json').exists()


def test_template_places_ahr999_block_in_top_module(client):
    html = client.get('/').get_data(as_text=True)
    top_start = html.index('id="top-section"')
    bottom_start = html.index('id="bottom-section"')
    legacy_start = html.index('id="top-bottom-section"')
    top_slice = html[top_start:bottom_start]
    bottom_slice = html[bottom_start:legacy_start]

    assert '摸底策略 · AHR999 定投仓位' in top_slice
    assert 'bottom-ahr999-block' in top_slice
    for marker in (
        'bottom-ahr999-quantity', 'bottom-ahr999-avg-price',
        'bottom-ahr999-float-profit', 'bottom-ahr999-status', 'bottom-ahr999-detail',
    ):
        assert marker in top_slice
    assert 'bottom-ahr999-block' not in bottom_slice


def test_template_uses_spot_and_bottom_top_data_keys(client):
    html = client.get('/').get_data(as_text=True)
    # 现货模块读 data.spot；AHR999/摸底读 data.bottom；摸顶读 data.top
    assert 'const spotData = data.spot || {};' in html
    assert 'const bottomData = data.bottom || {};' in html
    assert '(bottomData.trade_records || []).filter(isAhr999Record)' in html
    assert "setupStatusClick(bottomStatusEl, 'spot')" in html
    assert 'latestSpotData' in html
    assert 'latestBottomData' in html
    assert 'function isAhr999Record' in html
