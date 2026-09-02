"""Entropic, Gini, Omega and partial-moment measures, tested against identities.

Where a closed form exists for a known distribution, the test uses it. Where one
does not, the test uses an ordering that holds by construction rather than a
number copied from the implementation — a test that asserts what the code
already returns proves only that it is deterministic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.risk import coherent
from src.quant.risk import engine as risk


def _normal(n: int = 600, mu: float = 0.0004, sigma: float = 0.012, seed: int = 0):
    rng = np.random.default_rng(seed)
    return pd.Series(
        rng.normal(mu, sigma, n), index=pd.bdate_range("2020-01-01", periods=n)
    )


# ── the ordering identity ────────────────────────────────────────────────────

@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("confidence", [0.90, 0.95, 0.99])
def test_var_le_cvar_le_evar(seed: int, confidence: float) -> None:
    """Holds by construction for every sample, not on average."""
    series = _normal(seed=seed)
    var = risk.var_historical(series, confidence=confidence).value
    cvar = risk.cvar_historical(series, confidence=confidence).value
    evar = coherent.entropic_value_at_risk(series, confidence=confidence)
    assert var <= cvar + 1e-12
    assert cvar <= evar + 1e-9


def test_the_three_collapse_when_there_is_no_tail() -> None:
    """A constant series has one loss and all three measures equal it."""
    series = pd.Series([-0.01] * 200, index=pd.bdate_range("2020-01-01", periods=200))
    evar = coherent.entropic_value_at_risk(series, confidence=0.95)
    assert evar == pytest.approx(0.01, rel=1e-6)


def test_evar_is_monotone_in_confidence() -> None:
    series = _normal(seed=2)
    levels = [0.80, 0.90, 0.95, 0.99]
    values = [coherent.entropic_value_at_risk(series, confidence=c) for c in levels]
    assert values == sorted(values)


def test_evar_survives_a_fat_tail_without_overflowing() -> None:
    """The objective evaluates exp(L/z) for small z; naive code returns inf."""
    rng = np.random.default_rng(4)
    series = pd.Series(rng.standard_t(3, 500) * 0.02)
    value = coherent.entropic_value_at_risk(series, confidence=0.95)
    assert value is not None and np.isfinite(value) and value > 0


# ── Gini against its closed form ─────────────────────────────────────────────

def test_gini_matches_the_normal_closed_form() -> None:
    """For a normal, the mean absolute difference is sigma * 2 / sqrt(pi)."""
    sigma = 0.02
    rng = np.random.default_rng(7)
    series = pd.Series(rng.normal(0.0, sigma, 40_000))
    expected = sigma * 2.0 / np.sqrt(np.pi)
    assert coherent.gini_mean_difference(series) == pytest.approx(expected, rel=0.02)


def test_gini_matches_the_uniform_closed_form() -> None:
    """For U(0, 1), the mean absolute difference is 1/3."""
    rng = np.random.default_rng(9)
    series = pd.Series(rng.uniform(0.0, 1.0, 40_000))
    assert coherent.gini_mean_difference(series) == pytest.approx(1 / 3, rel=0.02)


def test_gini_agrees_with_the_brute_force_double_sum() -> None:
    """The O(n log n) rank identity must equal the O(n^2) definition."""
    rng = np.random.default_rng(11)
    values = rng.normal(0, 0.02, 120)
    n = len(values)
    brute = sum(
        abs(values[i] - values[j]) for i in range(n) for j in range(n) if i != j
    ) / (n * (n - 1))
    assert coherent.gini_mean_difference(pd.Series(values)) == pytest.approx(brute)


def test_gini_is_zero_for_a_constant_series() -> None:
    assert coherent.gini_mean_difference(pd.Series([0.01] * 50)) == pytest.approx(0.0)


# ── Omega and partial moments ────────────────────────────────────────────────

def test_omega_at_the_median_of_a_symmetric_series_is_one() -> None:
    values = pd.Series([-3.0, -2.0, -1.0, 1.0, 2.0, 3.0])
    assert coherent.omega_ratio(values, threshold=0.0) == pytest.approx(1.0)


def test_omega_is_none_when_nothing_falls_below_the_threshold() -> None:
    """Unbounded, and a huge number would read as a spectacular result."""
    assert coherent.omega_ratio(pd.Series([0.01] * 50), threshold=0.0) is None


def test_omega_rises_as_the_threshold_falls() -> None:
    series = _normal(seed=5)
    high = coherent.omega_ratio(series, threshold=0.002)
    low = coherent.omega_ratio(series, threshold=-0.002)
    assert low > high


def test_lower_partial_moment_order_two_is_the_semi_variance() -> None:
    values = np.array([-0.02, -0.01, 0.0, 0.01, 0.03])
    expected = float(np.mean(np.maximum(-values, 0.0) ** 2))
    assert coherent.lower_partial_moment(
        pd.Series(values), threshold=0.0, order=2
    ) == pytest.approx(expected)


def test_lower_partial_moment_is_zero_above_the_threshold() -> None:
    series = pd.Series([0.01, 0.02, 0.03])
    assert coherent.lower_partial_moment(series, threshold=0.0, order=2) == 0.0


def test_partial_moment_threshold_must_be_stated_to_matter() -> None:
    """Zero and the mean are different questions, and give different answers."""
    series = _normal(mu=0.005, seed=6)
    at_zero = coherent.lower_partial_moment(series, threshold=0.0, order=2)
    at_mean = coherent.lower_partial_moment(
        series, threshold=float(series.mean()), order=2
    )
    assert at_mean > at_zero


# ── integration with the engine ──────────────────────────────────────────────

def test_the_engine_reports_all_of_them_with_methodology() -> None:
    report = risk.analyse(_normal(seed=1), periods_per_year=252.0).as_dict()
    for name in (
        "entropic_var_95", "entropic_drawdown_risk_95",
        "gini_dispersion", "semi_variance", "omega",
    ):
        assert name in report["metrics"], name
        assert report["metrics"][name]["value"] is not None
        assert "methodology" in report["metrics"][name]


def test_rank_units_suppress_the_threshold_measures() -> None:
    """Omega and semi-variance need a return scale; a rank has none."""
    rank = pd.Series(
        np.linspace(-1, 1, 300), index=pd.bdate_range("2020-01-01", periods=300)
    )
    report = risk.analyse(
        rank, periods_per_year=252.0, compound=False,
        series_unit=risk.SeriesUnit.RANK,
    ).as_dict()
    assert report["metrics"]["omega"]["value"] is None
    assert report["metrics"]["semi_variance"]["value"] is None
    # Gini is pure dispersion and stays applicable.
    assert report["metrics"]["gini_dispersion"]["value"] is not None


def test_entropic_drawdown_refuses_unordered_input() -> None:
    """Path-dependent, so it takes the same ordering guard as the others."""
    series = _normal(seed=3)
    shuffled = series.sample(frac=1.0, random_state=0)
    with pytest.raises(risk.UnorderedSeries):
        risk.entropic_drawdown_risk(shuffled)


def test_short_series_report_insufficient_rather_than_a_number() -> None:
    short = _normal(n=20, seed=1)
    assert risk.entropic_var(short).value is None
    assert risk.gini_dispersion(short).value is None
