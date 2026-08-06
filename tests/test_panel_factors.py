"""
Oracle tests — the vectorized factor path must equal the scalar engine.

`src/scoring/engine.py` defines what a factor *means*. `src/panel/factors.py`
is a faster way to compute the same thing. A second implementation of shared
semantics is the most dangerous construct in a quantitative codebase: if the
two drift, the panel and production disagree and nothing announces it.

`test_vectorized_matches_scalar_engine_exactly` is what makes keeping the
second implementation defensible. It runs both paths over the same history
and compares every factor at every date. It is not a smoke test with a loose
tolerance — it asserts equality to floating-point round-off.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.panel.factors import (
    MIN_LOOKBACK,
    _compute_unchecked,
    PRICE_FACTOR_COLUMNS,
    compute_price_factors,
)
from src.scoring.engine import (
    MIN_BARS,
    detect_regimes,
    momentum_factors,
    reversal_factor,
)

TOLERANCE = 1e-12


def _prices(days: int, seed: int, volume: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2020-01-02", periods=days)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.013, days)))
    data = {
        "Open": closes * 0.997,
        "High": closes * 1.008,
        "Low": closes * 0.992,
        "Close": closes,
    }
    if volume:
        data["Volume"] = rng.integers(1_000_000, 9_000_000, days).astype(float)
    return pd.DataFrame(data, index=index)


def _scalar_factors(window: pd.DataFrame, benchmark: pd.DataFrame | None) -> dict:
    """What the engine produces for one window — the reference answer."""
    rows = momentum_factors(window, benchmark) + reversal_factor(window)
    return {row.name: row.score for row in rows}


def _compare(frame, benchmark, lookback, dates=None, unchecked=False):
    """Yield (date, factor, vectorized, scalar) for every mismatch."""
    compute = _compute_unchecked if unchecked else compute_price_factors
    vectorized = compute(frame, benchmark, lookback)
    # From row 0, not from MIN_BARS: the interesting rows are where each
    # factor's guard switches on (40 daily returns for sigma, 120 bars for
    # high52, 22/64/253 for the momentum horizons), and most of those sit
    # below MIN_BARS. Starting later left a mutant alive.
    positions = dates if dates is not None else range(len(frame))

    mismatches = []
    for position in positions:
        observed_on = frame.index[position]
        window = frame.iloc[: position + 1].tail(lookback)
        # Slice the benchmark by DATE, not by the stock's row position — the
        # two calendars differ whenever their histories start on different
        # days, and the builder truncates the benchmark at the observation
        # date via `_pit_window`.
        benchmark_window = (
            None if benchmark is None
            else benchmark[benchmark.index <= observed_on].tail(lookback)
        )
        scalar = _scalar_factors(window, benchmark_window)

        for name in PRICE_FACTOR_COLUMNS:
            expected = scalar.get(name)
            actual = vectorized[name].iloc[position]
            both_absent = expected is None and pd.isna(actual)
            if both_absent:
                continue
            if expected is None or pd.isna(actual):
                mismatches.append((frame.index[position].date(), name, actual, expected))
            elif abs(float(actual) - float(expected)) > TOLERANCE:
                mismatches.append((frame.index[position].date(), name, actual, expected))
    return mismatches


# ── THE ORACLE TEST ──────────────────────────────────────────────────────────

def test_vectorized_matches_scalar_engine_exactly():
    """Every factor, every date, to floating-point round-off."""
    frame = _prices(420, seed=1)
    benchmark = _prices(420, seed=2)

    mismatches = _compare(frame, benchmark, lookback=1260)
    assert not mismatches, (
        f"{len(mismatches)} vectorized/scalar mismatches; first 10:\n"
        + "\n".join(
            f"  {day} {name}: vectorized={actual!r} scalar={expected!r}"
            for day, name, actual, expected in mismatches[:10]
        )
    )


@pytest.mark.parametrize("lookback", [252, 300, 400])
def test_truncating_windows_is_refused_not_approximated(lookback):
    """The fast path must decline rather than diverge.

    With lookback > series length the window never truncates and every
    `lookback - k` warm-up offset is dead code — mutation testing showed
    three such mutants surviving the oracle test above. Where the window
    genuinely slides, the engine's RSI warm-up artifact cannot be
    reproduced, so the guard fires.
    """
    frame = _prices(600, seed=21)
    with pytest.raises(ValueError, match="exceeds lookback"):
        compute_price_factors(frame, None, lookback=lookback)


@pytest.mark.parametrize("lookback", [252, 300, 400])
def test_divergence_outside_the_guard_is_material(lookback):
    """Pins *why* the guard exists, so nobody deletes it as over-caution.

    Bypassing the guard produces materially wrong factors — not round-off.
    If this test ever stops finding divergence, the guard has become
    unnecessary and should be removed deliberately, not left as folklore.
    """
    frame = _prices(600, seed=21)
    benchmark = _prices(600, seed=22)

    mismatches = _compare(frame, benchmark, lookback=lookback, unchecked=True)
    assert mismatches, "expected divergence; if none, the guard may be removable"

    worst = max(abs(float(a) - float(e)) for _, _, a, e in mismatches)
    assert worst > 1e-3, (
        f"divergence only {worst:.2e} — too small to justify the guard; re-examine"
    )


def test_matches_without_a_benchmark():
    """SPY missing must null relative strength in both paths identically."""
    frame = _prices(320, seed=5)
    assert not _compare(frame, None, lookback=1260)


def test_matches_when_benchmark_has_more_history():
    """A symbol listed after SPY: benchmark bar counts differ from the stock's.

    The engine's `len(spy) >= 63` guard counts benchmark bars, so deriving it
    from the stock's row positions gates `rel21_vs_spy` off on dates where
    the engine computes it.
    """
    benchmark = _prices(500, seed=31)
    frame = _prices(500, seed=30).iloc[200:]          # listed 200 bars later
    assert not _compare(frame, benchmark, lookback=1260)


def test_matches_when_benchmark_has_less_history():
    benchmark = _prices(500, seed=33).iloc[150:]
    frame = _prices(500, seed=32)
    assert not _compare(frame, benchmark, lookback=1260)


def test_matches_without_volume():
    """No volume column must skip vol_confirm in both paths identically."""
    frame = _prices(320, seed=6, volume=False)
    benchmark = _prices(320, seed=7)
    assert not _compare(frame, benchmark, lookback=1260)


def test_matches_with_zero_volume():
    """The engine's `volume.sum() > 0` guard, reproduced as a trailing sum."""
    frame = _prices(320, seed=8)
    frame["Volume"] = 0.0
    benchmark = _prices(320, seed=9)
    assert not _compare(frame, benchmark, lookback=1260)


