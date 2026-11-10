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


# --- load_alpha_engine_valuation: 0–1 估值读取 ---------------------------------

def _valuation_state(value, label=None, confidence='high',
                     updated_at='2026-11-10T04:25:00Z'):
    data = {'current': value, 'confidence': confidence, 'updated_at': updated_at}
    if label is not None:
        data['label'] = label
    return {'version': 2, 'valuation': data,
            'runtime': {'analysis_count': 1, 'post_count': 0}}


def test_load_valuation_missing_file_returns_none(state_file):
    assert web.load_alpha_engine_valuation() is None


def test_load_valuation_valid(state_file):
    _write_state(state_file, _valuation_state(0.62, '轻度高估'))

    assert web.load_alpha_engine_valuation() == {
        'value': 0.62, 'label': '轻度高估', 'confidence': 'high',
        'updated_at': '2026-11-10T04:25:00Z'}


def test_load_valuation_missing_label_derived_from_value(state_file):
    _write_state(state_file, _valuation_state(0.18, confidence=''))

    assert web.load_alpha_engine_valuation()['label'] == '极度低估'


@pytest.mark.parametrize('value,label', [
    (0.0, '极度低估'), (0.19, '极度低估'), (0.2, '轻度低估'),
    (0.49, '轻度低估'), (0.5, '轻度高估'), (0.79, '轻度高估'),
    (0.8, '极度高估'), (1.0, '极度高估'),
])
def test_valuation_band_label_boundaries(value, label):
    assert web.valuation_band_label(value) == label


def test_load_valuation_unassessed_when_null(state_file):
    _write_state(state_file, _valuation_state(None))

    assert web.load_alpha_engine_valuation() is None


@pytest.mark.parametrize('bad_value', [1.5, -0.1, 'x', True, [], {}])
def test_load_valuation_invalid_value_returns_none(state_file, bad_value):
    _write_state(state_file, _valuation_state(bad_value))

    assert web.load_alpha_engine_valuation() is None


def test_load_valuation_legacy_v1_state_returns_none(state_file):
    _write_state(state_file,
                 {'version': 1, 'regime': {'current': 'BULL'},
                  'alpha': {'current': 0.5}})

    assert web.load_alpha_engine_valuation() is None


def test_load_valuation_tolerates_corrupt_json_and_non_dict(state_file):
    state_file.write_text('{not-json', encoding='utf-8')
    assert web.load_alpha_engine_valuation() is None

    _write_state(state_file, ['not', 'a', 'dict'])
    assert web.load_alpha_engine_valuation() is None


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
    _write_state(state_file, _valuation_state(0.62, '轻度高估'))
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
_BASE_VALUATION = {'value': 0.62, 'label': '轻度高估', 'confidence': 'high',
                   'updated_at': '2026-11-10T04:25:00Z'}


def _market_data(ma=_BASE_MA, valuation=_BASE_VALUATION):
    return {
        'alpha_engine_valuation': dict(valuation) if isinstance(valuation, dict) else valuation,
        'alpha_engine_ma': dict(ma) if isinstance(ma, dict) else ma,
    }


def test_update_changed_false_when_nothing_changes():
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION), dict(_BASE_MA)) is False


def test_update_changed_on_valuation():
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION, value=0.18, label='极度低估'),
        _BASE_MA) is True
    # 值相同但置信/更新时间变化也算变化
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION, confidence='low'), _BASE_MA) is True
    # 极端情况: 差异小于 0.0001 视为不变 (round(4))
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION, value=0.62001), _BASE_MA) is False


def test_update_changed_on_ma_zone_as_of_or_available():
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION),
        {'available': True, 'zone': '空头区', 'as_of': '2026-09-21'}) is True
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION),
        {'available': True, 'zone': '强势多头区', 'as_of': '2026-09-22'}) is True
    assert web.alpha_engine_update_changed(
        _market_data(), dict(_BASE_VALUATION),
        {'available': False, 'zone': None, 'as_of': None}) is True


def test_update_changed_unassessed():
    assert web.alpha_engine_update_changed(
        _market_data(valuation=None), None, dict(_BASE_MA)) is False
    assert web.alpha_engine_update_changed(
        _market_data(valuation=None), dict(_BASE_VALUATION), dict(_BASE_MA)) is True
    assert web.alpha_engine_update_changed(
        _market_data(), None, dict(_BASE_MA)) is True


def test_update_changed_ma_none_vs_none_is_false():
    old_absent = _market_data(ma=None)
    old_absent.pop('alpha_engine_ma')
    assert web.alpha_engine_update_changed(old_absent, dict(_BASE_VALUATION), None) is False
    assert web.alpha_engine_update_changed(_market_data(ma=None), dict(_BASE_VALUATION), None) is False
    assert web.alpha_engine_update_changed(_market_data(), dict(_BASE_VALUATION), None) is True


def test_update_changed_without_market_data_is_true():
    assert web.alpha_engine_update_changed(None, dict(_BASE_VALUATION), None) is True
    assert web.alpha_engine_update_changed({}, dict(_BASE_VALUATION), None) is True


# --- market_data 接线 -----------------------------------------------------------

def test_market_data_carries_valuation_and_ma_on_initial_and_update():
    assert 'alpha_engine_valuation' in web.data_storage.market_data
    assert 'alpha_engine_ma' in web.data_storage.market_data

    storage = web.DataStorage()
    ma_payload = {'available': True, 'zone': '上升趋势回调区', 'as_of': '2026-09-21'}
    valuation_payload = dict(_BASE_VALUATION)
    assert storage.update_market_data({'alpha_engine_ma': ma_payload}) is True
    assert storage.update_market_data(
        {'alpha_engine_valuation': valuation_payload}) is True
    assert storage.market_data['alpha_engine_ma'] == ma_payload
    assert storage.market_data['alpha_engine_valuation'] == valuation_payload
    assert storage.get_all_data()['market_data']['alpha_engine_ma'] == ma_payload
    assert storage.get_all_data()['market_data']['alpha_engine_valuation'] == valuation_payload


def test_market_data_carries_ahr999_on_initial_and_update():
    assert 'ahr999' in web.data_storage.market_data

    storage = web.DataStorage()
    payload = {
        'available': True, 'value': 0.5232, 'zone': '定投区', 'zone_key': 'dca',
        'as_of': '2026-10-08', 'stale': False,
    }
    assert storage.update_market_data({'ahr999': payload}) is True
    assert storage.market_data['ahr999'] == payload
    assert storage.get_all_data()['market_data']['ahr999'] == payload


def test_index_template_has_valuation_slot_next_to_ahr999():
    template = os.path.join(WEB_DIR, 'templates', 'index.html')
    with open(template, encoding='utf-8') as file_obj:
        html = file_obj.read()
    assert 'id="alpha-valuation"' in html
    assert 'id="ahr999-value"' in html
    assert 'marketData.ahr999' in html
    assert 'marketData.alpha_engine_valuation' in html
    assert html.index('id="alpha-valuation"') < html.index('id="ahr999-value"')
    # 旧 regime/alpha 展示彻底移除
    assert 'id="market-cycle"' not in html
    assert 'id="alpha-value"' not in html
    assert 'alpha_engine_regime' not in html
    assert 'alpha_engine_alpha' not in html
