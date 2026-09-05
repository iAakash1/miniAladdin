"""A session block assembled from two different days.

Taking each session field from the first vendor that supplied one produced an
impossible session, and the numbers below are the ones actually observed on
4 September 2026 rather than a constructed example.

Polygon answered with the previous session — basis "previous session close",
as_of 3 September — while Finnhub and Twelve Data answered with the current
one. First-wins took day_open, day_high, day_low, VWAP and trade count from
Polygon and previous_close, change and change_pct from Finnhub, and published
a day range of 324.11–330.81 beside a last sale of 321.03. A last price below
its own session low cannot happen. The real low that day was 317.86, which
Finnhub and Twelve Data both reported and which iteration order passed over.

The live market has since moved on and no longer reproduces it, which is
exactly why the observation is pinned here.
"""

import pytest

from src.providers import fabric
from src.providers.fabric import Evidence


class Quote:
    """Only the attributes `reconcile_price` reads."""

    def __init__(self, **kw):
        for field in ("price", "price_basis", "bid", "ask", "spread_bps", "volume",
                      "as_of", "day_open", "day_high", "day_low", "previous_close",
                      "change", "change_pct", "vwap", "trade_count", "avg_volume",
                      "ma_50", "ma_200", "market_cap"):
            setattr(self, field, kw.get(field))


def _observed() -> list[Evidence]:
    """AAPL, as the four vendors answered on 4 September 2026."""
    return [
        Evidence("finnhub", "quote", "AAPL", True, Quote(
            price=321.03, price_basis="last sale", as_of="2026-09-04T18:31:41+00:00",
            day_open=327.7325, day_high=328.93, day_low=317.86,
            previous_close=328.21, change=-7.18, change_pct=-2.1876)),
        # Yesterday's session, answered as though it were a quote.
        Evidence("polygon", "quote", "AAPL", True, Quote(
            price=328.21, price_basis="previous session close",
            as_of="2026-09-03T20:00:00+00:00",
            day_open=324.87, day_high=330.81, day_low=324.11,
            vwap=328.1567, trade_count=778553, volume=37225838.0)),
        Evidence("twelvedata", "quote", "AAPL", True, Quote(
            price=320.98, price_basis="last sale", as_of="2026-09-04",
            day_open=328.33, day_high=328.895, day_low=317.86,
            previous_close=328.20999, volume=922113.0)),
        # No timestamp at all.
        Evidence("yfinance", "quote", "AAPL", True, Quote(price=321.0299987792969)),
    ]


def test_the_session_is_pinned_to_one_date():
    c = fabric.reconcile_price(_observed())
    assert c["session_date"] == "2026-09-04"


def test_yesterdays_vendor_contributes_nothing_to_todays_session():
    c = fabric.reconcile_price(_observed())
    providers_used = {v["provider"] for v in c["session"].values()}
    assert "polygon" not in providers_used, (
        "the previous session's vendor supplied a field to the current session"
    )


def test_the_stale_vendor_is_named_rather_than_silently_dropped():
    """"Polygon answered with yesterday" and "Polygon failed" are different."""
    c = fabric.reconcile_price(_observed())
    assert c["session_excluded"] == ["polygon", "yfinance"]


def test_the_day_range_is_the_one_that_actually_happened():
    c = fabric.reconcile_price(_observed())
    assert c["session"]["day_low"]["value"] == 317.86
    assert c["session"]["day_high"]["value"] == 328.93


def test_no_last_price_falls_outside_the_published_range():
    """The contradiction that exposed the defect."""
    c = fabric.reconcile_price(_observed())
    lo = c["session"]["day_low"]["value"]
    hi = c["session"]["day_high"]["value"]
    for r in c["readings"]:
        assert lo <= r["price"] <= hi, (
            f"{r['provider']} last price {r['price']} is outside the session "
            f"range {lo}–{hi}"
        )
    assert c["session_coherent"] is True


def test_the_open_high_low_triple_comes_from_a_single_vendor():
    """A high from one tape and a low from another is not a range."""
    c = fabric.reconcile_price(_observed())
    sources = {c["session"][f]["provider"]
               for f in ("day_open", "day_high", "day_low") if f in c["session"]}
    assert len(sources) == 1, f"the day range was assembled from {sources}"


def test_incoherence_is_reported_rather_than_repaired():
    """Where a range and a price still contradict, say so.

    Constructed rather than observed: after the date filter this is rare, and
    a flag nobody can trigger is a flag nobody can trust.
    """
    ev = [
        Evidence("a", "quote", "X", True, Quote(
            price=50.0, as_of="2026-09-04", day_high=110.0, day_low=100.0)),
        Evidence("b", "quote", "X", True, Quote(price=50.5, as_of="2026-09-04")),
    ]
    c = fabric.reconcile_price(ev)
    assert c["session_coherent"] is False
    # And nothing is silently adjusted to make it fit.
    assert c["session"]["day_low"]["value"] == 100.0


def test_a_vendor_with_no_timestamp_cannot_join_a_session():
    ev = [Evidence("nostamp", "quote", "X", True, Quote(
        price=10.0, day_high=11.0, day_low=9.0))]
    c = fabric.reconcile_price(ev)
    assert c["session"] is None
    assert c["session_date"] is None
    assert c["session_excluded"] == ["nostamp"]


def test_a_single_dated_vendor_still_produces_a_session():
    ev = [Evidence("only", "quote", "X", True, Quote(
        price=10.0, as_of="2026-09-04", day_open=9.5, day_high=11.0, day_low=9.0))]
    c = fabric.reconcile_price(ev)
    assert c["session_date"] == "2026-09-04"
    assert c["session"]["day_high"]["provider"] == "only"
    assert c["session_coherent"] is True
    assert c["session_excluded"] is None


def test_coherence_is_unknown_rather_than_true_when_there_is_no_range():
    ev = [Evidence("a", "quote", "X", True, Quote(price=10.0, as_of="2026-09-04"))]
    c = fabric.reconcile_price(ev)
    assert c["session_coherent"] is None, (
        "absence of a range was reported as a passed coherence check"
    )
