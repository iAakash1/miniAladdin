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


# ── capability matrix ─────────────────────────────────────────────────────

def test_the_matrix_is_discovered_from_methods_not_from_a_hand_kept_table():
    """A table drifts the first time someone adds a method and forgets to
    register it — and the question it answers wrongly is exactly the one the
    orchestrator asks on every request."""
    class Quoter:
        NAME, healthy, available, KEY_ENV = "q", True, True, "Q_KEY"
        def get_price(self, s): return None

    class Newsy:
        NAME, healthy, available, KEY_ENV = "n", False, False, "N_KEY"
        def get_news(self, s, c="", limit=12): return None
        def get_news_sentiment(self, s, limit=20): return None

    m = fabric.capability_matrix({"market": [Quoter()], "news": [Newsy()]})
    caps = {e["provider"]: e["capabilities"] for e in m["providers"]}
    assert caps["q"] == ["quote"]
    assert caps["n"] == ["news", "news_sentiment"]


def test_configured_and_healthy_are_reported_separately():
    """They fail for different reasons and are fixed by different people: a
    missing key is a deploy problem, a tripped circuit is an outage."""
    class Cooling:
        NAME, healthy, available, KEY_ENV = "c", False, True, "C_KEY"
        def get_price(self, s): return None

    class Unset:
        NAME, healthy, available, KEY_ENV = "u", False, False, "U_KEY"
        def get_price(self, s): return None

    m = fabric.capability_matrix({"market": [Cooling(), Unset()]})
    quote = m["by_capability"]["quote"]
    assert quote["implemented_by"] == ["c", "u"]
    assert quote["live"] == []                 # neither will be asked
    assert quote["unconfigured"] == ["u"]      # but only one lacks a key
    assert m["totals"]["configured"] == 1


def test_the_matrix_never_exposes_a_credential_value(monkeypatch):
    monkeypatch.setenv("Q_KEY", "super-secret-value")

    class Quoter:
        NAME, healthy, available, KEY_ENV = "q", True, True, "Q_KEY"
        def get_price(self, s): return None

    import json
    blob = json.dumps(fabric.capability_matrix({"market": [Quoter()]}))
    assert "super-secret-value" not in blob
    assert "Q_KEY" in blob   # the variable's name is useful; its value is not


def test_a_vendor_in_two_groups_appears_once_with_both_groups():
    class Both:
        NAME, healthy, available, KEY_ENV = "b", True, True, None
        def get_price(self, s): return None
        def get_fundamentals(self, s): return None

    v = Both()
    m = fabric.capability_matrix({"market": [v], "fundamentals": [v]})
    assert len(m["providers"]) == 1
    assert sorted(m["providers"][0]["groups"]) == ["fundamentals", "market"]


def test_the_merge_carries_the_richest_copy_of_a_shared_story():
    """One vendor has the summary, another the publisher's image, a third the
    sentiment score. The union is strictly better than any single copy, and
    that is the whole reason to fan out."""
    url = "https://example.com/story"
    ev = [
        Evidence("v1", "news", "X", True, [
            NewsHeadline(title="Big news", url=url, summary="the detail"),
        ]),
        Evidence("v2", "news", "X", True, [
            NewsHeadline(title="Big news", url=url, image_url="https://img/x.jpg"),
        ]),
        Evidence("v3", "news_sentiment", "X", True, [
            NewsHeadline(title="Big news", url=url, sentiment_score=0.42,
                         sentiment_label="Bullish", sentiment_source="v3"),
        ]),
    ]
    merged = fabric.merge_news(ev)
    story = merged["headlines"][0]
    assert story.summary == "the detail"
    assert story.image_url == "https://img/x.jpg"
    assert story.sentiment_score == 0.42
    assert sorted(story.corroborated_by) == ["v1", "v2", "v3"]


def test_a_publishers_image_is_never_overwritten_by_a_later_vendors_copy():
    url = "https://example.com/s"
    merged = fabric.merge_news([
        Evidence("v1", "news", "X", True, [NewsHeadline(title="T", url=url, image_url="https://first.jpg")]),
        Evidence("v2", "news", "X", True, [NewsHeadline(title="T", url=url, image_url="https://second.jpg")]),
    ])
    assert merged["headlines"][0].image_url == "https://first.jpg"


