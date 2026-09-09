"""Invalid, stale or misdated macro observations cannot become a regime."""
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.providers.schemas import MacroSnapshot, ProviderResult
from src.providers.vendors.data_vendors import FredVendor
from src.services import dashboard_service as dashboard


@pytest.fixture(autouse=True)
def no_cache():
    api._macro_cache.clear()
    api._stress_cache.clear()
    yield
    api._macro_cache.clear()
    api._stress_cache.clear()


@pytest.mark.parametrize('field', ['yield_spread', 'inflation_rate', 'fed_funds_rate'])
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_macro_values_stay_unavailable(field, bad):
    fields = dict(yield_spread=0.4, inflation_rate=2.0, fed_funds_rate=3.0)
    fields[field] = bad
    result = ProviderResult(data=MacroSnapshot(**fields), source='fred')
    with patch.object(api.providers.macro, 'get_macro', return_value=result):
        response = TestClient(api.app, raise_server_exceptions=False).get('/api/macro')
    assert response.status_code == 200
    body = response.json()
    assert body['stats'][field] is None
    if field != 'fed_funds_rate':
        assert body['risk_multiplier'] is None
        assert body['stats']['status'] == 'UNAVAILABLE'


def test_stale_snapshot_does_not_apply_a_live_gate():
    fetched = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = ProviderResult(data=MacroSnapshot(yield_spread=.4, inflation_rate=2, fed_funds_rate=3),
                            source='fred', stale=True, cached=True, fetched_at=fetched)
    with patch.object(api.providers.macro, 'get_macro', return_value=result):
        body = TestClient(api.app).get('/api/macro').json()
    assert body['risk_multiplier'] is None
    assert body['stats']['status'] == 'UNAVAILABLE'
    assert body['stats']['stale'] is True
    assert body['stats']['source'] == 'fred'
    assert body['stats']['fetched_at'].startswith('2020-01-01')


@pytest.mark.parametrize('fields', [dict(yield_spread=None, inflation_rate=2), dict(yield_spread=.5, inflation_rate=None)])
def test_dashboard_does_not_substitute_missing_macro_with_zero(fields):
    result = ProviderResult(data=MacroSnapshot(**fields), source='fred')
    with patch.object(dashboard, '_gather', return_value=[]), patch.object(dashboard.providers.macro, 'get_macro', return_value=result):
        regime = dashboard._macro_board()['regime']
    assert not regime['available']
    assert regime.get('risk_multiplier') is None


def test_stale_stress_observations_cannot_gate_the_verdict():
    result = ProviderResult(data=[('2020-01-01', 99.0)], source='fred', stale=True)
    with patch.object(api.providers.macro, 'get_series_snapshot', return_value=result), patch.object(api.providers.market_data, 'get_series', return_value=ProviderResult(data=None)):
        stress = api._stress_inputs()
    assert stress['term_spread'] is None
    assert stress['nfci'] is None


def _observations():
    # Missing June must not move February's comparison back to January.
    dates = pd.date_range('2024-01-01', periods=14, freq='MS').delete(5)
    return pd.Series([100., 102.] + [103.] * 10 + [110.], index=dates)


def test_fred_cpi_compares_the_same_month_one_year_earlier():
    vendor = FredVendor()
    class Fred:
        def get_series(self, series_id):
            return _observations() if series_id == 'CPIAUCNS' else pd.Series([.4], index=pd.to_datetime(['2026-09-07']))
    with patch.object(FredVendor, 'available', True), patch.object(vendor, '_client', return_value=Fred()):
        snapshot = vendor.get_macro()
    assert snapshot.inflation_rate == 7.84
    assert snapshot.observation_dates['inflation_rate'] == '2025-02-01'
    assert snapshot.observation_dates['yield_spread'] == '2026-09-07'


def test_dashboard_cpi_does_not_turn_a_short_history_into_an_index_reading():
    obs = [('2026-08-01', 320.)]
    with patch.object(dashboard.providers.macro, 'get_series_snapshot', return_value=ProviderResult(data=obs, source='fred')):
        card = dashboard._macro_card({'id':'CPIAUCSL','label':'CPI','unit':'index','yoy':'true','explain':'year over year'})
    assert card is None


def test_dashboard_cpi_uses_calendar_year_ago():
    obs = [(d.strftime('%Y-%m-%d'), v) for d,v in _observations().items()]
    with patch.object(dashboard.providers.macro, 'get_series_snapshot', return_value=ProviderResult(data=obs, source='fred')):
        card = dashboard._macro_card({'id':'CPIAUCSL','label':'CPI','unit':'index','yoy':'true','explain':'year over year'})
    assert card['value'] == 7.84
    assert card['unit'] == '% y/y'


def test_zero_spread_and_zero_inflation_are_real_measurements():
    result = ProviderResult(data=MacroSnapshot(yield_spread=0, inflation_rate=0, fed_funds_rate=0), source='fred')
    with patch.object(api.providers.macro, 'get_macro', return_value=result):
        multiplier, stats = api._fetch_macro_safe()
    assert multiplier == 1.0
    assert stats['yield_spread'] == 0
    assert stats['inflation_rate'] == '0.00%'
