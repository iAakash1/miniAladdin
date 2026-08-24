"""The fabric must ask everyone, keep everything, and never let one vendor
break the fan-out. Those three properties are the whole architecture."""

from __future__ import annotations

import pytest

from src.providers import fabric
from src.providers.fabric import Evidence
from src.providers.schemas import NewsHeadline, PriceQuote


class _Vendor:
    def __init__(self, name, *, healthy=True, price=None, raises=None, news=None):
        self.NAME = name
        self.healthy = healthy
        self._price = price
        self._raises = raises
        self._news = news

    def get_price(self, symbol):
        if self._raises:
            raise self._raises
        return PriceQuote(symbol=symbol, price=self._price) if self._price else None

    def get_news(self, symbol, limit=12):
        return self._news


def test_every_healthy_vendor_is_asked_not_just_the_first():
    """The core requirement: a successful vendor must not stop the others."""
    vendors = [_Vendor("a", price=10.0), _Vendor("b", price=10.1), _Vendor("c", price=10.0)]
    ev = fabric.collect("quote", "X", vendors, lambda v: v.get_price("X"))
    assert [e.provider for e in ev] == ["a", "b", "c"]
    assert all(e.ok for e in ev)


def test_an_unhealthy_vendor_is_skipped_without_being_called():
    called = []

    class Tracking(_Vendor):
        def get_price(self, symbol):
            called.append(self.NAME)
            return super().get_price(symbol)

    vendors = [Tracking("up", price=1.0), Tracking("down", healthy=False, price=1.0)]
    fabric.collect("quote", "X", vendors, lambda v: v.get_price("X"))
    assert called == ["up"]


def test_one_exploding_vendor_cannot_break_the_fan_out():
    vendors = [
        _Vendor("ok", price=5.0),
        _Vendor("boom", raises=RuntimeError("429 rate limit exceeded")),
        _Vendor("also_ok", price=5.0),
    ]
    ev = fabric.collect("quote", "X", vendors, lambda v: v.get_price("X"))
    assert sum(e.ok for e in ev) == 2
    failed = next(e for e in ev if not e.ok)
    # A failure is evidence too — it is recorded, classified, and kept.
    assert failed.status == "rate_limited"


def test_a_capability_no_vendor_implements_returns_nothing_rather_than_erroring():
    assert fabric.collect("fundamentals", "X", [_Vendor("a", price=1.0)], lambda v: None) == []


def test_consensus_is_a_median_so_one_stale_vendor_cannot_drag_it():
    """Four vendors on the live print and one on yesterday's close: the
    median ignores the outlier and the dispersion reports it."""
    ev = [
        Evidence(n, "quote", "X", True, PriceQuote(symbol="X", price=p))
        for n, p in (("a", 100.0), ("b", 100.1), ("c", 100.0), ("d", 100.05), ("e", 90.0))
    ]
    c = fabric.reconcile_price(ev)
    assert 100.0 <= c["consensus"] <= 100.1
    assert c["provider_count"] == 5
    assert c["agreeing"] == 4          # the stale one does not agree
    assert c["conflict"] is True        # and the disagreement is surfaced
    assert len(c["readings"]) == 5      # nothing discarded


def test_tight_agreement_is_not_flagged_as_conflict():
    ev = [
        Evidence(n, "quote", "X", True, PriceQuote(symbol="X", price=p))
        for n, p in (("a", 309.35), ("b", 309.35), ("c", 309.42))
    ]
    c = fabric.reconcile_price(ev)
    assert c["agreement"] == "3/3"
    assert c["conflict"] is False


def test_news_from_several_vendors_merges_and_records_corroboration():
    """Two vendors carrying one URL is one story seen twice — and the fact it
    was seen twice is the closest thing a feed has to verification."""
    same = "https://example.com/story?utm=x"
    ev = [
        Evidence("v1", "news", "X", True, [
            NewsHeadline(title="Apple beats estimates", url=same),
            NewsHeadline(title="Only on v1", url="https://a.com/1"),
        ]),
        Evidence("v2", "news", "X", True, [
            NewsHeadline(title="Apple Beats Estimates!", url="https://example.com/story"),
            NewsHeadline(title="Only on v2", url="https://b.com/2"),
        ]),
    ]
    m = fabric.merge_news(ev)
    assert m["collected"] == 4
    assert m["unique"] == 3            # the shared URL collapsed
    assert m["corroborated"] == 1
    assert m["providers"] == ["v1", "v2"]


def test_fundamentals_are_a_union_so_fields_only_one_vendor_has_survive():
    """The reason to ask several vendors: no one of them has every line."""
    class F:
        def __init__(self, **kw):
            self.symbol = "X"; self.period = "2026-06-30"; self.history = []
            for k in fabric._COMPARABLE_FUNDAMENTALS:
                setattr(self, k, kw.get(k))

    ev = [
        Evidence("a", "fundamentals", "X", True, F(revenue=100.0, net_income=10.0)),
        Evidence("b", "fundamentals", "X", True, F(free_cash_flow=7.0, revenue=100.0)),
    ]
    merged = fabric.merge_fundamentals(ev)
    # Union, not a choice: all three fields present though neither vendor had all.
    assert set(merged["fields"]) == {"revenue", "net_income", "free_cash_flow"}
    assert merged["fields"]["revenue"]["providers"] == ["a", "b"]
    assert merged["conflicts"] == []


def test_disagreeing_fundamentals_are_surfaced_not_averaged_away():
    class F:
        def __init__(self, revenue):
            self.symbol = "X"; self.period = "2026-06-30"; self.history = []
            for k in fabric._COMPARABLE_FUNDAMENTALS:
                setattr(self, k, None)
            self.revenue = revenue

    merged = fabric.merge_fundamentals([
        Evidence("a", "fundamentals", "X", True, F(41.2e9)),
        Evidence("b", "fundamentals", "X", True, F(39.8e9)),
        Evidence("c", "fundamentals", "X", True, F(41.0e9)),
    ])
    conflict = merged["conflicts"][0]
    assert conflict["field"] == "revenue"
    # Every observation kept, so a reader can see who said what.
    assert len(conflict["observations"]) == 3
    assert merged["fields"]["revenue"]["agrees"] is False


def test_nothing_answering_yields_no_consensus_rather_than_zero():
    assert fabric.reconcile_price([Evidence("a", "quote", "X", False)]) is None
    assert fabric.merge_fundamentals([Evidence("a", "fundamentals", "X", False)]) is None