def test_unscored_articles_are_reported_as_unscored_not_as_neutral():
    """"Not measured" and "measured as neutral" are different facts; merging
    them would let a stream with two scored articles look as well-evidenced
    as one with twenty."""
    merged = fabric.merge_news([
        Evidence("v1", "news", "X", True, [
            NewsHeadline(title="A", url="https://a"),
            NewsHeadline(title="B", url="https://b"),
        ]),
        Evidence("v2", "news_sentiment", "X", True, [
            NewsHeadline(title="C", url="https://c", sentiment_score=0.8,
                         sentiment_label="Bullish", sentiment_source="v2"),
        ]),
    ])
    s = merged["sentiment"]
    assert s["scored"] == 1 and s["unscored"] == 2
    assert s["positive"] == 1
    assert s["source"] == "v2"


def test_a_stream_nobody_scored_reports_no_sentiment_at_all():
    merged = fabric.merge_news([
        Evidence("v1", "news", "X", True, [NewsHeadline(title="A", url="https://a")]),
    ])
    assert merged["sentiment"] is None


# ── profile union ─────────────────────────────────────────────────────────

class _Profile:
    """Minimal stand-in with the fields merge_profile reads."""
    def __init__(self, **kw):
        for f in fabric._PROFILE_TEXT:
            setattr(self, f, kw.get(f, ""))
        for f in fabric._PROFILE_NUMERIC:
            setattr(self, f, kw.get(f))


def test_a_profile_is_a_union_so_fields_only_one_vendor_has_survive():
    """No vendor here carries a complete profile: one has the domain, another
    the headcount, a third the business summary. Choosing one would discard
    whatever the others uniquely hold."""
    merged = fabric.merge_profile([
        Evidence("finnhub", "company", "X", True,
                 _Profile(name="Acme Inc", domain="acme.com", ipo_date="1980-12-12")),
        Evidence("polygon", "company", "X", True,
                 _Profile(name="Acme Inc", employees=166000, description="Acme makes things.")),
        Evidence("yfinance", "company", "X", True,
                 _Profile(name="Acme Inc", sector="Technology", industry="Consumer Electronics")),
    ])
    resolved = merged["resolved"]
    assert resolved["domain"] == "acme.com"          # only finnhub had it
    assert resolved["employees"] == 166000           # only polygon had it
    assert resolved["sector"] == "Technology"        # only yfinance had it
    assert resolved["description"] == "Acme makes things."
    assert merged["providers"] == ["finnhub", "polygon", "yfinance"]


def test_a_gics_industry_is_preferred_over_a_shouty_sic_description():
    """Length alone picked "ELECTRONIC COMPUTERS" over "Consumer
    Electronics". SIC is a 1930s taxonomy; GICS is what a company page should
    show and what an industry image query should be built from."""
    merged = fabric.merge_profile([
        Evidence("polygon", "company", "X", True, _Profile(industry="ELECTRONIC COMPUTERS")),
        Evidence("yfinance", "company", "X", True, _Profile(industry="Consumer Electronics")),
    ])
    assert merged["resolved"]["industry"] == "Consumer Electronics"
    assert merged["fields"]["industry"]["chosen_from"] == "yfinance"
    # And the discarded value is still visible, not deleted.
    values = {o["value"] for o in merged["fields"]["industry"]["observations"]}
    assert "ELECTRONIC COMPUTERS" in values


def test_disagreeing_headcounts_are_flagged_rather_than_averaged():
    merged = fabric.merge_profile([
        Evidence("polygon", "company", "X", True, _Profile(employees=166000)),
        Evidence("yfinance", "company", "X", True, _Profile(employees=150000)),
    ])
    conflict = merged["conflicts"][0]
    assert conflict["field"] == "employees"
    assert conflict["spread_pct"] > 5
    assert merged["fields"]["employees"]["agrees"] is False


