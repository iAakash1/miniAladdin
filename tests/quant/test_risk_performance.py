"""
Risk-adjusted performance metrics, pinned against hand-computed values.

The failure mode these guard is **double annualisation**: annualising a
per-period mean and then dividing by an already-annualised volatility inflates a
Sharpe by sqrt(periods_per_year) — 15.87x on daily data. It is silent, it makes
everything look excellent, and it is only catchable by checking the arithmetic
against a number computed independently. So every ratio here is asserted against
one.

The second failure mode is the degenerate case reported as a great result: a
zero-variance series yielding an infinite Sharpe, or an all-positive sample
yielding an infinite Sortino. Both must return None.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.risk import engine

PPY = 252.0
N = 120          # comfortably above MIN_OBSERVATIONS


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))


def _alternating(high: float, low: float, n: int = N) -> pd.Series:
    return _series([high if i % 2 == 0 else low for i in range(n)])


# ── Sharpe ───────────────────────────────────────────────────────────────────

def test_sharpe_matches_the_hand_computed_value():
    series = _alternating(0.02, -0.01)
    result = engine.sharpe(series, periods_per_year=PPY)

    expected = series.mean() / series.std(ddof=1) * np.sqrt(PPY)
    assert result.value == pytest.approx(expected)
    assert result.observations == N
    assert result.method == "mean_over_std_annualised"


def test_sharpe_annualises_exactly_once():
    """The regression that matters. Annualising twice inflates by sqrt(252)."""
    series = _alternating(0.02, -0.01)
    once = engine.sharpe(series, periods_per_year=PPY).value
    per_period = series.mean() / series.std(ddof=1)

    assert once == pytest.approx(per_period * np.sqrt(PPY))
    # And is nowhere near the doubly-annualised figure.
    assert once != pytest.approx(per_period * PPY, rel=1e-3)


def test_sharpe_subtracts_a_per_period_risk_free_rate():
    series = _alternating(0.02, -0.01)
    rf = 0.0001
    result = engine.sharpe(series, periods_per_year=PPY, risk_free=rf)
    expected = (series - rf).mean() / (series - rf).std(ddof=1) * np.sqrt(PPY)
    assert result.value == pytest.approx(expected)


def test_a_constant_series_has_no_sharpe():
    """Not infinity. An unbounded value would rank first in any leaderboard."""
    result = engine.sharpe(_series([0.001] * N), periods_per_year=PPY)
    assert result.value is None
    assert "zero variance" in result.caveat


# ── Sortino ──────────────────────────────────────────────────────────────────

def test_sortino_uses_downside_only_and_beats_sharpe_when_upside_is_volatile():
    """A series whose dispersion is mostly upside should score better."""
    series = _series(([0.05] * 3 + [-0.01]) * (N // 4))
    assert engine.sortino(series, periods_per_year=PPY).value > \
           engine.sharpe(series, periods_per_year=PPY).value


def test_sortino_matches_the_hand_computed_value():
    series = _alternating(0.02, -0.01)
    downside = np.sqrt(np.mean(np.square(np.minimum(series - 0.0, 0.0))))
    expected = series.mean() / downside * np.sqrt(PPY)
    assert engine.sortino(series, periods_per_year=PPY).value == pytest.approx(expected)


def test_an_all_positive_series_has_no_sortino():
    result = engine.sortino(_series(np.linspace(0.001, 0.01, N)), periods_per_year=PPY)
    assert result.value is None
    assert "no observation below" in result.caveat


# ── Calmar ───────────────────────────────────────────────────────────────────

def test_calmar_is_the_geometric_rate_over_the_worst_drawdown():
    series = _alternating(0.02, -0.01)
    worst = engine.max_drawdown(series, compound=True).value
    growth = float((1.0 + series).prod())
    expected = (growth ** (PPY / len(series)) - 1.0) / abs(worst)
    assert engine.calmar(series, periods_per_year=PPY).value == pytest.approx(expected)


def test_a_series_that_never_falls_has_no_calmar():
    result = engine.calmar(_series([0.001] * N), periods_per_year=PPY)
    assert result.value is None
    assert "no drawdown" in result.caveat


# ── benchmark-relative ───────────────────────────────────────────────────────

def test_tracking_error_aligns_on_the_index_before_differencing():
    """Misaligned series must not be subtracted positionally."""
    full = _alternating(0.02, -0.01)
    partial = full.iloc[10:]                      # different length AND offset
    result = engine.tracking_error(full, partial, periods_per_year=PPY)
    assert result.observations == len(partial), "must inner-join, not truncate"
    assert result.value == pytest.approx(0.0, abs=1e-12), (
        "a series against itself has zero tracking error once aligned"
    )


def test_information_ratio_matches_the_hand_computed_value():
    portfolio = _alternating(0.02, -0.01)
    benchmark = _series(np.full(N, 0.001))
    active = portfolio - benchmark
    expected = active.mean() / active.std(ddof=1) * np.sqrt(PPY)
    assert engine.information_ratio(portfolio, benchmark,
                                    periods_per_year=PPY).value == pytest.approx(expected)


def test_a_portfolio_tracking_exactly_has_no_information_ratio():
    series = _alternating(0.02, -0.01)
    result = engine.information_ratio(series, series, periods_per_year=PPY)
    assert result.value is None
    assert "zero variance" in result.caveat


def test_capm_alpha_is_zero_for_a_portfolio_that_is_the_benchmark():
    series = _alternating(0.02, -0.01)
    assert engine.capm_alpha(series, series, periods_per_year=PPY).value == pytest.approx(0.0, abs=1e-9)


def test_capm_alpha_recovers_a_known_intercept():
    """beta 2, per-period alpha 0.001 -> annualised 0.001 * 252."""
    rng = np.random.default_rng(0)
    market = _series(rng.normal(0.0005, 0.01, N))
    portfolio = 0.001 + 2.0 * market
    result = engine.capm_alpha(portfolio, market, periods_per_year=PPY)
    assert result.value == pytest.approx(0.001 * PPY, rel=1e-6)
    assert "six-factor" in result.caveat, "must not be confused with the research alpha"


# ── drawdown profile ─────────────────────────────────────────────────────────

def test_drawdown_profile_reports_duration_and_recovery():
    # rise 10, fall 10, recover 20 — recovery is reachable within the sample.
    values = [0.02] * 10 + [-0.02] * 10 + [0.02] * 20 + [0.0] * (N - 40)
    profile = engine.drawdown_profile(_series(values))
    assert profile["max_drawdown"] < 0
    assert profile["drawdown_periods"] == 10
    assert profile["recovered"] is True
    assert profile["recovery_periods"] > 0


def test_an_unrecovered_drawdown_reports_no_recovery_time():
    """Not the sample length — that would measure when we stopped looking."""
    values = [0.02] * 10 + [-0.03] * (N - 10)
    profile = engine.drawdown_profile(_series(values))
    assert profile["recovered"] is False
    assert profile["recovery_periods"] is None
    assert "still underwater" in profile["caveat"]


# ── distribution ─────────────────────────────────────────────────────────────

def test_distribution_flags_fat_tails():
    values = list(np.full(N - 2, 0.001)) + [0.5, -0.5]
    result = engine.distribution(_series(values))
    assert result["excess_kurtosis"] > engine.KURTOSIS_WARNING
    assert result["gaussian_reasonable"] is False
    assert "fat tails" in result["caveat"]


def test_distribution_accepts_a_well_behaved_sample():
    rng = np.random.default_rng(7)
    result = engine.distribution(_series(rng.normal(0.0, 0.01, 2000)))
    assert result["gaussian_reasonable"] is True
    assert result["caveat"] is None


# ── shared edge cases ────────────────────────────────────────────────────────

@pytest.mark.parametrize("fn", [engine.sharpe, engine.sortino, engine.calmar])
def test_a_short_sample_refuses_rather_than_estimating(fn):
    result = fn(_series([0.01, -0.01, 0.02]), periods_per_year=PPY)
    assert result.value is None
    assert "INSUFFICIENT DATA" in result.caveat


@pytest.mark.parametrize("fn", [engine.sharpe, engine.sortino])
def test_nan_and_inf_are_dropped_not_propagated(fn):
    values = [0.02 if i % 2 == 0 else -0.01 for i in range(N)]
    dirty = list(values) + [np.nan, np.inf, -np.inf]
    assert fn(_series(dirty), periods_per_year=PPY).value == pytest.approx(
        fn(_series(values), periods_per_year=PPY).value
    )


# ── numerical robustness ─────────────────────────────────────────────────────

@pytest.mark.parametrize("constant", [0.0, 0.001, -0.05, 1e-9])
def test_a_constant_series_never_produces_a_finite_ratio(constant):
    """The bug this guard exists for.

    120 identical floats have a sample standard deviation near 1e-19, not zero,
    so an exact `<= 0` check passes and the ratio explodes. A constant series
    once produced a Sharpe of 3.6e16 — a number that would rank first in any
    leaderboard while describing a series that never moved.
    """
    series = _series([constant] * N)
    for result in (engine.sharpe(series, periods_per_year=PPY),
                   engine.information_ratio(series, series, periods_per_year=PPY)):
        assert result.value is None
        assert result.caveat is not None


def test_a_near_constant_series_is_treated_as_constant():
    """Dispersion at the float-noise scale is not information."""
    series = _series([0.001 + i * 1e-18 for i in range(N)])
    assert engine.sharpe(series, periods_per_year=PPY).value is None


def test_a_genuinely_small_but_real_dispersion_still_computes():
    """The guard must not swallow a real, tiny signal."""
    series = _series([0.001 + (1e-6 if i % 2 else -1e-6) for i in range(N)])
    result = engine.sharpe(series, periods_per_year=PPY)
    assert result.value is not None and np.isfinite(result.value)
