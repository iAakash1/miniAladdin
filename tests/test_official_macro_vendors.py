"""Official macro fallbacks preserve source units and dates."""

from unittest.mock import Mock
import pytest

from src.providers.vendors.macro_vendors import BeaVendor, BlsVendor
from src.providers.base import VendorError, redact


def _session(payload):
    session = Mock()
    session.headers = {}
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    session.request.return_value = response
    return session


def test_bls_cpi_matches_seasonally_adjusted_fred_series():
    session = _session({
        "status": "REQUEST_SUCCEEDED",
        "Results": {"series": [{"data": [
            {"year": "2026", "period": "M02", "value": "324.1"},
            {"year": "2026", "period": "M01", "value": "323.7"},
            {"year": "2026", "period": "M13", "value": "324.0"},
        ]}]},
    })
    vendor = BlsVendor(session=session)
    assert vendor.get_official_series("CPIAUCSL") == [
        ("2026-01-01", 323.7), ("2026-02-01", 324.1),
    ]
    assert session.request.call_args.kwargs["json"]["seriesid"] == ["CUSR0000SA0"]
    assert vendor.get_official_series("T10Y2Y") is None


def test_bea_gdp_is_quarterly_growth_only(monkeypatch):
    monkeypatch.setenv("BEA_API_KEY", "test-key-placeholder")
    session = _session({"BEAAPI": {"Results": {"Data": [
        {"LineNumber": "1", "TimePeriod": "2026Q2", "DataValue": "2.3"},
        {"LineNumber": "2", "TimePeriod": "2026Q2", "DataValue": "8.7"},
        {"LineNumber": "1", "TimePeriod": "2026Q1", "DataValue": "1.9"},
    ]}}})
    vendor = BeaVendor(session=session)
    assert vendor.get_official_series("A191RL1Q225SBEA") == [
        ("2026-01-01", 1.9), ("2026-04-01", 2.3),
    ]
    assert vendor.get_official_series("FEDFUNDS") is None


def test_bea_user_id_is_removed_from_transport_errors():
    assert redact("https://apps.bea.gov/api/data/?UserID=private-value&method=GetData") == (
        "https://apps.bea.gov/api/data/?UserID=<redacted>&method=GetData"
    )


def test_bea_inactive_key_is_not_reported_healthy(monkeypatch):
    monkeypatch.setenv("BEA_API_KEY", "test-key-placeholder")
    session = _session({"BEAAPI": {"Results": {"Error": {
        "APIErrorCode": "4", "APIErrorDescription": "This UserId is not active.",
    }}}})
    vendor = BeaVendor(session=session)
    with pytest.raises(VendorError):
        vendor.get_official_series("A191RL1Q225SBEA")
    assert vendor.health_snapshot()["health_state"] == "AUTH_FAILURE"