def test_market_cap_gets_a_wider_tolerance_because_it_moves_with_the_price():
    """Two vendors quoting a market cap minutes apart are not in conflict —
    it is the same number measured at different moments."""
    merged = fabric.merge_profile([
        Evidence("a", "company", "X", True, _Profile(market_cap=1_000_000_000)),
        Evidence("b", "company", "X", True, _Profile(market_cap=1_020_000_000)),
    ])
    assert merged["fields"]["market_cap"]["agrees"] is True
    assert merged["conflicts"] == []
    # The same 2% spread on headcount *is* a conflict.
    head = fabric.merge_profile([
        Evidence("a", "company", "X", True, _Profile(employees=1_000_000)),
        Evidence("b", "company", "X", True, _Profile(employees=1_020_000)),
    ])
    assert head["fields"]["employees"]["agrees"] is False


def test_agreeing_text_records_no_observations_to_review():
    merged = fabric.merge_profile([
        Evidence("a", "company", "X", True, _Profile(name="Acme Inc")),
        Evidence("b", "company", "X", True, _Profile(name="Acme Inc")),
    ])
    assert merged["fields"]["name"]["agrees"] is True
    assert merged["fields"]["name"]["observations"] is None


def test_nobody_answering_yields_no_profile_rather_than_an_empty_one():
    assert fabric.merge_profile([Evidence("a", "company", "X", False)]) is None


def test_sec_is_discoverable_as_its_own_capability_not_as_a_fundamentals_vendor():
    """EDGAR is the filing itself, not a vendor's reading of one. Merging it
    into the fundamentals union would make the primary source a fourth
    opinion to median against."""
    class Sec:
        NAME, healthy, available, KEY_ENV = "sec", True, True, None
        def get_filings(self, s, limit=20): return []
        def get_xbrl_facts(self, s): return {}

    m = fabric.capability_matrix({"filings": [Sec()]})
    caps = m["providers"][0]["capabilities"]
    assert caps == ["filings", "xbrl_facts"]
    assert "fundamentals" not in caps
    # Keyless, so it is live in every environment including CI.
    assert m["by_capability"]["filings"]["live"] == ["sec"]
    assert m["by_capability"]["filings"]["unconfigured"] == []


# ── XBRL trend derivation ─────────────────────────────────────────────────

def test_xbrl_trends_never_cross_two_different_concepts():
    """The failure this guards: comparing this year's revenue against last
    year's net income would produce an impressive and meaningless number."""
    from api.index import _xbrl_trends

    trends = _xbrl_trends({
        "Revenue": [
            {"fiscal_year": 2025, "value": 400.0, "unit": "USD", "form": "10-K", "filed": "2025-10-31"},
            {"fiscal_year": 2024, "value": 350.0, "unit": "USD", "form": "10-K", "filed": "2024-11-01"},
        ],
        "Net income": [
            {"fiscal_year": 2025, "value": 100.0, "unit": "USD", "form": "10-K", "filed": "2025-10-31"},
            {"fiscal_year": 2024, "value": 90.0, "unit": "USD", "form": "10-K", "filed": "2024-11-01"},
        ],
    })
    by_concept = {t["concept"]: t for t in trends}
    assert by_concept["Revenue"]["change_pct"] == pytest.approx(14.29, abs=0.01)
    assert by_concept["Net income"]["change_pct"] == pytest.approx(11.11, abs=0.01)
    # The prior value travels with the percentage so the arithmetic is
    # checkable against the rows rendered beside it.
    assert by_concept["Revenue"]["prior_value"] == 350.0
    assert by_concept["Revenue"]["prior_year"] == 2024


def test_a_single_year_yields_no_trend_rather_than_zero():
    """One observation is not a direction."""
    from api.index import _xbrl_trends
    assert _xbrl_trends({"Revenue": [
        {"fiscal_year": 2025, "value": 400.0, "unit": "USD", "form": "10-K", "filed": "2025-10-31"},
    ]}) == []


