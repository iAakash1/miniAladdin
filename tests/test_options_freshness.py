from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
import api.index as api
from src.providers.schemas import OptionChain, ProviderResult

@pytest.mark.parametrize('stale,delayed,as_of,expected',[
    (True,False,'2026-08-01T00:00:00Z','stale'),
    (False,None,None,'unknown'),
    (False,False,None,'unknown'),
    (False,True,'2026-09-08T20:00:00Z','delayed'),
    (False,False,'2026-09-08T20:00:00Z','live'),
])
def test_options_do_not_infer_freshness(stale,delayed,as_of,expected):
    result=ProviderResult(data=OptionChain(underlying='AAPL',source='massive',as_of=as_of,delayed=delayed),source='massive',stale=stale)
    with patch.object(api.providers.market_data,'get_option_chain',return_value=result):
        body=TestClient(api.app).get('/api/options/AAPL').json()
    assert body['status']==expected
    assert body['stale']==stale
    assert body['as_of']==as_of
