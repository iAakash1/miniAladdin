"""
Drawdown-path and robust-dispersion measures, pinned to hand-computed values.

`max_drawdown` reports depth alone, so a single catastrophic day and a two-year
grind to the same trough score identically. This family measures the path.

The robust measures matter here for a concrete reason: EXP-007's selected
configuration has excess kurtosis of 43.28, and a standard deviation on that
series is dominated by a handful of periods. A large gap between MAD and std is
the finding, not a rounding difference.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.risk import engine

N = 120


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))


# ── drawdown path ────────────────────────────────────────────────────────────

def test_ulcer_index_is_the_rms_of_the_drawdown_path():
    series = _series([0.02] * 10 + [-0.03] * 10 + [0.01] * (N - 20))
    path = engine.drawdown_series(series).to_numpy()
    assert engine.ulcer_index(series).value == pytest.approx(
        float(np.sqrt(np.mean(np.square(path))))
    )


def test_ulcer_separates_two_paths_with_the_same_maximum_drawdown():
    """The whole reason this measure exists.

    One brief plunge and a long grind to the same trough have identical maximum
    drawdowns. The one that stays underwater must score worse.
    """
    brief = _series([0.0] * 5 + [-0.20] + [0.25] + [0.0] * (N - 7))
    grind = _series([0.0] * 5 + [-0.20] + [0.0] * (N - 7) + [0.25])

    assert engine.max_drawdown(brief).value == pytest.approx(
        engine.max_drawdown(grind).value, rel=1e-9
    )
    assert engine.ulcer_index(grind).value > engine.ulcer_index(brief).value


def test_average_drawdown_includes_periods_at_the_high_water_mark():
    """Averaging only underwater periods answers a different question."""
    series = _series([0.01] * (N - 1) + [-0.5])
    path = engine.drawdown_series(series)
    assert engine.average_drawdown(series).value == pytest.approx(float(path.mean()))
    assert (path == 0).sum() > 0, "fixture must contain at-peak periods"


def test_drawdown_at_risk_is_the_empirical_quantile_as_a_magnitude():
    series = _series(np.concatenate([np.full(60, 0.01), np.full(60, -0.01)]))
    path = engine.drawdown_series(series).to_numpy()
    expected = -float(np.quantile(path, 0.05))
    assert engine.drawdown_at_risk(series, confidence=0.95).value == pytest.approx(expected)


def test_cdar_is_at_least_dar():
    """The mean of a tail cannot be shallower than the tail's boundary."""
    series = _series(np.concatenate([np.full(60, 0.01), np.full(60, -0.01)]))
    dar = engine.drawdown_at_risk(series, confidence=0.95).value
    cdar = engine.conditional_drawdown_at_risk(series, confidence=0.95).value
    assert cdar >= dar - 1e-12


def test_ulcer_performance_index_has_no_denominator_without_a_drawdown():
    result = engine.ulcer_performance_index(_series([0.001] * N))
    assert result.value is None
    assert "no drawdown" in result.caveat


# ── robust dispersion ────────────────────────────────────────────────────────

def test_mean_absolute_deviation_matches_the_hand_computed_value():
    series = _series([0.02 if i % 2 == 0 else -0.01 for i in range(N)])
    values = series.to_numpy()
    assert engine.mean_absolute_deviation(series).value == pytest.approx(
        float(np.mean(np.abs(values - values.mean())))
    )


def test_mad_is_far_less_sensitive_to_one_outlier_than_std():
    """The property that makes it worth reporting on fat-tailed data."""
    clean = _series([0.001] * N)
    spiked = _series([0.001] * (N - 1) + [0.5])

    mad_ratio = (engine.mean_absolute_deviation(spiked).value
                 / max(engine.mean_absolute_deviation(clean).value, 1e-12))
    std_ratio = (spiked.std(ddof=1) / max(clean.std(ddof=1), 1e-12))
    assert mad_ratio < std_ratio, "MAD must move less than std for one outlier"


def test_worst_realization_is_an_observation_not_an_estimate():
    series = _series([0.01] * (N - 1) + [-0.37])
    result = engine.worst_realization(series)
    assert result.value == pytest.approx(0.37)
    assert result.method == "sample_minimum"


def test_worst_realization_is_at_least_historical_var():
    """VaR is a quantile; the worst case cannot be inside it."""
    rng = np.random.default_rng(11)
    series = _series(rng.normal(0.0, 0.02, 500))
    assert (engine.worst_realization(series).value
            >= engine.var_historical(series, confidence=0.95).value)


# ── shared edge cases ────────────────────────────────────────────────────────

@pytest.mark.parametrize("fn", [
    engine.ulcer_index, engine.average_drawdown, engine.drawdown_at_risk,
    engine.conditional_drawdown_at_risk, engine.mean_absolute_deviation,
])
def test_a_short_sample_refuses_rather_than_estimating(fn):
    result = fn(_series([0.01, -0.01, 0.02]))
    assert result.value is None
    assert "INSUFFICIENT DATA" in result.caveat


@pytest.mark.parametrize("fn", [engine.ulcer_index, engine.mean_absolute_deviation])
def test_nan_and_inf_are_dropped(fn):
    values = [0.02 if i % 2 == 0 else -0.01 for i in range(N)]
    dirty = list(values) + [np.nan, np.inf, -np.inf]
    assert fn(_series(dirty)).value == pytest.approx(fn(_series(values)).value)


def test_every_new_measure_is_non_negative_as_a_magnitude():
    """These are reported as magnitudes; a negative would be a sign error."""
    rng = np.random.default_rng(5)
    series = _series(rng.normal(0.0003, 0.012, 300))
    for fn in (engine.ulcer_index, engine.drawdown_at_risk,
               engine.conditional_drawdown_at_risk, engine.mean_absolute_deviation,
               engine.worst_realization):
        assert fn(series).value >= 0, fn.__name__
