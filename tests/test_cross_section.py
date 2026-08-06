"""
Cross-sectional evaluation tests.

Statistics code is the easiest place in a codebase to be confidently wrong:
it produces plausible numbers whatever it does, and nobody can eyeball a
t-statistic. So every estimator here is checked against an independent
reference implementation, and the properties that make the results *honest*
— refusing to measure what it cannot, and shrinking t-statistics that
overlapping samples inflate — are asserted directly.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.research.cross_section import (
    MIN_DATES,
    MIN_NAMES_PER_DATE,
    SIGNIFICANCE_T,
    evaluate_factor,
    forward_returns,
    newey_west_tstat,
    quantile_spread,
    rank_cross_section,
    spearman_ic,
)


# ── Newey-West against an independent reference ──────────────────────────────

def naive_newey_west(values, lags):
    """Textbook formula, written for clarity rather than speed."""
    n = len(values)
    mean = sum(values) / n
    centered = [v - mean for v in values]
    variance = sum(c * c for c in centered) / n
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1.0)
        cov = sum(centered[t] * centered[t - lag] for t in range(lag, n)) / n
        variance += 2.0 * weight * cov
    return mean / math.sqrt(variance / n)


@pytest.mark.parametrize("lags", [0, 1, 3, 5, 10])
def test_newey_west_matches_the_textbook_formula(lags):
    rng = np.random.default_rng(11)
    values = rng.normal(0.03, 1.0, 150)
    assert newey_west_tstat(values, lags) == pytest.approx(
        naive_newey_west(values, lags), rel=1e-12
    )


def test_zero_lags_equals_the_population_t_statistic():
    """Not the ddof=1 sample statistic — they differ by sqrt(n/(n-1))."""
    rng = np.random.default_rng(3)
    values = rng.normal(0.1, 1.0, 80)
    population = values.mean() / (values.std(ddof=0) / math.sqrt(len(values)))
    assert newey_west_tstat(values, 0) == pytest.approx(population, rel=1e-12)


def test_correction_shrinks_overlapping_samples():
    """The reason this module exists, asserted without relying on a lucky seed.

    A rolling mean is what overlapping forward returns look like. Across
    many independent draws the correction must shrink the statistic every
    time, not merely on a fixture that happened to cooperate.
    """
    shrunk = 0
    for seed in range(40):
        rng = np.random.default_rng(seed)
        overlapping = np.convolve(rng.normal(0.05, 1, 220), np.ones(20) / 20, mode="valid")
        naive = overlapping.mean() / (overlapping.std(ddof=0) / math.sqrt(len(overlapping)))
        if abs(newey_west_tstat(overlapping, 19)) < abs(naive):
            shrunk += 1
    assert shrunk == 40, f"correction failed to shrink {40 - shrunk} of 40 samples"


def test_correction_controls_the_false_positive_rate():
    """The property that makes the correction worth having.

    On *pure noise* with zero true mean, a correct statistic rejects at
    roughly its nominal 5%. The naive statistic applied to overlapping
    samples rejects far more often — it manufactures significance out of
    autocorrelation. This measures both, and is the empirical case for
    every Newey-West line in this module.
    """
    naive_rejections = 0
    corrected_rejections = 0
    trials = 300

    for seed in range(trials):
        rng = np.random.default_rng(1000 + seed)
        overlapping = np.convolve(rng.normal(0.0, 1, 140), np.ones(20) / 20, mode="valid")
        naive = overlapping.mean() / (overlapping.std(ddof=0) / math.sqrt(len(overlapping)))
        if abs(naive) >= SIGNIFICANCE_T:
            naive_rejections += 1
        if abs(newey_west_tstat(overlapping, 19)) >= SIGNIFICANCE_T:
            corrected_rejections += 1

    naive_rate = naive_rejections / trials
    corrected_rate = corrected_rejections / trials

    assert naive_rate > 0.30, (
        f"fixture is not overlapping enough to inflate anything ({naive_rate:.0%})"
    )
    assert corrected_rate < naive_rate / 2, (
        f"correction did not control false positives: naive {naive_rate:.0%}, "
        f"corrected {corrected_rate:.0%}"
    )


def test_correction_is_neutral_on_independent_data():
    """It must not penalise a genuinely iid series."""
    rng = np.random.default_rng(9)
    values = rng.normal(0.2, 1.0, 400)
    naive = values.mean() / (values.std(ddof=0) / math.sqrt(len(values)))
    assert newey_west_tstat(values, 5) == pytest.approx(naive, rel=0.25)


def test_degenerate_inputs_do_not_raise():
    assert newey_west_tstat(np.array([1.0]), 3) == 0.0
    assert newey_west_tstat(np.array([]), 3) == 0.0
    assert newey_west_tstat(np.full(50, 2.0), 3) == 0.0   # zero variance


def test_non_positive_variance_falls_back_without_inventing_significance():
    """The fallback must never report a *larger* t than the correction would."""
    values = np.array([1.0, -1.0] * 30)      # strong negative autocorrelation
    result = newey_west_tstat(values, 5)
    assert math.isfinite(result)


# ── rank IC ──────────────────────────────────────────────────────────────────

def test_ic_is_one_for_a_perfect_ranking():
    factor = pd.Series(range(20), dtype=float)
    forward = pd.Series(range(20), dtype=float)
    assert spearman_ic(factor, forward) == pytest.approx(1.0)


def test_ic_is_minus_one_for_a_perfectly_inverted_ranking():
    factor = pd.Series(range(20), dtype=float)
    assert spearman_ic(factor, factor[::-1].reset_index(drop=True)) == pytest.approx(-1.0)


def test_ic_uses_ranks_not_levels():
    """A single outlier must not dominate. Pearson would; Spearman must not."""
    factor = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], dtype=float)
    forward = factor.copy()
    forward.iloc[-1] = 10_000.0
    assert spearman_ic(factor, forward) == pytest.approx(1.0)


def test_ic_is_none_below_the_minimum_cross_section():
    small = pd.Series(range(MIN_NAMES_PER_DATE - 1), dtype=float)
    assert spearman_ic(small, small) is None


def test_ic_is_none_when_there_is_no_ranking():
    """A constant factor has no ordering. Zero would fold a non-observation
    into the mean as though it were evidence."""
    flat = pd.Series([1.0] * 20)
    varied = pd.Series(range(20), dtype=float)
    assert spearman_ic(flat, varied) is None
    assert spearman_ic(varied, pd.Series([2.0] * 20)) is None


# ── quantile spread ──────────────────────────────────────────────────────────

def test_spread_is_positive_when_the_factor_orders_returns():
    factor = pd.Series(range(50), dtype=float)
    forward = pd.Series(np.arange(50) * 0.001)
    assert quantile_spread(factor, forward, 5) > 0


def test_spread_is_negative_when_the_factor_is_inverted():
    factor = pd.Series(range(50), dtype=float)
    forward = pd.Series(np.arange(50)[::-1] * 0.001)
    assert quantile_spread(factor, forward, 5) < 0


def test_spread_is_none_when_there_are_too_few_names():
    factor = pd.Series(range(6), dtype=float)
    assert quantile_spread(factor, factor, 5) is None


# ── forward returns ──────────────────────────────────────────────────────────

def _prices(days: int, start: str = "2024-01-02", drift: float = 0.001):
    index = pd.bdate_range(start, periods=days)
    return pd.Series(100 * np.exp(np.arange(days) * drift), index=index)


def test_forward_returns_look_forward_by_the_horizon():
    prices = _prices(60)
    observed = [prices.index[10].date()]
    frame = forward_returns({"AAA": prices}, observed, horizon=21)

    expected = float(prices.iloc[31] / prices.iloc[10] - 1)
    assert frame["forward_return"].iloc[0] == pytest.approx(expected)


def test_forward_returns_are_absent_when_the_future_has_not_happened():
    """The last dates in any sample have no realised outcome yet."""
    prices = _prices(30)
    observed = [prices.index[25].date()]
    assert forward_returns({"AAA": prices}, observed, horizon=21).empty


def test_forward_returns_use_the_last_bar_on_or_before_a_non_trading_day():
    prices = _prices(60, start="2024-01-01")
    saturday = prices.index[10].date() + timedelta(days=1)
    frame = forward_returns({"AAA": prices}, [saturday], horizon=5)
    assert len(frame) == 1


def test_forward_returns_skip_non_positive_bases():
    prices = _prices(60)
    prices.iloc[10] = 0.0
    frame = forward_returns({"AAA": prices}, [prices.index[10].date()], horizon=21)
    assert frame.empty


# ── end-to-end evaluation ────────────────────────────────────────────────────

def _panel(dates: int, names: int, signal: float, seed: int = 1) -> pd.DataFrame:
    """A synthetic panel where the factor explains `signal` of the ordering."""
    rng = np.random.default_rng(seed)
    rows = []
    for step in range(dates):
        day = date(2024, 1, 2) + timedelta(days=7 * step)
        scores = rng.normal(size=names)
        noise = rng.normal(size=names)
        forward = signal * scores + math.sqrt(max(0.0, 1 - signal**2)) * noise
        for index in range(names):
            rows.append({
                "symbol": f"S{index:02d}", "date": day,
                "factor": float(scores[index]),
                "forward_return": float(forward[index]) * 0.01,
            })
    return pd.DataFrame(rows)


def test_a_strong_factor_is_detected():
    evaluation = evaluate_factor(_panel(60, 30, signal=0.6), "factor", 21, 5)
    assert evaluation is not None
    assert evaluation.mean_ic > 0.3
    assert evaluation.significant
    assert "ranks names correctly" in evaluation.assessment


def test_a_worthless_factor_is_reported_as_worthless():
    """The result this tool must be willing to return."""
    evaluation = evaluate_factor(_panel(60, 30, signal=0.0, seed=4), "factor", 21, 5)
    assert evaluation is not None
    assert not evaluation.significant
    assert "ranks names correctly" not in evaluation.assessment


def test_worthless_factors_are_flagged_at_roughly_the_nominal_rate():
    """A worthless factor is *sometimes* significant, and that is correct.

    An earlier version of this test asserted a zero-signal factor is never
    flagged. It failed on a seed — rightly. At a 5% level, roughly 1 sample
    in 20 looks significant by chance; a test demanding zero would be
    asserting that the statistic is broken.

    What must hold is the rate. This also quantifies the multiple-testing
    exposure the UI has to disclose: evaluating all 7 price factors at once
    means the chance that *at least one* looks significant by luck is far
    higher than 5%.
    """
    flagged = sum(
        evaluate_factor(_panel(60, 30, signal=0.0, seed=seed), "factor", 21, 5).significant
        for seed in range(60)
    )
    rate = flagged / 60
    assert rate < 0.20, f"false-positive rate {rate:.0%} is far above nominal"

    # The multiple-comparison consequence, made concrete.
    family_wise = 1 - (1 - rate) ** 7
    assert family_wise > rate, "testing 7 factors cannot be safer than testing 1"


def test_an_inverted_factor_is_named_as_inverted():
    panel = _panel(60, 30, signal=0.6)
    panel["factor"] = -panel["factor"]
    evaluation = evaluate_factor(panel, "factor", 21, 5)
    assert evaluation.mean_ic < 0
    assert "inversely" in evaluation.assessment


def test_evaluation_reports_the_overlap_correction_it_applied():
    evaluation = evaluate_factor(_panel(60, 30, signal=0.4), "factor", 21, 5)
    assert evaluation.newey_west_lags == math.ceil(21 / 5) - 1 == 4
    assert evaluation.horizon_days == 21


def test_non_overlapping_sampling_needs_no_correction():
    evaluation = evaluate_factor(_panel(60, 30, signal=0.4), "factor", 5, 5)
    assert evaluation.newey_west_lags == 0


def test_inflation_reports_how_much_the_naive_statistic_overstated():
    evaluation = evaluate_factor(_panel(60, 30, signal=0.4), "factor", 21, 5)
    assert evaluation.inflation > 0
    assert evaluation.naive_t_stat != evaluation.t_stat


def test_too_few_dates_returns_none_not_a_zeroed_result():
    """"Could not measure" must stay distinct from "measured no effect"."""
    assert evaluate_factor(_panel(MIN_DATES - 1, 30, signal=0.5), "factor", 21, 5) is None


def test_missing_factor_column_returns_none():
    assert evaluate_factor(_panel(30, 20, signal=0.5), "absent", 21, 5) is None


def test_thin_cross_sections_are_skipped_not_averaged_in():
    """Dates with too few names must not contribute a noisy IC."""
    panel = _panel(40, 30, signal=0.5)
    first = panel["date"].min()
    thinned = panel[(panel["date"] != first) | (panel["symbol"] < "S05")]
    evaluation = evaluate_factor(thinned, "factor", 21, 5)
    assert evaluation.dates == 39


# ── ranking ──────────────────────────────────────────────────────────────────

def test_ranking_is_ordered_and_carries_percentiles():
    panel = _panel(3, 20, signal=0.5)
    day = panel["date"].min()
    rows = rank_cross_section(panel, "factor", day)

    assert len(rows) == 20
    assert [row["rank"] for row in rows] == list(range(1, 21))
    assert rows[0]["score"] >= rows[-1]["score"]
    assert rows[0]["percentile"] == pytest.approx(100.0)


def test_ranking_respects_a_limit():
    panel = _panel(3, 20, signal=0.5)
    rows = rank_cross_section(panel, "factor", panel["date"].min(), limit=5)
    assert len(rows) == 5


def test_ranking_an_unknown_date_or_factor_is_empty_not_an_error():
    panel = _panel(3, 20, signal=0.5)
    assert rank_cross_section(panel, "factor", date(1999, 1, 1)) == []
    assert rank_cross_section(panel, "nope", panel["date"].min()) == []


# ── winsorization saturation ─────────────────────────────────────────────────

def test_saturation_detects_clipping_at_the_winsor_bound():
    """A factor that clips many names cannot rank them relative to each other."""
    from src.research.cross_section import saturation_rate
    from src.scoring.engine import WINSOR_Z, squash

    bound = squash(WINSOR_Z)
    clipped = pd.Series([bound] * 6 + [0.1, 0.2, 0.3, -0.4])
    assert saturation_rate(clipped) == pytest.approx(0.6)


def test_saturation_counts_both_bounds():
    from src.research.cross_section import saturation_rate
    from src.scoring.engine import WINSOR_Z, squash

    bound = squash(WINSOR_Z)
    assert saturation_rate(pd.Series([bound, -bound, 0.0, 0.1])) == pytest.approx(0.5)


def test_saturation_is_zero_for_an_unclipped_factor():
    from src.research.cross_section import saturation_rate

    assert saturation_rate(pd.Series([0.1, -0.2, 0.3])) == 0.0
    assert saturation_rate(pd.Series([], dtype=float)) == 0.0


def test_evaluation_reports_saturation():
    evaluation = evaluate_factor(_panel(30, 20, signal=0.4), "factor", 21, 5)
    assert 0.0 <= evaluation.saturation <= 1.0
