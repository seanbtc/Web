import json
import os
import sys

import pytest

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

os.environ.setdefault('WEB_DISABLE_EVENTLET', '1')
os.environ.setdefault('WEB_SESSION_SECRET', 'test-session-secret')

import web  # noqa: E402


@pytest.fixture()
def state_file(tmp_path, monkeypatch):
    path = tmp_path / 'state.json'
    monkeypatch.setattr(web, 'alpha_engine_state_file', str(path))
    return path


def _write_state(path, payload):
    path.write_text(json.dumps(payload), encoding='utf-8')


# --- load_alpha_engine_ma: 容错 -------------------------------------------------

def test_load_ma_missing_file_returns_none(state_file):
    assert web.load_alpha_engine_ma() is None


def test_load_ma_valid_summary(state_file):
    _write_state(state_file, {'ma': {
        'available': True, 'as_of': '2026-09-21', 'zone': '强势多头区',
        'price': 76401.8, 'updated_at': '2026-09-21T12:25:00Z',
    }})

    assert web.load_alpha_engine_ma() == {
        'available': True, 'zone': '强势多头区', 'as_of': '2026-09-21'}


def test_load_ma_without_key_returns_none(state_file):
    _write_state(state_file, {'regime': {'current': 'BULL'}, 'alpha': {'current': 0.5}})
    assert web.load_alpha_engine_ma() is None


@pytest.mark.parametrize('ma_value', [None, [], 'x', 3, True])
def test_load_ma_non_dict_returns_none(state_file, ma_value):
    _write_state(state_file, {'ma': ma_value})
    assert web.load_alpha_engine_ma() is None


@pytest.mark.parametrize('ma_data', [
    {'available': 'yes', 'zone': '强势多头区', 'as_of': '2026-09-21'},
    {'available': True, 'zone': 12, 'as_of': '2026-09-21'},
    {'available': True, 'zone': '强势多头区', 'as_of': 20260921},
])
def test_load_ma_bad_field_types_return_none(state_file, ma_data):
    _write_state(state_file, {'ma': ma_data})
    assert web.load_alpha_engine_ma() is None


def test_load_ma_missing_fields_default_to_unavailable(state_file):
    _write_state(state_file, {'ma': {}})
    assert web.load_alpha_engine_ma() == {
        'available': False, 'zone': None, 'as_of': None}


def test_load_ma_blank_strings_normalized_to_none(state_file):
    _write_state(state_file, {'ma': {'available': False, 'zone': '', 'as_of': ''}})
    assert web.load_alpha_engine_ma() == {
        'available': False, 'zone': None, 'as_of': None}


def test_load_ma_tolerates_corrupt_json_and_non_dict_state(state_file):
    state_file.write_text('{not-json', encoding='utf-8')
    assert web.load_alpha_engine_ma() is None

    _write_state(state_file, ['not', 'a', 'dict'])
    assert web.load_alpha_engine_ma() is None


# --- alpha_engine_update_changed: 变化检测 --------------------------------------

_BASE_MA = {'available': True, 'zone': '强势多头区', 'as_of': '2026-09-21'}


def _market_data(ma=_BASE_MA, regime='BULL', alpha=0.5):
    return {
        'cycle': web.alpha_engine_regime_label(regime),
        'alpha_engine_regime': regime,
        'alpha_engine_alpha': alpha,
        'alpha_engine_ma': dict(ma) if isinstance(ma, dict) else ma,
    }


def test_update_changed_false_when_nothing_changes():
    assert web.alpha_engine_update_changed(
        _market_data(), 'BULL', 0.5, dict(_BASE_MA)) is False


def test_update_changed_on_regime_or_cycle_or_alpha():
    assert web.alpha_engine_update_changed(_market_data(), 'BEAR', 0.5, _BASE_MA) is True
    stale = _market_data()
    stale['cycle'] = '熊中'
    assert web.alpha_engine_update_changed(stale, 'BULL', 0.5, _BASE_MA) is True
    assert web.alpha_engine_update_changed(_market_data(), 'BULL', 0.6, _BASE_MA) is True
    assert web.alpha_engine_update_changed(_market_data(), 'BULL', 0.5005, _BASE_MA) is False


def test_update_changed_on_ma_zone_as_of_or_available():
    assert web.alpha_engine_update_changed(
        _market_data(), 'BULL', 0.5,
        {'available': True, 'zone': '空头区', 'as_of': '2026-09-21'}) is True
    assert web.alpha_engine_update_changed(
        _market_data(), 'BULL', 0.5,
        {'available': True, 'zone': '强势多头区', 'as_of': '2026-09-22'}) is True
    assert web.alpha_engine_update_changed(
        _market_data(), 'BULL', 0.5,
        {'available': False, 'zone': None, 'as_of': None}) is True


def test_update_changed_ma_none_vs_none_is_false():
    old_absent = _market_data(ma=None)
    old_absent.pop('alpha_engine_ma')
    assert web.alpha_engine_update_changed(old_absent, 'BULL', 0.5, None) is False
    assert web.alpha_engine_update_changed(_market_data(ma=None), 'BULL', 0.5, None) is False
    assert web.alpha_engine_update_changed(_market_data(), 'BULL', 0.5, None) is True


def test_update_changed_without_market_data_is_true():
    assert web.alpha_engine_update_changed(None, 'BULL', 0.5, None) is True
    assert web.alpha_engine_update_changed({}, 'BULL', 0.5, None) is True


# --- market_data 接线 -----------------------------------------------------------

def test_market_data_carries_ma_on_initial_and_update():
    assert 'alpha_engine_ma' in web.data_storage.market_data

    storage = web.DataStorage()
    payload = {'available': True, 'zone': '上升趋势回调区', 'as_of': '2026-09-21'}
    assert storage.update_market_data({'alpha_engine_ma': payload}) is True
    assert storage.market_data['alpha_engine_ma'] == payload
    assert storage.get_all_data()['market_data']['alpha_engine_ma'] == payload
