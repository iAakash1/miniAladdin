"""The provider catalogue, health window, operator switch and registry view.

Each test holds one property the providers page relies on: every adapter is
described, a state means what the page says it means, nothing secret or
user-specific leaves the server, and instances of one vendor are reported as
one vendor.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import time
from unittest.mock import Mock, patch

import pytest
import requests

import src.providers.vendors as vendors_pkg
from src.observability import request as request_context
from src.providers import catalog, registry_view
from src.providers.base import RECENT_EVENTS, VendorClient, VendorError


def _adapter_classes() -> dict[str, type]:
    found: dict[str, type] = {}
    for mod in pkgutil.iter_modules(vendors_pkg.__path__):
        module = importlib.import_module(f"{vendors_pkg.__name__}.{mod.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, VendorClient) and cls is not VendorClient and cls.__module__ == module.__name__:
                found[cls.NAME] = cls
    return found


# ── the catalogue ────────────────────────────────────────────────────────────

def test_every_adapter_has_a_catalogue_entry_and_every_entry_an_adapter():
    adapters = set(_adapter_classes())
    described = set(catalog.CATALOG)
    assert adapters - described == set(), "adapters missing from src/providers/catalog.py"
    assert described - adapters == set(), "catalogue entries with no adapter"


@pytest.mark.parametrize("entry", list(catalog.CATALOG.values()), ids=lambda e: e.name)
def test_entries_use_the_declared_vocabularies_and_claim_no_more_than_was_checked(entry):
    assert entry.domain in catalog.DOMAINS
    assert entry.source_kind in catalog.SOURCE_KINDS
    assert entry.terms_status in catalog.TERMS_STATUSES
    if entry.terms_status == "not_located":
        assert entry.terms_url is None
    else:
        assert entry.terms_url and entry.terms_url.startswith("https://")
    # A licence flag is a conclusion drawn from reading the terms.
    if entry.licence_review:
        assert entry.terms_status == "reviewed" and entry.notes
    assert "?" not in (entry.endpoint or ""), "an endpoint is a host, never a URL with parameters"


def test_the_fred_notice_is_the_wording_the_terms_require():
    assert catalog.CATALOG["fred"].attribution == (
        "This product uses the FRED® API but is not endorsed or certified by the "
        "Federal Reserve Bank of St. Louis."
    )


# ── a test vendor ────────────────────────────────────────────────────────────

class _Vendor(VendorClient):
    NAME = "catalog_test"
    KEY_ENV = None
    MAX_RETRIES = 0
    BACKOFF_BASE = 0.0
    DEFAULT_RPM = 10_000  # the local limiter is not what these tests are about


def _session(status: int, body=None, headers=None):
    session = Mock()
    session.headers = {}
    response = Mock(status_code=status, headers=headers or {})
    response.json.return_value = body if body is not None else {"ok": True}
    response.content = b"{}"
    session.request.return_value = response
    return session


def _age_events(vendor: VendorClient, seconds: float) -> None:
    """Move everything the vendor has seen `seconds` into the past."""
    stats = vendor.stats
    for event in stats.recent:
        event["at"] -= seconds
    for attr in ("last_success_at", "last_failure_at", "last_attempt_at"):
        if getattr(stats, attr):
            setattr(stats, attr, getattr(stats, attr) - seconds)


# ── health states ────────────────────────────────────────────────────────────

def test_a_success_older_than_the_window_is_stale_not_healthy(monkeypatch):
    monkeypatch.setenv("PROVIDER_HEALTH_WINDOW_SECONDS", "60")
    vendor = _Vendor(session=_session(200))
    vendor._get_json("https://example.test/q", operation="quote")
    assert vendor.health_snapshot()["health_state"] == "HEALTHY"
    _age_events(vendor, 120)
    assert vendor.health_snapshot()["health_state"] == "STALE"


def test_a_recovered_failure_degrades_only_while_it_is_inside_the_window(monkeypatch):
    monkeypatch.setenv("PROVIDER_HEALTH_WINDOW_SECONDS", "60")
    vendor = _Vendor(session=_session(500))
    with pytest.raises(VendorError):
        vendor._get_json("https://example.test/q", operation="quote")
    vendor._session = _session(200)
    vendor._get_json("https://example.test/q", operation="quote")
    assert vendor.health_snapshot()["health_state"] == "DEGRADED"
    # The failure ages out; a fresh success is all that is left in the window.
    _age_events(vendor, 120)
    vendor._get_json("https://example.test/q", operation="quote")
    assert vendor.health_snapshot()["health_state"] == "HEALTHY"


def test_a_404_about_one_input_does_not_degrade_the_vendor():
    vendor = _Vendor(session=_session(200))
    vendor._get_json("https://example.test/q", operation="quote")
    response = Mock(status_code=404, headers={}, content=b"x", text="x")
    response.json.side_effect = ValueError("not json")
    vendor._session.request.return_value = response
    with pytest.raises(VendorError):
        vendor._get_json("https://example.test/q", operation="quote")
    vendor._session = _session(200)
    vendor._get_json("https://example.test/q", operation="quote")
    assert vendor.health_snapshot()["health_state"] == "HEALTHY"


def test_the_operator_switch_takes_a_vendor_out_of_routing(monkeypatch):
    vendor = _Vendor(session=_session(200))
    assert vendor.available
    monkeypatch.setenv("PROVIDER_DISABLED", "something_else, CATALOG_TEST")
    assert vendor.disabled and not vendor.available and not vendor.healthy
    snap = vendor.health_snapshot()
    assert snap["health_state"] == "DISABLED"
    assert snap["configured"] is True, "disabled is not the same as unconfigured"


def test_unconfigured_and_configured_are_reported_separately_from_disabled(monkeypatch):
    class Keyed(_Vendor):
        NAME = "catalog_keyed"
        KEY_ENV = "CATALOG_TEST_KEY"

    monkeypatch.delenv("CATALOG_TEST_KEY", raising=False)
    vendor = Keyed(session=_session(200))
    assert vendor.health_snapshot()["health_state"] == "NOT_CONFIGURED"
    monkeypatch.setenv("CATALOG_TEST_KEY", "fake-key-not-real-000")
    snap = vendor.health_snapshot()
    assert snap["health_state"] == "IDLE" and snap["credential_state"] == "unverified"


# ── retries ──────────────────────────────────────────────────────────────────

def test_backoff_jitter_is_bounded():
    class Retrying(_Vendor):
        NAME = "catalog_retry"
        MAX_RETRIES = 1
        BACKOFF_BASE = 0.4

    vendor = Retrying(session=_session(503))
    with patch("src.providers.base.time.sleep") as sleep, \
         patch("src.providers.base.random.uniform", side_effect=lambda lo, hi: hi):
        with pytest.raises(VendorError):
            vendor._get_json("https://example.test/q", operation="quote")
    (delay,), _ = sleep.call_args
    assert 0.4 <= delay <= 0.4 * (1 + Retrying.BACKOFF_JITTER) + 1e-9


def test_an_auth_failure_is_not_retried():
    class Retrying(_Vendor):
        NAME = "catalog_auth"
        MAX_RETRIES = 2

    vendor = Retrying(session=_session(401))
    with patch("src.providers.base.time.sleep") as sleep, pytest.raises(VendorError) as err:
        vendor._get_json("https://example.test/q", operation="quote")
    assert err.value.failure_class == "auth_failure"
    sleep.assert_not_called()
    assert vendor._session.request.call_count == 1


# ── recent activity ──────────────────────────────────────────────────────────

def test_recent_calls_carry_outcomes_never_urls_parameters_or_keys():
    vendor = _Vendor(session=_session(429, headers={"Retry-After": "1"}))
    with patch("src.providers.base.time.sleep"), pytest.raises(VendorError):
        vendor._get_json("https://example.test/q?symbol=NVDA&apikey=sk-SECRET123",
                         params={"symbol": "NVDA", "apikey": "sk-SECRET123"}, operation="quote")
    vendor._session = _session(200)
    vendor._get_json("https://example.test/q", params={"symbol": "NVDA"}, operation="quote")
    recent = vendor.health_snapshot(include_recent=True)["recent"]
    assert [e["outcome"] for e in recent] == ["ok", "rate_limited"], "one 429 is one event"
    assert recent[1]["status_code"] == 429
    dumped = json.dumps(recent)
    for forbidden in ("NVDA", "SECRET", "example.test", "apikey"):
        assert forbidden not in dumped


def test_recent_calls_are_bounded_and_carry_the_request_id():
    vendor = _Vendor(session=_session(200))
    request_context.begin("GET /api/test", request_id="rid-abc12345")
    try:
        for _ in range(RECENT_EVENTS + 5):
            vendor._get_json("https://example.test/q", operation="quote")
    finally:
        request_context.clear()
    recent = vendor.health_snapshot(include_recent=True)["recent"]
    assert len(recent) == RECENT_EVENTS
    assert {e["request_id"] for e in recent} == {"rid-abc12345"}


def test_a_library_error_is_redacted_before_it_is_recorded():
    vendor = _Vendor()

    def leaks():
        raise RuntimeError("Bad Request for https://api.example.test/series?api_key=abcdef123456")

    with pytest.raises(VendorError) as err:
        vendor.timed_call(leaks, operation="series")
    assert "abcdef123456" not in str(err.value)
    assert "abcdef123456" not in (vendor.health_snapshot()["last_error"] or "")


# ── the registry view ────────────────────────────────────────────────────────

def test_the_view_merges_instances_and_reports_the_worst_state():
    busy, quiet = _Vendor(session=_session(200)), _Vendor(session=_session(500))
    busy._get_json("https://example.test/q", operation="quote")
    with pytest.raises(VendorError):
        quiet._get_json("https://example.test/q", operation="quote")
    view = registry_view.build({"market": [busy, quiet]})
    (record,) = [p for p in view["providers"] if p["id"] == "catalog_test"]
    assert record["instances"] >= 2
    assert record["health"]["requests"] >= 2
    assert record["health"]["state"] == "UNAVAILABLE"
    assert record["catalogued"] is False
    assert any(a["kind"] == "catalog" for a in record["advisories"])


def test_the_view_never_carries_a_credential_value(monkeypatch):
    class Keyed(_Vendor):
        NAME = "catalog_secret"
        KEY_ENV = "CATALOG_SECRET_KEY"

    monkeypatch.setenv("CATALOG_SECRET_KEY", "sk-live-DO-NOT-SHOW-123")
    vendor = Keyed(session=_session(401))
    with pytest.raises(VendorError):
        vendor._get_json("https://example.test/q?token=sk-live-DO-NOT-SHOW-123", operation="quote")
    view = registry_view.build({"market": [vendor]})
    dumped = json.dumps(view)
    assert "DO-NOT-SHOW" not in dumped
    (record,) = [p for p in view["providers"] if p["id"] == "catalog_secret"]
    assert record["configuration"]["credential_env"] == "CATALOG_SECRET_KEY"
    assert record["configuration"]["credential_state"] == "rejected"


def test_a_disabled_vendor_is_not_eligible_for_any_capability(monkeypatch):
    class Quoting(_Vendor):
        NAME = "catalog_quoting"

        def get_price(self, symbol):  # noqa: D401 - capability marker
            return None

    vendor = Quoting(session=_session(200))
    view = registry_view.build({"market": [vendor]})
    price = next(c for c in view["capabilities"] if c["key"] == "quote")
    assert "catalog_quoting" in price["eligible"]
    monkeypatch.setenv("PROVIDER_DISABLED", "catalog_quoting")
    view = registry_view.build({"market": [vendor]})
    price = next(c for c in view["capabilities"] if c["key"] == "quote")
    assert "catalog_quoting" in price["implemented_by"]
    assert "catalog_quoting" not in price["eligible"]
    assert view["disabled"] == ["catalog_quoting"]


def test_an_unset_sec_contact_is_raised_as_an_advisory(monkeypatch):
    from src.providers.vendors.sec_vendor import SECVendor

    sec = SECVendor()
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    view = registry_view.build({"filings": [sec]})
    (record,) = [p for p in view["providers"] if p["id"] == "sec"]
    assert any(a["kind"] == "configuration" and "SEC_USER_AGENT" in a["text"] for a in record["advisories"])
    assert {"name": "SEC_USER_AGENT", "set": False} in record["configuration"]["optional_env"]
    monkeypatch.setenv("SEC_USER_AGENT", "Example Org admin@example.org")
    view = registry_view.build({"filings": [sec]})
    (record,) = [p for p in view["providers"] if p["id"] == "sec"]
    assert not any(a["kind"] == "configuration" for a in record["advisories"])
    assert "admin@example.org" not in json.dumps(view), "a setting's value is never shown"


def test_safe_error_strips_urls_and_keys():
    raw = "403 Client Error: Forbidden for url: https://x.test/a?apikey=SECRET&s=1"
    assert registry_view.safe_error(raw) == "403 Client Error: Forbidden"


def test_the_endpoint_serves_the_view():
    from fastapi.testclient import TestClient

    import api.index as api

    response = TestClient(api.app).get("/api/providers/registry")
    assert response.status_code == 200
    body = response.json()
    assert {"providers", "capabilities", "health_window_seconds", "process_started_at"} <= set(body)
    ids = {p["id"] for p in body["providers"]}
    assert {"sec", "fred", "yfinance"} <= ids
    assert all(p["catalogued"] for p in body["providers"] if p["id"] in catalog.CATALOG)


def test_every_catalogued_adapter_is_listed_even_before_its_service_loads():
    view = registry_view.build({})
    listed = {p["id"]: p for p in view["providers"]}
    assert set(catalog.CATALOG) <= set(listed)
    for name in catalog.CATALOG:
        assert listed[name]["instances"] >= 0
    # A never-called adapter reads as idle or unconfigured, never healthy.
    for p in listed.values():
        if p["health"]["requests"] == 0:
            assert p["health"]["state"] in ("IDLE", "NOT_CONFIGURED", "DISABLED"), p["id"]


def test_a_call_is_recorded_under_the_adapter_method_that_made_it():
    class Named(_Vendor):
        NAME = "catalog_named"

        def get_filings(self, symbol):
            return self._get_json("https://example.test/f", params={"s": symbol})

    vendor = Named(session=_session(200))
    vendor.get_filings("AAPL")
    vendor._get_json("https://example.test/raw")  # outside any operation
    ops = [e["operation"] for e in vendor.health_snapshot(include_recent=True)["recent"]]
    assert ops == ["http", "get_filings"]


def test_local_pacing_and_plan_refusals_are_declined_not_failed():
    class Paced(_Vendor):
        NAME = "catalog_paced"
        DEFAULT_RPM = 1

    vendor = Paced(session=_session(200))
    vendor._get_json("https://example.test/q", operation="quote")
    with pytest.raises(VendorError):
        vendor._get_json("https://example.test/q", operation="quote")  # local limiter
    snap = vendor.health_snapshot()
    assert snap["window"] == {"ok": 1, "failed": 0, "declined": 1}
    # The latest event was our own limiter: that is reported, but it is not a
    # vendor fault, so a later success leaves the vendor healthy.
    vendor.rate_limiter.tokens = 5
    vendor._get_json("https://example.test/q", operation="quote")
    assert vendor.health_snapshot()["health_state"] == "HEALTHY"


def test_placeholders_for_unloaded_adapters_are_reused_and_never_counted():
    registry_view.build({})
    first = dict(registry_view._PLACEHOLDERS)
    view = registry_view.build({})
    assert registry_view._PLACEHOLDERS == first, "a read must not create adapters"
    for name in first:
        record = next(p for p in view["providers"] if p["id"] == name)
        assert record["instances"] == 0


def test_a_non_json_body_from_real_requests_is_a_parse_failure_and_not_retried():
    """The exception `requests` actually raises, not a plain ValueError.

    `requests.JSONDecodeError` subclasses both `RequestException` and
    `ValueError`; mocks that raise a bare ValueError hid that it was being
    caught as a transport fault and retried.
    """
    class Retrying(_Vendor):
        NAME = "catalog_html"
        MAX_RETRIES = 2

    response = requests.Response()
    response.status_code = 200
    response._content = b"<html>maintenance</html>"
    session = Mock()
    session.headers = {}
    session.request.return_value = response
    vendor = Retrying(session=session)
    with pytest.raises(VendorError) as err:
        vendor._get_json("https://example.test/q", operation="quote")
    assert err.value.failure_class == "parse_failure"
    assert session.request.call_count == 1, "an unreadable body is not retried"