def test_a_zero_or_sign_flipped_prior_year_produces_no_percentage():
    """A prior year of zero has no defined growth rate, and a swing from
    negative to positive makes the percentage meaningless rather than large."""
    from api.index import _xbrl_trends
    assert _xbrl_trends({"Net income": [
        {"fiscal_year": 2025, "value": 100.0, "unit": "USD", "form": "10-K", "filed": "x"},
        {"fiscal_year": 2024, "value": 0.0, "unit": "USD", "form": "10-K", "filed": "y"},
    ]}) == []
    assert _xbrl_trends({"Net income": [
        {"fiscal_year": 2025, "value": 100.0, "unit": "USD", "form": "10-K", "filed": "x"},
        {"fiscal_year": 2024, "value": -50.0, "unit": "USD", "form": "10-K", "filed": "y"},
    ]}) == []


def test_every_trend_names_the_document_it_came_from():
    """Primary-source evidence whose document is not named is just another
    number — the form and filing date are the point."""
    from api.index import _xbrl_trends
    trend = _xbrl_trends({"Revenue": [
        {"fiscal_year": 2025, "value": 400.0, "unit": "USD", "form": "10-K", "filed": "2025-10-31"},
        {"fiscal_year": 2024, "value": 350.0, "unit": "USD", "form": "10-K", "filed": "2024-11-01"},
    ]})[0]
    assert trend["form"] == "10-K"
    assert trend["filed"] == "2025-10-31"
    assert trend["unit"] == "USD"


def test_a_quarter_is_never_compared_against_a_full_year():
    """The SEC adapter filters to annual 10-K rows today, so this cannot fire
    yet. It exists because the alternative is a silent wrong answer: relax
    that filter and an unguarded trend reports a ~75% 'decline' that is
    purely a period mismatch."""
    from api.index import _xbrl_trends
    assert _xbrl_trends({"Revenue": [
        {"fiscal_year": 2025, "value": 100.0, "unit": "USD", "form": "10-Q", "filed": "a"},
        {"fiscal_year": 2024, "value": 400.0, "unit": "USD", "form": "10-K", "filed": "b"},
    ]}) == []


def test_two_different_units_are_never_compared():
    from api.index import _xbrl_trends
    assert _xbrl_trends({"Revenue": [
        {"fiscal_year": 2025, "value": 400.0, "unit": "EUR", "form": "10-K", "filed": "a"},
        {"fiscal_year": 2024, "value": 350.0, "unit": "USD", "form": "10-K", "filed": "b"},
    ]}) == []


def test_a_restatement_of_one_year_is_not_reported_as_growth():
    """The same fiscal year republished under a later filing date is a
    correction, not a change."""
    from api.index import _xbrl_trends
    assert _xbrl_trends({"Revenue": [
        {"fiscal_year": 2025, "value": 402.0, "unit": "USD", "form": "10-K", "filed": "2026-02-01"},
        {"fiscal_year": 2025, "value": 400.0, "unit": "USD", "form": "10-K", "filed": "2025-10-31"},
    ]}) == []


def test_a_gap_year_is_not_labelled_year_over_year():
    """A two-year jump is a reporting hole, not a YoY change."""
    from api.index import _xbrl_trends
    assert _xbrl_trends({"Revenue": [
        {"fiscal_year": 2025, "value": 400.0, "unit": "USD", "form": "10-K", "filed": "a"},
        {"fiscal_year": 2023, "value": 350.0, "unit": "USD", "form": "10-K", "filed": "b"},
    ]}) == []


def test_brand_mark_is_deliberately_outside_the_fan_out():
    """Pins a decision an audit will otherwise rediscover as a false positive.

    `brand_mark` is registered so an operator can see whether the logo
    provider is configured, but it is never run through `collect`: it is pure
    URL construction with no network call, so a fan-out would add a thread
    handoff and an evidence record for something that cannot fail, time out,
    or be rate-limited. Everything else registered *is* collected, and this
    test fails if that stops being true in either direction.
    """
    import pathlib
    import re

    sources = "\n".join(
        p.read_text()
        for p in [
            *pathlib.Path("src/providers").rglob("*.py"),
            *pathlib.Path("src/services").rglob("*.py"),
            pathlib.Path("api/index.py"),
        ]
    )
    collected = set(re.findall(r'collect\(\s*\n?\s*"([a-z_]+)"', sources))
    uncollected = {c for c in fabric.CAPABILITY_METHODS if c not in collected}

    assert uncollected == {"brand_mark"}, (
        f"capability wiring changed: {uncollected} are registered but never "
        "collected. Either wire them into the fabric or document why not."
    )
    # And the reasoning lives next to the registration, not only here.
    registry = pathlib.Path("src/providers/fabric.py").read_text()
    assert "pure URL construction" in registry


