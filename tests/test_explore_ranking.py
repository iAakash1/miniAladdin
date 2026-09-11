"""What Explore puts first, and why.

The ordering is the product claim, so these tests are about ordering rather
than about plumbing. Three properties matter most.

**Monotonicity.** Changing one input in the worse direction must never
improve a security's position. Written explicitly because a weighted sum with
one sign flipped — using `risk_score` where `100 - risk_score` was meant —
still produces a plausible-looking ranked list, and nothing else in the
system would notice.

**Unknown must not win.** A security we know little about has few factors,
few factors mean little disagreement, little disagreement means high
confidence and low measured risk. On a naive ranking the name we understand
least sorts first. The eligibility policy exists to stop that, and this file
holds it to it.

**Trending is not buying.** A security can lead the trending list while
carrying a SELL verdict, and both statements have to survive to the reader.
"""

import pytest

from src.services import explore_eligibility as eligibility
from src.services import explore_ranking as ranking
from src.services.explore_service import (
    CATEGORIES, ExploreFilters, ExploreRow, ExploreSnapshot, rank, recommendations,
)


def _row(symbol="X", **kw):
    base = dict(
        company_name=f"{symbol} Inc.", sector="Information Technology", eligible=True,
        price=100.0, model_signal="Buy", signal_strength=0.3, signal_percentile=70.0,
        confidence=70, risk_score=40, data_completeness=0.9, overall_rank=70.0,
    )
    base.update(kw)
    return ExploreRow(symbol=symbol, **base)


def _snapshot(rows):
    return ExploreSnapshot(
        generated_at="2026-09-11T00:00:00+00:00", universe_version="us-v1",
        rows=rows, eligible_count=sum(1 for r in rows if r.eligible),
        evaluated_count=len(rows),
    )


# ── percentiles ──────────────────────────────────────────────────────────────

def test_ties_share_a_percentile():
    """Otherwise the ranking changes when the input file is re-sorted."""
    assert ranking.percentile_rank(5, [5, 5, 5, 5]) == 50.0


def test_a_missing_value_has_no_percentile():
    """Not 50. An unmeasured security must not be handed an average."""
    assert ranking.percentile_rank(None, [1, 2, 3]) is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_value_has_no_percentile(bad):
    assert ranking.percentile_rank(bad, [1.0, 2.0, 3.0]) is None


def test_ordering_is_preserved():
    population = [1.0, 2.0, 3.0, 4.0]
    ranks = [ranking.percentile_rank(v, population) for v in population]
    assert ranks == sorted(ranks)


# ── monotonicity ─────────────────────────────────────────────────────────────

def _rank(**kw):
    base = dict(signal_percentile=60.0, confidence=60.0, risk_score=50.0,
                data_completeness_pct=80.0)
    base.update(kw)
    return ranking.overall_rank(**base)


def test_more_risk_alone_never_improves_the_ranking():
    assert _rank(risk_score=80.0) < _rank(risk_score=20.0)


def test_more_confidence_alone_never_lowers_the_ranking():
    assert _rank(confidence=90.0) > _rank(confidence=30.0)


def test_a_stronger_signal_alone_never_lowers_the_ranking():
    assert _rank(signal_percentile=95.0) > _rank(signal_percentile=5.0)


def test_more_complete_evidence_alone_never_lowers_the_ranking():
    assert _rank(data_completeness_pct=100.0) > _rank(data_completeness_pct=60.0)


def test_the_composite_stays_inside_nought_to_a_hundred():
    assert _rank(signal_percentile=100.0, confidence=100.0, risk_score=0.0,
                 data_completeness_pct=100.0) == pytest.approx(100.0)
    assert _rank(signal_percentile=0.0, confidence=0.0, risk_score=100.0,
                 data_completeness_pct=0.0) == pytest.approx(0.0)


def test_a_missing_component_refuses_to_produce_a_rank():
    """Strict rather than tolerant: a default would let absence act as
    evidence, and eligibility has already refused anything incomplete."""
    assert _rank(confidence=None) is None
    assert _rank(risk_score=None) is None


def test_the_weights_sum_to_one():
    total = (ranking.WEIGHT_SIGNAL + ranking.WEIGHT_CONFIDENCE
             + ranking.WEIGHT_INVERSE_RISK + ranking.WEIGHT_COMPLETENESS)
    assert total == pytest.approx(1.0)


