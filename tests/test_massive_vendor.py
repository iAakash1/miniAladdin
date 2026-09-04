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


# ── options ──────────────────────────────────────────────────────────────────
#
# The fixtures below are the provider's documented response shape for this wire
# format. They were NOT captured from a live authenticated response — this
# environment has no Massive credential — so these test normalisation, not
# entitlement or live behaviour. That distinction is deliberate and is repeated
# in the provider matrix: a 401 proves a route exists and says nothing about
# whether a plan may read it.

def _chain_payload(**overrides):
    row = {
        "details": {
            "ticker": "O:AAPL261218C00330000",
            "contract_type": "call",
            "expiration_date": "2026-12-18",
            "strike_price": 330,
            "shares_per_contract": 100,
            "exercise_style": "american",
        },
        "last_quote": {"bid": 1.10, "ask": 1.20, "midpoint": 1.15, "timeframe": "REAL-TIME"},
        "last_trade": {"price": 1.18},
        "day": {"volume": 0},
        "open_interest": 8133,
        "implied_volatility": 0.2841,
        "greeks": {"delta": 0.31, "gamma": 0.01, "theta": -0.05, "vega": 0.12},
    }
    row.update(overrides)
    return {"results": [row], "status": "OK"}


def test_a_contract_keeps_its_identity():
    v = _vendor_with_key()
    with patch.object(MassiveVendor, "_get_json", return_value=_chain_payload()):
        chain = v.get_option_chain("AAPL")

    assert chain is not None
    c = chain.contracts[0]
    assert c.contract == "O:AAPL261218C00330000"
    assert c.underlying == "AAPL"
    assert c.expiration == "2026-12-18"
    assert c.strike == 330
    assert c.contract_type == "call"


def test_missing_market_fields_are_none_and_never_zero():
    """An option chain is mostly holes. A bid of zero is a statement about a
    market; a missing bid is the absence of one, and rendering the second as
    the first is the most misleading thing an options surface can do."""
    v = _vendor_with_key()
    payload = _chain_payload(last_quote={}, last_trade={}, greeks={})
    del payload["results"][0]["implied_volatility"]

    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        c = v.get_option_chain("AAPL").contracts[0]

    for field in ("bid", "ask", "midpoint", "last_price",
                  "implied_volatility", "delta", "gamma", "theta", "vega"):
        assert getattr(c, field) is None, f"{field} was filled in rather than left absent"


def test_a_reported_zero_volume_is_kept_as_zero():
    """Volume and open interest are the two places a literal zero is the
    provider's own answer — a contract that did not trade. Converting that to
    None would discard a real observation."""
    v = _vendor_with_key()
    with patch.object(MassiveVendor, "_get_json", return_value=_chain_payload()):
        c = v.get_option_chain("AAPL").contracts[0]
    assert c.day_volume == 0
    assert c.open_interest == 8133


def test_an_absent_volume_is_none_rather_than_zero():
    v = _vendor_with_key()
    payload = _chain_payload(day={})
    del payload["results"][0]["open_interest"]
    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        c = v.get_option_chain("AAPL").contracts[0]
    assert c.day_volume is None
    assert c.open_interest is None


def test_an_unidentifiable_row_is_dropped_not_patched():
    """A row missing strike or expiry cannot go into a chain keyed on them.
    Defaulting either would corrupt the axes rather than lose one row."""
    v = _vendor_with_key()
    payload = _chain_payload()
    payload["results"].append({"details": {"ticker": "O:BAD", "contract_type": "put"}})
    payload["results"].append({"details": {}})

    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        chain = v.get_option_chain("AAPL")

    assert len(chain.contracts) == 1, "an unidentifiable row survived"


def test_the_chain_axes_come_from_its_own_contracts():
    v = _vendor_with_key()
    payload = _chain_payload()
    second = dict(payload["results"][0])
    second["details"] = {**second["details"], "ticker": "O:AAPL261218P00320000",
                         "contract_type": "put", "strike_price": 320}
    payload["results"].append(second)

    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        chain = v.get_option_chain("AAPL")

    assert chain.strikes == [320.0, 330.0]
    assert chain.expirations == ["2026-12-18"]


def test_a_delayed_quote_makes_the_whole_chain_delayed():
    """A chain is only as current as its least current contract."""
    v = _vendor_with_key()
    payload = _chain_payload()
    payload["results"][0]["last_quote"]["timeframe"] = "DELAYED"
    with patch.object(MassiveVendor, "_get_json", return_value=payload):
        assert v.get_option_chain("AAPL").delayed is True

    with patch.object(MassiveVendor, "_get_json", return_value=_chain_payload()):
        assert v.get_option_chain("AAPL").delayed is False


def test_an_empty_chain_is_none_rather_than_an_empty_object():
    v = _vendor_with_key()
    with patch.object(MassiveVendor, "_get_json", return_value={"results": []}):
        assert v.get_option_chain("AAPL") is None


def test_an_expiration_filter_is_pushed_to_the_provider():
    """A full chain is thousands of rows; filtering client-side would fetch
    them all and throw most away."""
    v = _vendor_with_key()
    seen = {}

    def capture(url, params=None, headers=None, operation="http"):
        seen["params"] = params or {}
        seen["url"] = url
        return {"results": []}

    with patch.object(MassiveVendor, "_get_json", side_effect=capture):
        v.get_option_chain("AAPL", expiration="2026-12-18")

    assert seen["params"].get("expiration_date") == "2026-12-18"
    assert "test-key-not-real" not in seen["url"]