# ── restatement detection ─────────────────────────────────────────────────

def _fact(concept, start, end, value, filed, form="10-K", unit="USD", label=None):
    return {
        "concept": concept, "label": label or concept, "period_start": start,
        "period_end": end, "value": value, "filed": filed, "form": form,
        "unit": unit, "fiscal_year": None, "fiscal_period": None,
    }


def test_an_annual_figure_is_never_compared_against_its_own_fourth_quarter():
    """The bug this exists for, caught against live EDGAR data before it
    shipped: a 10-K carries both the fiscal-year figure and the Q4 that shares
    its end date. Grouping on the end date alone compared annual revenue with
    quarterly revenue and produced 106 fictitious 'restatements' for Apple,
    the largest a -77% swing with both values filed the same day."""
    from api.index import _restatements

    timeline = [
        # FY2018 revenue and Q4-2018 revenue: same end date, same filing.
        _fact("Revenue", "2017-10-01", "2018-09-29", 265_595_000_000, "2018-11-05"),
        _fact("Revenue", "2018-07-01", "2018-09-29", 62_900_000_000, "2018-11-05"),
    ]
    assert _restatements(timeline) == []


def test_a_genuine_revision_of_the_same_period_is_reported():
    """Apple's 2009 retrospective adoption of ASU 2009-13 really did restate
    FY2009 net income upward — the same period, refiled a year later."""
    from api.index import _restatements

    timeline = [
        _fact("NetIncomeLoss", "2008-09-28", "2009-09-26", 5_704_000_000, "2009-10-27",
              label="Net income"),
        _fact("NetIncomeLoss", "2008-09-28", "2009-09-26", 8_235_000_000, "2010-10-27",
              label="Net income"),
    ]
    found = _restatements(timeline)
    assert len(found) == 1
    assert found[0]["original_value"] == 5_704_000_000
    assert found[0]["revised_value"] == 8_235_000_000
    assert found[0]["change_pct"] == pytest.approx(44.4, abs=0.1)
    # Both filing dates survive so a reader can open each document and check.
    assert found[0]["original_filed"] == "2009-10-27"
    assert found[0]["revised_filed"] == "2010-10-27"


def test_a_unit_change_is_not_a_restatement():
    """A concept reported in USD and later per-share is a different
    measurement, not a correction."""
    from api.index import _restatements
    assert _restatements([
        _fact("EPS", "2024-01-01", "2024-12-31", 6_000_000_000, "2025-01-01", unit="USD"),
        _fact("EPS", "2024-01-01", "2024-12-31", 6.1, "2025-06-01", unit="USD/shares"),
    ]) == []


def test_a_quarterly_figure_superseded_by_an_annual_filing_is_not_a_restatement():
    """Ordinary year-end adjustment, not a revision of the same disclosure."""
    from api.index import _restatements
    assert _restatements([
        _fact("Revenue", "2024-01-01", "2024-03-31", 100.0, "2024-04-01", form="10-Q"),
        _fact("Revenue", "2024-01-01", "2024-03-31", 110.0, "2025-01-01", form="10-K"),
    ]) == []


def test_repeating_the_same_figure_is_confirmation_not_a_change():
    from api.index import _restatements
    assert _restatements([
        _fact("Revenue", "2024-01-01", "2024-12-31", 100.0, "2025-01-01"),
        _fact("Revenue", "2024-01-01", "2024-12-31", 100.0, "2025-06-01"),
        _fact("Revenue", "2024-01-01", "2024-12-31", 100.0, "2025-09-01"),
    ]) == []


