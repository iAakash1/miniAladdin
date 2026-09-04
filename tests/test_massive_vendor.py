"""Massive's adapter, and the one property that must never regress.

Massive speaks Polygon's wire format — established against the live service,
not assumed: an unauthenticated request answers `"API Key was not provided"`
and a wrong key answers `"Unknown API Key"`, which is Polygon's wording. So
these tests are mostly about the two things that are *not* shared: where the
credential travels, and what happens when there isn't one.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from src.providers.vendors.massive_vendor import MassiveVendor


def _vendor_with_key() -> MassiveVendor:
    os.environ["MASSIVE_API_KEY"] = "test-key-not-real"
    return MassiveVendor()


def test_absent_key_makes_the_vendor_unavailable():
    """The whole configuration story. No flag, no half-initialised client."""
    os.environ.pop("MASSIVE_API_KEY", None)
    v = MassiveVendor()
    assert v.available is False
    assert v.healthy is False


def test_a_present_key_makes_it_available():
    v = _vendor_with_key()
    assert v.available is True


def test_the_key_travels_in_a_header_and_never_in_the_url():
    """A key in a query string reaches access logs, proxy logs and browser
    history. Massive accepts both forms, so nothing stops this regressing
    except a test that fails when it does."""
    v = _vendor_with_key()
    seen: dict[str, object] = {}

    def capture(url, params=None, headers=None, operation="http"):
        seen["url"] = url
        seen["params"] = params or {}
        seen["headers"] = headers or {}
        return {"results": []}

    with patch.object(MassiveVendor, "_get_json", side_effect=capture):
        v.get_price("AAPL")

    assert "test-key-not-real" not in seen["url"]
    assert not any("test-key-not-real" in str(x) for x in seen["params"].values())
    assert "apiKey" not in seen["params"]
    assert seen["headers"].get("Authorization") == "Bearer test-key-not-real"


def test_every_endpoint_authenticates_the_same_way():
    """One missed header is a silent 401 that the chain reports as the vendor
    being down, which is the least debuggable failure available."""
    v = _vendor_with_key()
    calls: list[dict] = []

    def capture(url, params=None, headers=None, operation="http"):
        calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        return {"results": []}

    with patch.object(MassiveVendor, "_get_json", side_effect=capture):
        v.get_price("AAPL")
        v.get_series("AAPL", "1mo")
        v.get_company("AAPL")

    assert len(calls) == 3
    for c in calls:
        assert c["headers"].get("Authorization", "").startswith("Bearer ")
        assert "apiKey" not in c["params"]
        assert "test-key-not-real" not in c["url"]


def test_history_is_split_adjusted():
    """An unadjusted multi-year series draws a split as a crash, which is the
    most misleading thing a price chart can do."""
    v = _vendor_with_key()
    seen: dict[str, object] = {}

    def capture(url, params=None, headers=None, operation="http"):
        seen["params"] = params or {}
        return {"results": []}

    with patch.object(MassiveVendor, "_get_json", side_effect=capture):
        v.get_series("AAPL", "5y")

    assert seen["params"].get("adjusted") == "true"


def test_a_bar_without_a_close_is_dropped_not_zeroed():
    v = _vendor_with_key()
    payload = {"results": [
        {"t": 1_700_000_000_000, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100},
        {"t": 1_700_086_400_000, "o": 1.0, "h": 2.0, "l": 0.5, "v": 100},   # no close
        {"o": 1.0, "c": 1.7, "v": 100},                                      # no stamp
    ]}
    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        series = v.get_series("AAPL", "1mo")

    assert series is not None
    assert len(series.bars) == 1, "a bar with no close or no date became a bar"
    assert series.bars[0].close == 1.5


def test_an_empty_result_is_none_rather_than_an_empty_series():
    """None lets the chain fall through to the next vendor. An empty series
    would be a successful answer meaning "this security has no history"."""
    v = _vendor_with_key()
    with patch.object(MassiveVendor, "_get_json", return_value={"results": []}):
        assert v.get_series("AAPL", "1mo") is None
        assert v.get_price("AAPL") is None


def test_the_quote_says_which_session_it_is():
    """`/prev` is the previous session's aggregate. A consumer reading it as a
    live tick is reading it wrong, so it carries its own basis."""
    v = _vendor_with_key()
    payload = {"results": [{"c": 328.21, "o": 320.0, "h": 330.0, "l": 319.0,
                            "v": 1000, "vw": 325.0, "n": 42, "t": 1_700_000_000_000}]}
    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        q = v.get_price("AAPL")

    assert q is not None
    assert q.price == 328.21
    assert q.price_basis == "previous session close"
    assert q.as_of is not None and q.as_of.startswith("20")
