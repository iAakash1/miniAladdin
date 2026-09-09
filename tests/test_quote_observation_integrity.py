"""A new HTTP/cache read does not make a daily close a live quote."""
from unittest.mock import patch

from fastapi.testclient import TestClient
import api.index as api
from src.providers.schemas import OHLCVBar, PriceSeries, ProviderResult


def test_batch_quote_keeps_the_actual_market_date_and_daily_basis():
    bars = [OHLCVBar(date=f'2026-01-{i:02d}', close=100.0+i, volume=0) for i in range(1, 7)]
    result = ProviderResult(data=PriceSeries(symbol='AAPL', bars=bars), source='vendor', cached=True)
    with patch.object(api.providers.market_data, 'get_series', return_value=result):
        quote = TestClient(api.app).get('/api/quotes?symbols=AAPL').json()['quotes']['AAPL']
    assert quote['as_of'] == '2026-01-06'
    assert quote['price_basis'] == 'daily close'
    assert quote['source'] == 'vendor'


def test_one_failed_symbol_does_not_erase_the_other_quote():
    good = ProviderResult(data=PriceSeries(symbol='MSFT', bars=[
        OHLCVBar(date=f'2026-01-{i:02d}', close=400.0+i) for i in range(1, 7)
    ]), source='vendor')
    def fetch(symbol, period):
        return ProviderResult(error='vendor unavailable') if symbol == 'AAPL' else good
    with patch.object(api.providers.market_data, 'get_series', side_effect=fetch):
        body = TestClient(api.app).get('/api/quotes?symbols=AAPL,MSFT').json()
    assert body['quotes']['AAPL']['error']
    assert body['quotes']['MSFT']['price'] == 406.0
    assert body['count'] == 2