def test_rounding_level_differences_stay_below_the_floor():
    """XBRL carries sub-percent differences that are noise, not news."""
    from api.index import _restatements
    assert _restatements([
        _fact("Revenue", "2024-01-01", "2024-12-31", 100_000.0, "2025-01-01"),
        _fact("Revenue", "2024-01-01", "2024-12-31", 100_200.0, "2025-06-01"),
    ]) == []


def test_instant_and_flow_concepts_are_never_mixed():
    """Balance-sheet lines carry no start date; that absence is exactly what
    separates them from flow concepts and must not collapse them together."""
    from api.index import _restatements
    found = _restatements([
        _fact("Cash", None, "2024-12-31", 50.0, "2025-01-01"),
        _fact("Cash", "2024-01-01", "2024-12-31", 90.0, "2025-01-01"),
    ])
    assert found == []


# ── macro context ─────────────────────────────────────────────────────────

def test_every_macro_observation_carries_its_own_publication_date():
    """Macro series publish on different cadences — the policy rate monthly,
    Treasury yields daily. One 'as of' for the block would be wrong for most
    of it, and a monthly series read today is still last month's number."""
    from unittest.mock import patch

    from api.index import _macro_context
    from src.providers.schemas import ProviderResult

    def fake(series_id, count=8):
        dates = {"FEDFUNDS": "2026-07-01", "DGS10": "2026-08-21",
                 "T10Y2Y": "2026-08-24", "DFII10": "2026-08-21"}
        return ProviderResult(data=[(dates[series_id], 4.0), (dates[series_id], 4.5)],
                              source="fred", confidence=0.85)

    with patch("src.providers.macro.get_series_snapshot", side_effect=fake):
        ctx = _macro_context({})

    assert {r["as_of"] for r in ctx["rates"]} == {
        "2026-07-01", "2026-08-21", "2026-08-24",
    }
    # And each row says what it changes about a valuation, not what it is.
    assert all(r["why"] for r in ctx["rates"])
    assert all(r["source"] == "FRED" for r in ctx["rates"])


def test_the_stress_inputs_that_gate_the_verdict_are_surfaced():
    """These four series gate the engine's verdict. Fetching them, scoring
    with them and discarding them meant a reader could be shown a dampened
    verdict with no way to see what dampened it."""
    from unittest.mock import patch

    from api.index import _macro_context
    from src.providers.schemas import ProviderResult

    stress = {"nfci": -0.559, "credit_spread_z": -0.674,
              "vix_percentile": 0.178, "term_spread": 0.46}
    with patch("src.providers.macro.get_series_snapshot",
               return_value=ProviderResult(data=None, error="x")):
        ctx = _macro_context(stress)

    keys = {row["key"] for row in ctx["stress"]}
    assert keys == set(stress)
    # Vendor-supplied versus computed here is a distinction the reader gets.
    by_key = {row["key"]: row for row in ctx["stress"]}
    assert "computed locally" in by_key["vix_percentile"]["source"]
    assert by_key["nfci"]["source"] == "FRED"


def test_a_missing_stress_input_is_omitted_rather_than_shown_as_zero():
    """A financial-conditions index of zero means 'exactly average', which is
    a specific and wrong claim about an input we simply do not have."""
    from unittest.mock import patch

    from api.index import _macro_context
    from src.providers.schemas import ProviderResult

    with patch("src.providers.macro.get_series_snapshot",
               return_value=ProviderResult(data=None, error="x")):
        ctx = _macro_context({"nfci": None, "vix_percentile": 0.5})
    assert {row["key"] for row in ctx["stress"]} == {"vix_percentile"}


def test_no_macro_data_at_all_yields_nothing_rather_than_an_empty_panel():
    from unittest.mock import patch

    from api.index import _macro_context
    from src.providers.schemas import ProviderResult

    with patch("src.providers.macro.get_series_snapshot",
               return_value=ProviderResult(data=None, error="x")):
        assert _macro_context({}) is None
