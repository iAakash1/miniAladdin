"""Instrument mapping stays outside the deterministic scoring path."""

from unittest.mock import Mock

from src.providers.vendors.openfigi_vendor import OpenFigiVendor


def _vendor(payload):
    session = Mock()
    session.headers = {}
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    session.request.return_value = response
    return OpenFigiVendor(session=session), session


def test_openfigi_preserves_unambiguous_identifier_and_evidence(monkeypatch):
    monkeypatch.setenv("OPENFIGI_API_KEY", "test-key-placeholder")
    vendor, session = _vendor([{"data": [{
        "ticker": "AAPL", "compositeFIGI": "BBG000B9XRY4",
        "figi": "BBG000B9Y5X2", "name": "APPLE INC",
    }]}])

    bundle = vendor.get_instrument_identity("aapl")
    assert bundle.nodes[0].metadata["composite_figi"] == "BBG000B9XRY4"
    assert bundle.claims[0].evidence[0].source.provider == "openfigi"
    assert session.request.call_args.kwargs["json"] == [
        {"idType": "TICKER", "idValue": "AAPL", "exchCode": "US"},
    ]


def test_openfigi_withholds_ambiguous_mapping(monkeypatch):
    monkeypatch.setenv("OPENFIGI_API_KEY", "test-key-placeholder")
    vendor, _ = _vendor([{"data": [
        {"ticker": "TEST", "compositeFIGI": "BBG000B9XRY4"},
        {"ticker": "TEST", "compositeFIGI": "BBG000B9XRY5"},
    ]}])
    assert vendor.get_instrument_identity("TEST").claims == []


def test_openfigi_rejects_invalid_symbol_before_network(monkeypatch):
    monkeypatch.setenv("OPENFIGI_API_KEY", "test-key-placeholder")
    vendor, session = _vendor([])
    assert vendor.get_instrument_identity("AAPL?other=1").claims == []
    session.request.assert_not_called()