def test_matches_on_a_flat_series():
    """Zero variance means MAD is zero — both paths must decline to guess."""
    index = pd.bdate_range("2020-01-02", periods=300)
    frame = pd.DataFrame(
        {"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0, "Volume": 1e6},
        index=index,
    )
    benchmark = _prices(300, seed=11)
    assert not _compare(frame, benchmark, lookback=1260)


def test_matches_on_a_near_degenerate_series():
    """Dispersion just above zero exercises the engine's 1e-9 sigma floor.

    A perfectly flat series has sigma exactly 0 and both paths decline; the
    floor only earns its keep in the narrow band just above it.
    """
    index = pd.bdate_range("2020-01-02", periods=300)
    rng = np.random.default_rng(77)
    closes = 50.0 * (1 + rng.normal(0, 1e-10, 300).cumsum())
    frame = pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes,
         "Volume": 1e6},
        index=index,
    )
    assert not _compare(frame, None, lookback=1260)


def test_matches_across_the_minimum_history_boundary():
    """The interesting rows are where guards switch on, not the steady state."""
    frame = _prices(300, seed=12)
    benchmark = _prices(300, seed=13)
    boundaries = list(range(MIN_BARS - 2, 135)) + list(range(245, 300))
    assert not _compare(frame, benchmark, lookback=1260, dates=boundaries)


def _assert_regime_matches(frame):
    vectorized = compute_price_factors(frame, None, lookback=1260)
    for position in range(len(frame)):
        window = frame.iloc[: position + 1]
        expected = "high_volatility" in detect_regimes(window, None, window.index[-1].date())
        actual = bool(vectorized["high_volatility"].iloc[position])
        assert actual == expected, f"regime mismatch at {frame.index[position].date()}"


@pytest.mark.parametrize("seed", [14, 15, 16, 17])
def test_high_volatility_regime_matches_engine(seed):
    """Every row and several seeds: the 120-return guard sits below MIN_BARS,
    and a single seed left a boundary mutant alive."""
    _assert_regime_matches(_prices(400, seed=seed))


def test_high_volatility_regime_matches_engine_with_tied_volatility():
    """Forces exact ties against the 80th percentile.

    Returns cycle through a few fixed magnitudes, so rolling volatility
    repeats values and the quantile lands exactly on an observation. That is
    the only way to distinguish the engine's `>=` from a `>`; with continuous
    random data the comparison is never exactly equal and the mutant lives.
    """
    pattern = np.array([0.01, -0.01, 0.02, -0.02, 0.0, 0.01, -0.01])
    returns = np.tile(pattern, 60)
    closes = 100 * np.exp(np.cumsum(returns))
    index = pd.bdate_range("2020-01-02", periods=len(closes))
    frame = pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes,
         "Volume": 1e6},
        index=index,
    )
    _assert_regime_matches(frame)


# ── guards ───────────────────────────────────────────────────────────────────

def test_lookback_below_the_floor_is_rejected():
    """Below 252 bars, windowed and global rolling statistics diverge."""
    frame = _prices(300, seed=15)
    with pytest.raises(ValueError, match="below 252"):
        compute_price_factors(frame, None, lookback=MIN_LOOKBACK - 1)


def test_bars_column_tracks_visible_history():
    frame = _prices(300, seed=16)
    result = compute_price_factors(frame, None, lookback=1260)
    assert result["bars"].iloc[0] == 1
    assert result["bars"].iloc[-1] == 300


def test_bars_column_is_capped_by_lookback():
    """Only observable unchecked: the guard forbids truncation in the fast path."""
    frame = _prices(400, seed=17)
    result = _compute_unchecked(frame, None, lookback=300)
    assert result["bars"].max() == 300


def test_short_history_yields_all_null_factors():
    frame = _prices(30, seed=18)
    result = compute_price_factors(frame, None, lookback=1260)
    for name in PRICE_FACTOR_COLUMNS:
        assert result[name].isna().all()


def test_factor_columns_are_the_price_sleeve():
    """These seven are exactly what OHLCV can support point-in-time."""
    assert PRICE_FACTOR_COLUMNS == (
        "r12_1", "r63", "r21", "vol_confirm",
        "high52_prox", "rel21_vs_spy", "reversal",
    )
