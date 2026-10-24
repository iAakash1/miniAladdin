"""End to end: an API route asks the market-data family, the family walks its
chain, adapters make (mocked) HTTP requests, and the providers registry then
describes exactly what happened.

Only the transport is mocked — `HTTPAdapter.send`, routed by host — so the
route, the fallback chain, the adapters, the error classification, the health
states and the registry view are all the production code. Each test uses its
own symbol, and resets the vendors it touches, because the provider families
are process-wide singletons shared with the rest of the suite.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import requests
from fastapi.testclient import TestClient
from requests.structures import CaseInsensitiveDict

import api.index as api
from src import providers
from src.providers.base import VendorStats

FAKE_KEYS = {
    "MASSIVE_API_KEY": "fake-massive-key-000111",
    "POLYGON_API_KEY": "fake-polygon-key-222333",
}


def _bars(days: int = 70) -> dict:
    """Polygon's aggregate shape: one bar per weekday, ending yesterday."""
    end = datetime.now(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0) - timedelta(days=1)
    results, day, price = [], end, 100.0
    while len(results) < days:
        if day.weekday() < 5:
            results.append({"t": int(day.timestamp() * 1000), "o": price, "h": price + 1,
                            "l": price - 1, "c": price + 0.5, "v": 1_000_000})
            price -= 0.1
        day -= timedelta(days=1)
    return {"status": "OK", "resultsCount": len(results), "results": list(reversed(results))}


def _response(request, status: int, body, headers=None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    r.headers = CaseInsensitiveDict({"Content-Type": "application/json", **(headers or {})})
    r.url = request.url
    r.request = request
    return r


@pytest.fixture()
def market(monkeypatch):
    """Two keyed vendors in front of the chain; everything else unconfigured or switched off."""
    for name, value in FAKE_KEYS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PROVIDER_DISABLED", "yfinance")
    family = providers.market_data
    for vendor in family.vendors:
        monkeypatch.setattr(vendor, "stats", VendorStats())
        monkeypatch.setattr(vendor, "_cooldown_until", 0.0)
    monkeypatch.setattr("src.providers.base.time.sleep", lambda _s: None)
    # The registry merges every live instance of a vendor, which is right in
    # production. Elsewhere in the suite, tests create their own Polygon and
    # Massive instances and leave some cooling down; this test describes only
    # the instances it drives.
    monkeypatch.setattr("src.providers.registry_view.live_vendors", lambda: list(family.vendors))
    routes: dict[str, tuple[int, object, dict]] = {}

    def send(self, request, **kwargs):
        host = requests.utils.urlparse(request.url).hostname
        status, body, headers = routes.get(host, (599, b"unrouted", {}))
        if status == 599:
            raise requests.ConnectionError(f"no route to {host} in this test")
        return _response(request, status, body, headers)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    return routes


def _registry(client) -> dict[str, dict]:
    return {p["id"]: p for p in client.get("/api/providers/registry").json()["providers"]}


def test_a_fallback_after_a_rejected_key_is_reported_vendor_by_vendor(market):
    market["api.massive.com"] = (401, {"status": "ERROR", "error": "Unknown API Key"}, {})
    market["api.polygon.io"] = (200, _bars(), {})
    client = TestClient(api.app, raise_server_exceptions=False)

    quotes = client.get("/api/quotes?symbols=ZQE2E", headers={"x-request-id": "e2e-fallback-01"})
    assert quotes.status_code == 200
    assert quotes.json()["quotes"]["ZQE2E"].get("error") is None, quotes.json()

    reg = _registry(client)
    massive, polygon = reg["massive"], reg["polygon"]

    # The rejected key: its own state, the credential named, its value nowhere.
    assert massive["health"]["state"] == "AUTH_FAILURE"
    assert massive["configuration"]["credential_state"] == "rejected"
    assert massive["recent"][0]["outcome"] == "auth_failure"
    assert massive["recent"][0]["status_code"] == 401

    # The vendor that answered: healthy because it answered, with a real time.
    assert polygon["health"]["state"] == "HEALTHY"
    assert polygon["health"]["last_success_at"] is not None
    assert polygon["health"]["window"] == {"ok": 1, "failed": 0, "declined": 0}
    call = polygon["recent"][0]
    assert call["operation"] == "get_series"
    assert call["request_id"] == "e2e-fallback-01"
    assert call["latency_ms"] >= 0

    # Everything else is described as what it is, not as healthy.
    assert reg["tiingo"]["health"]["state"] == "NOT_CONFIGURED"
    assert reg["yfinance"]["health"]["state"] == "DISABLED"
    assert reg["yfinance"]["configuration"]["disabled"] is True

    for body in (quotes.text, client.get("/api/providers/registry").text):
        for secret in FAKE_KEYS.values():
            assert secret not in body


def test_an_upstream_rate_limit_is_an_outage_not_an_empty_answer(market):
    market["api.massive.com"] = (429, {"status": "ERROR"}, {"Retry-After": "30"})
    market["api.polygon.io"] = (429, {"status": "ERROR"}, {"Retry-After": "30"})
    client = TestClient(api.app, raise_server_exceptions=False)

    quotes = client.get("/api/quotes?symbols=ZQE2F").json()["quotes"]
    assert quotes["ZQE2F"]["status"] == "unavailable", "an outage must not read as a missing symbol"

    reg = _registry(client)
    for name in ("massive", "polygon"):
        assert reg[name]["health"]["state"] in ("RATE_LIMITED", "COOLDOWN"), reg[name]["health"]
        assert reg[name]["health"]["last_failure_class"] == "rate_limited"
        assert reg[name]["recent"][0]["outcome"] == "rate_limited"
        assert reg[name]["health"]["window"]["failed"] == 1


def test_a_malformed_reply_is_a_parse_failure_and_the_chain_moves_on(market):
    market["api.massive.com"] = (200, b"<html>maintenance</html>", {})
    market["api.polygon.io"] = (200, _bars(), {})
    client = TestClient(api.app, raise_server_exceptions=False)

    quotes = client.get("/api/quotes?symbols=ZQE2G").json()["quotes"]
    assert quotes["ZQE2G"].get("error") is None, quotes

    reg = _registry(client)
    assert reg["massive"]["recent"][0]["outcome"] == "parse_failure"
    assert reg["massive"]["health"]["state"] == "UNAVAILABLE"
    assert reg["polygon"]["health"]["state"] == "HEALTHY"
    # Partial success stays visible: one vendor failed, the capability answered.
    series = next(c for c in client.get("/api/providers/registry").json()["capabilities"] if c["key"] == "series")
    assert {"massive", "polygon"} <= set(series["eligible"])
    assert "yfinance" not in series["eligible"]