# ── unknown must not win ─────────────────────────────────────────────────────

def test_a_thinly_covered_security_is_excluded_however_confident():
    """The specific failure this policy exists to prevent."""
    verdict = eligibility.assess(
        asset_type="common_equity", bars=300, price=100.0, price_age_days=0.0,
        has_scorecard=True, data_completeness=0.20, confidence=99,
    )
    assert not verdict.eligible
    assert "insufficient_data_completeness" in verdict.reasons


@pytest.mark.parametrize("confidence", [33, 36, 44, 48])
def test_a_healthy_large_cap_confidence_is_not_excluded(confidence):
    """The gate must not fire on the ordinary bottom of the healthy band.

    Measured over twelve well-covered large caps the engine produced 33-48
    (median 44) at full data completeness. An earlier floor of 35 excluded a
    mega-cap sitting at 33, which is a gate rejecting noise rather than
    uncertainty.
    """
    verdict = eligibility.assess(
        asset_type="common_equity", bars=300, price=100.0, price_age_days=0.0,
        has_scorecard=True, data_completeness=1.0, confidence=confidence,
    )
    assert verdict.eligible, verdict.reasons


def test_a_genuinely_unsure_reading_is_still_excluded():
    """The floor still has to mean something. 5 is the engine's clip floor."""
    verdict = eligibility.assess(
        asset_type="common_equity", bars=300, price=100.0, price_age_days=0.0,
        has_scorecard=True, data_completeness=1.0, confidence=8,
    )
    assert not verdict.eligible and "low_confidence" in verdict.reasons


def test_a_stale_price_is_excluded():
    verdict = eligibility.assess(
        asset_type="common_equity", bars=300, price=100.0,
        price_age_days=eligibility.MAX_PRICE_AGE_DAYS + 1,
        has_scorecard=True, data_completeness=0.95, confidence=80,
    )
    assert not verdict.eligible and "price_stale" in verdict.reasons


def test_a_zero_day_old_price_is_the_freshest_not_a_missing_one():
    """Truthiness here would read today's price as no price at all."""
    verdict = eligibility.assess(
        asset_type="common_equity", bars=300, price=100.0, price_age_days=0.0,
        has_scorecard=True, data_completeness=0.95, confidence=80,
    )
    assert verdict.eligible


def test_an_etf_is_not_ranked_among_stocks():
    verdict = eligibility.assess(
        asset_type="etf", bars=300, price=100.0, price_age_days=0.0,
        has_scorecard=True, data_completeness=0.95, confidence=80,
    )
    assert not verdict.eligible and "not_common_equity" in verdict.reasons


def test_every_failure_is_reported_not_just_the_first():
    verdict = eligibility.assess(
        asset_type=None, bars=None, price=None, price_age_days=None,
        has_scorecard=False, data_completeness=None, confidence=None,
    )
    assert len(verdict.reasons) >= 5


def test_unknown_risk_never_appears_as_low_risk():
    """`Low Risk` must not be a list of securities we failed to measure."""
    assert ranking.risk_level(None) is None
    rows = [_row("MEASURED", risk_score=30), _row("UNMEASURED", risk_score=None)]
    ordered = rank(_snapshot(rows), "low_risk")
    assert [r.symbol for r in ordered] == ["MEASURED"]


# ── trending is not buying ───────────────────────────────────────────────────

def test_a_sell_rated_security_can_lead_trending():
    rows = [
        _row("FALLING", model_signal="Sell", trend_score=95.0,
             trend_direction="trending_down", overall_rank=20.0),
        _row("STEADY", model_signal="Buy", trend_score=10.0,
             trend_direction="high_attention", overall_rank=88.0),
    ]
    snapshot = _snapshot(rows)

    assert [r.symbol for r in rank(snapshot, "trending")] == ["FALLING", "STEADY"]
    # And its verdict survives the trip — trending never rewrites the signal.
    assert rank(snapshot, "trending")[0].model_signal == "Sell"
    # While the overall ordering is unmoved by attention.
    assert [r.symbol for r in rank(snapshot, "overall")] == ["STEADY", "FALLING"]


def test_trend_direction_distinguishes_a_rally_from_a_collapse():
    assert ranking.trend_direction(0.20, 0.10) == "trending_up"
    assert ranking.trend_direction(-0.20, -0.10) == "trending_down"
    assert ranking.trend_direction(0.0, 0.0) == "high_attention"
    assert ranking.trend_direction(None, None) == "high_attention"


def test_trend_renormalises_over_the_components_that_exist():
    """Missing components are dropped, never filled with a neutral value."""
    both = ranking.trend_score({"momentum_21d": 80.0, "momentum_5d": 80.0})
    assert both == pytest.approx(80.0)
    assert ranking.trend_score({}) is None


# ── filters and categories ───────────────────────────────────────────────────

def test_a_filter_excludes_rows_that_cannot_answer_it():
    """"Risk under 40" must not return securities with unmeasured risk."""
    rows = [_row("A", risk_score=20), _row("B", risk_score=None)]
    ordered = rank(_snapshot(rows), "overall", ExploreFilters(max_risk=40))
    assert [r.symbol for r in ordered] == ["A"]


def test_sector_and_signal_filters_apply():
    rows = [
        _row("A", sector="Energy", model_signal="Buy"),
        _row("B", sector="Financials", model_signal="Buy"),
        _row("C", sector="Energy", model_signal="Sell"),
    ]
    snapshot = _snapshot(rows)
    assert [r.symbol for r in rank(snapshot, "overall", ExploreFilters(sector="Energy"))] == ["A", "C"]
    assert [r.symbol for r in rank(snapshot, "overall", ExploreFilters(model_signal="Sell"))] == ["C"]


def test_ineligible_rows_never_appear():
    rows = [_row("GOOD"), _row("BAD", eligible=False, exclusion_reasons=["price_stale"])]
    assert [r.symbol for r in rank(_snapshot(rows), "overall")] == ["GOOD"]


def test_an_unknown_category_is_refused():
    with pytest.raises(KeyError):
        rank(_snapshot([_row()]), "guaranteed_winners")


def test_every_category_orders_by_a_field_the_row_actually_has():
    for category in CATEGORIES:
        assert category.field in ExploreRow.model_fields, category.key


def test_low_risk_sorts_ascending_and_the_rest_descending():
    by_key = {c.key: c for c in CATEGORIES}
    assert by_key["low_risk"].descending is False
    assert by_key["overall"].descending is True


# ── recommendations ──────────────────────────────────────────────────────────

def test_recommendations_are_computed_not_listed():
    """No symbol is named anywhere in the ranking path.

    Reversing the ranking must reverse the output. A hard-coded list would
    survive that and this test would not.
    """
    rows = [_row("AAA", overall_rank=10.0), _row("BBB", overall_rank=99.0)]
    assert [r.symbol for r in recommendations(_snapshot(rows), 2)] == ["BBB", "AAA"]

    flipped = [_row("AAA", overall_rank=99.0), _row("BBB", overall_rank=10.0)]
    assert [r.symbol for r in recommendations(_snapshot(flipped), 2)] == ["AAA", "BBB"]


def test_no_ticker_is_hard_coded_in_the_ranking_modules():
    """A configured universe is fine. A configured winner is not."""
    import pathlib
    import re

    from src.services.universe import load_universe

    # Checked against the real universe rather than against a shape. A
    # shape-based detector fires on "LOW" and "HIGH" — which are risk levels,
    # not securities — and a detector that cries wolf is one somebody deletes.
    members = {c.symbol.upper() for c in load_universe().constituents}
    assert "AAPL" in members, "the universe should be loaded for this to mean anything"

    for name in ("explore_service.py", "explore_ranking.py", "explore_eligibility.py"):
        source = pathlib.Path("src/services") / name
        body = "\n".join(
            line for line in source.read_text().splitlines()
            if not line.strip().startswith("#")
        )
        # LOW, MEDIUM and HIGH are risk levels. "LOW" is also Lowe's ticker
        # and Lowe's is in the universe, so a membership test alone flags the
        # risk vocabulary — excluded by name rather than by loosening the
        # pattern, which would stop catching real symbols.
        vocabulary = {"LOW", "MEDIUM", "HIGH", "SPY"}
        named = {
            t for t in re.findall(r'"([A-Z][A-Z.]{0,6})"', body)
            if t in members and t not in vocabulary
        }
        assert not named, f"{name} names universe securities directly: {named}"


def test_an_empty_eligible_set_returns_nothing_rather_than_relaxing_a_gate():
    rows = [_row("A", eligible=False), _row("B", eligible=False)]
    assert recommendations(_snapshot(rows), 5) == []
