"""
Vectorized price factors — one pass per symbol instead of one pass per cell.

## Why this module exists

`PanelBuilder` originally called the engine's scalar factor functions once
per (symbol, date). Each call recomputed `pct_change`, rolling medians and
MAD σ over the whole window from scratch, so a panel of N observations did
O(N) work N times. Profiling put it at ~20,000 Python-level calls per cell
and 430 cells/s — roughly 50 minutes for a 500-name, 10-year daily panel.

This module computes every factor as a full time series in one pass per
symbol, then reads values off per date.

## The correctness contract

**`src/scoring/engine.py` is the oracle. This module must agree with it
exactly — not approximately.**

That is not a claim, it is a test:
`tests/test_panel_factors.py::test_vectorized_matches_scalar_engine_exactly`
runs both paths over the same history and asserts equality at every date for
every factor. A second implementation of shared semantics is the most
dangerous thing in a quantitative codebase — a fast panel that silently
disagrees with production is worse than a slow one that does not. The oracle
test is what makes the second implementation safe to keep.

Where the engine is handed a window, this module reproduces exactly what the
engine would see *within that window*, which is subtler than it sounds:
a series derived inside a window (`pct_change`, a rolling mean, RSI) is NaN
for its own warm-up period, so the set of observations the engine's
normalizers actually see is a trailing slice shorter than the window. Each
factor below documents the slice it corresponds to.

## Scope

The seven price-derived factors, plus the `high_volatility` regime. The
fundamental, quality and news sleeves need point-in-time inputs that do not
exist yet (docs/PANEL.md §5.3); when they arrive they are added here, not
bolted onto the caller.
"""

from __future__ import annotations

import math
from datetime import date as Date
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd

from src.panel.windowed import (
    rolling_median_mad,
    rolling_quantile,
    rolling_robust_z,
)
from src.scoring.engine import (
    HIGH52_CENTER,
    HIGH52_SIGMA,
    HIGH_VOL_PERCENTILE,
    MAD_CONSISTENCY,
    SQUASH_SCALE,
    WINSOR_Z,
)
from src.scoring.fomc_calendar import business_days_to_next_fomc

#: Longest fixed lookback any single factor reads (52-week high). A lookback
#: shorter than this would make windowed and global rolling statistics
#: disagree, so it is a hard floor rather than a suggestion.
MIN_LOOKBACK = 252

PRICE_FACTOR_COLUMNS: tuple[str, ...] = (
    "r12_1", "r63", "r21", "vol_confirm", "high52_prox", "rel21_vs_spy", "reversal",
)


def _squash(values: np.ndarray) -> np.ndarray:
    """`engine.squash`, applied elementwise. NaN propagates as "no estimate"."""
    return np.tanh(values / SQUASH_SCALE)


def _tstat_z(
    closes: np.ndarray,
    sigma: np.ndarray,
    length: np.ndarray,
    horizon: int,
    skip: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """`engine.return_tstat_z` evaluated at every row.

    Mirrors the engine exactly, including its guards: the window must hold
    `horizon + skip + 1` bars, and a non-positive start price yields no value.
    """
    count = len(closes)
    value = np.full(count, np.nan)
    z = np.full(count, np.nan)

    end_index = np.arange(count) - skip
    start_index = end_index - horizon
    usable = (start_index >= 0) & (length >= horizon + skip + 1)
    if not usable.any():
        return value, z

    rows = np.flatnonzero(usable)
    start = closes[start_index[rows]]
    end = closes[end_index[rows]]
    positive = start > 0
    rows = rows[positive]
    if not len(rows):
        return value, z

    returns = end[positive] / start[positive] - 1.0
    value[rows] = returns

    scale = sigma[rows] * math.sqrt(horizon)
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = returns / scale
    raw[~np.isfinite(raw)] = np.nan
    z[rows] = np.clip(raw, -WINSOR_Z, WINSOR_Z)
    return value, z


@lru_cache(maxsize=4096)
def _fomc_window(day: Date, threshold: int) -> bool:
    """Memoized: observation dates repeat across every symbol in a universe.

    Uncached, this was ~13% of build time purely from recomputing the same
    calendar walk once per (symbol, date) instead of once per date.
    """
    days = business_days_to_next_fomc(day)
    return days is not None and days <= threshold


def is_exact_for(frame: pd.DataFrame, lookback: int) -> bool:
    """Whether the vectorized path provably equals the engine for this input.

    It does when windows never truncate — that is, when the history is no
    longer than the lookback. Two independent reasons it does not otherwise,
    both measured rather than assumed:

    **1. No warm-up compensation.** This module computes rolling statistics
    over the full history using the lookback as the window. Inside the
    domain that is identical to what the engine sees. Outside it, the engine
    normalizes over a *shorter* trailing slice than the window, because a
    series derived inside a window (`pct_change`, a rolling mean, RSI) is
    NaN through its own warm-up. Measured at lookback=252 over 600 bars:
    1,692 divergent values across six factors, up to 1.7e-1 on
    `vol_confirm`.

    **2. Compensating for #1 would still not be enough.** `_rsi_series`
    starts from `closes.diff()`, NaN at the first bar of whatever series it
    is handed, and `.where(delta > 0, 0.0)` turns that NaN into a fabricated
    `0.0`. Inside a truncated window the oldest RSI observation is therefore
    a 14-bar mean containing one invented zero, and differs from the same
    date's global RSI. `robust_z` takes its median and MAD over a sample
    holding that contaminated point. It is the oldest element of a sliding
    window — a per-row substitution no rolling reduction expresses. With
    warm-up compensation in place, divergence fell to 40 values, all in
    `reversal`, at ~1e-3: smaller, and still not equal.

    Because exactness is unreachable outside the domain either way, the
    compensation arithmetic for #1 was deleted rather than kept. Inside the
    domain it provably cannot change a result — the elements a narrower
    window would drop are exactly the NaN warm-up entries `min_count`
    already ignores, and mutation testing confirmed three such expressions
    were inert. Outside the domain it would only shrink an error that must
    not exist at all.

    So the fast path declines to run and `PanelBuilder` falls back to the
    scalar engine, which is the oracle. In the shipping configuration
    (lookback 1260, vendor history ~501 bars) windows never truncate, so the
    fast path always applies. See `tests/test_panel_factors.py`.
    """
    return len(frame) <= lookback


def compute_price_factors(
    frame: pd.DataFrame,
    benchmark: Optional[pd.DataFrame],
    lookback: int,
) -> pd.DataFrame:
    """Every price factor for every date in `frame`, in one pass.

    Returns a frame indexed like `frame`, holding the seven factor scores,
    the number of bars visible at each date, and the `high_volatility`
    regime flag. Rows whose window is too short carry NaN — absent, not zero.

    Raises `ValueError` when the result would not exactly equal the engine;
    see `is_exact_for`. Failing loudly is the point — a fast path that
    silently disagrees with production is worse than no fast path.
    """
    # Argument validity before input-domain validity: a bad lookback is a
    # caller bug, a long history is merely out of the fast path's domain.
    _require_valid_lookback(lookback)
    if not is_exact_for(frame, lookback):
        raise ValueError(
            f"history of {len(frame)} bars exceeds lookback {lookback}; the "
            "vectorized path would diverge from the engine on `reversal` "
            "(see is_exact_for). Use the scalar path for this input."
        )
    return _compute_unchecked(frame, benchmark, lookback)


def _require_valid_lookback(lookback: int) -> None:
    if lookback < MIN_LOOKBACK:
        raise ValueError(
            f"lookback {lookback} is below {MIN_LOOKBACK}; windowed and global "
            "rolling statistics would diverge and the panel would stop matching the engine"
        )


def _compute_unchecked(
    frame: pd.DataFrame,
    benchmark: Optional[pd.DataFrame],
    lookback: int,
) -> pd.DataFrame:
    """`compute_price_factors` without the exactness guard.

    Exists so a test can measure and pin the divergence the guard prevents.
    Not for production use: outside the guard's domain this is *close to*
    the engine, and "close to" is not a property this repository accepts.
    """
    _require_valid_lookback(lookback)

    closes = frame["Close"].astype("float64")
    count = len(frame)
    index = np.arange(count)

    # Bars visible at each date, capped by the lookback. Every "does the
    # window hold enough history" guard below is expressed against this.
    length = np.minimum(index + 1, lookback).astype("float64")

    # ── σ of daily returns ───────────────────────────────────────────────
    # No warm-up compensation anywhere in this function: `is_exact_for`
    # guarantees the window never truncates, and the only elements a
    # narrower window would exclude are the NaN warm-up entries that
    # `min_count` already ignores. Subtracting warm-up lengths here would be
    # arithmetic that provably cannot change the result — mutation testing
    # confirmed three such expressions were inert, so they were removed
    # rather than left looking load-bearing.
    daily = closes.pct_change().to_numpy()
    _, mad_daily = rolling_median_mad(daily, lookback, min_count=40)
    sigma = MAD_CONSISTENCY * mad_daily
    sigma[~(sigma > 1e-9)] = np.nan

    close_values = closes.to_numpy()
    _, z_r12_1 = _tstat_z(close_values, sigma, length, horizon=231, skip=21)
    r21_value, z_r63 = _tstat_z(close_values, sigma, length, horizon=63)
    r21_value, z_r21 = _tstat_z(close_values, sigma, length, horizon=21)

    factors: dict[str, np.ndarray] = {
        "r12_1": _squash(z_r12_1),
        "r63": _squash(z_r63),
        "r21": _squash(z_r21),
    }

    # ── vol_confirm ──────────────────────────────────────────────────────
    # The engine skips this factor entirely when the window carries no
    # volume, so the guard is a trailing sum, not a global one.
    factors["vol_confirm"] = np.full(count, np.nan)
    if "Volume" in frame.columns:
        volume = frame["Volume"].astype("float64").fillna(0.0)
        has_volume = (
            volume.rolling(lookback, min_periods=1).sum().to_numpy() > 0
        )
        if has_volume.any():
            ratio = (
                volume.rolling(21).mean() / volume.rolling(63).mean()
            ).to_numpy()
            z_ratio = rolling_robust_z(
                ratio, lookback, min_count=20,
                consistency=MAD_CONSISTENCY, winsor=WINSOR_Z,
            )
            direction = np.where(np.isnan(r21_value) | (r21_value < 0), -1.0, 1.0)
            confirm = _squash(z_ratio * direction)
            factors["vol_confirm"] = np.where(has_volume, confirm, np.nan)

    # ── high52_prox ──────────────────────────────────────────────────────
    # Valid from 120 bars (the engine's min_periods); identical to the
    # window-local rolling max because lookback >= 252 is enforced above.
    high = closes.rolling(252, min_periods=120).max().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        proximity = close_values / high
    proximity[~np.isfinite(proximity)] = np.nan
    z_high = np.clip(
        (proximity - HIGH52_CENTER) / HIGH52_SIGMA, -WINSOR_Z, WINSOR_Z
    )
    factors["high52_prox"] = _squash(z_high)

    # ── rel21_vs_spy ─────────────────────────────────────────────────────
    factors["rel21_vs_spy"] = _relative_strength(closes, benchmark, lookback, length)

    # ── reversal ─────────────────────────────────────────────────────────
    _, z_reversal_return = _tstat_z(close_values, sigma, length, horizon=5)
    rsi = _rsi(closes).to_numpy()
    z_rsi = rolling_robust_z(
        rsi, lookback, min_count=20,
        consistency=MAD_CONSISTENCY, winsor=WINSOR_Z,
    )
    factors["reversal"] = _squash(_merge_reversal(z_reversal_return, z_rsi))

    result = pd.DataFrame(factors, index=frame.index)
    result["bars"] = length.astype("int32")
    result["high_volatility"] = _high_volatility(daily, lookback)
    return result


def _merge_reversal(z_return: np.ndarray, z_rsi: np.ndarray) -> np.ndarray:
    """`engine.reversal_factor`: mean of the available contrarian readings.

    The engine averages over whichever components exist, so one missing
    component halves the sample rather than voiding the factor.
    """
    parts = np.stack([-z_return, -z_rsi])
    available = np.isfinite(parts).sum(axis=0)
    with np.errstate(invalid="ignore"):
        merged = np.nansum(np.where(np.isfinite(parts), parts, 0.0), axis=0) / available
    merged[available == 0] = np.nan
    return np.clip(merged, -WINSOR_Z, WINSOR_Z)


def _rsi(closes: pd.Series, window: int = 14) -> pd.Series:
    """`engine._rsi_series`, verbatim.

    Duplicated rather than imported because the engine's copy is private and
    the oracle test pins them together; if the engine's changes, that test
    fails rather than the panel drifting.
    """
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _relative_strength(
    closes: pd.Series,
    benchmark: Optional[pd.DataFrame],
    lookback: int,
    length: np.ndarray,
) -> np.ndarray:
    """21-day return relative to the benchmark, as a t-statistic."""
    count = len(closes)
    out = np.full(count, np.nan)
    if benchmark is None or len(benchmark) < 63:
        return out

    stock_daily = closes.pct_change()
    benchmark_daily = benchmark["Close"].astype("float64").pct_change().reindex(
        stock_daily.index
    )
    relative = (stock_daily - benchmark_daily).to_numpy()

    _, mad = rolling_median_mad(relative, lookback, min_count=40)
    sigma = MAD_CONSISTENCY * mad

    rolled = pd.Series(relative).rolling(21, min_periods=21).sum().to_numpy()
    observations = (
        pd.Series(relative).rolling(lookback, min_periods=1).count().to_numpy()
    )

    # The engine also requires the benchmark's own window to hold 63 bars.
    # Counted against the benchmark's calendar, not the stock's: a symbol
    # listed after SPY has fewer bars than its benchmark on the same date,
    # and deriving this from the stock's positions would gate the factor off
    # on dates where the engine computes it.
    benchmark_bars = np.searchsorted(
        benchmark.index.to_numpy(), closes.index.to_numpy(), side="right"
    )
    benchmark_length = np.minimum(benchmark_bars, lookback)
    usable = (observations >= 40) & (sigma > 1e-9) & (benchmark_length >= 63)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = rolled / (sigma * math.sqrt(21))
    z[~np.isfinite(z)] = np.nan
    out = np.where(usable, np.clip(z, -WINSOR_Z, WINSOR_Z), np.nan)
    return _squash(out)


def _high_volatility(daily: np.ndarray, lookback: int) -> np.ndarray:
    """`detect_regimes`' volatility branch, evaluated at every row.

    Current 21-day volatility at or above its own 80th percentile, measured
    over the window. Needs 120 daily returns and 60 volatility observations,
    both counted the way the engine counts them: after dropping NaN.
    """
    series = pd.Series(daily)
    volatility = series.dropna().rolling(21).std()
    volatility = volatility.reindex(series.index)
    values = volatility.to_numpy()

    # min_count=60 mirrors the engine's `len(rolling_vol) >= 60`, which is
    # dead there and here: the `daily_count >= 120` gate below already
    # guarantees at least 100 volatility observations, so 60 can never bind.
    # Kept because this module's contract is to mirror the engine one-for-one
    # — if that 120 ever loosens, this guard becomes live and stays correct.
    # Mutation testing cannot kill it; that is expected, not a coverage gap.
    threshold = rolling_quantile(
        values, lookback, HIGH_VOL_PERCENTILE, min_count=60
    )
    daily_count = series.rolling(lookback, min_periods=1).count().to_numpy()
    with np.errstate(invalid="ignore"):
        flagged = (daily_count >= 120) & (values >= threshold)
    return np.nan_to_num(flagged, nan=0.0).astype(bool)


def regimes_for(observed_on: Date, high_volatility: bool, fomc_window_days: int) -> str:
    """The regime label string stored on a panel row.

    Order matches `detect_regimes` so the stored string is comparable with
    anything the live engine produces. `earnings_window` never appears: the
    panel has no point-in-time earnings calendar (docs/PANEL.md §5.3).
    """
    labels: list[str] = []
    if high_volatility:
        labels.append("high_volatility")
    if _fomc_window(observed_on, fomc_window_days):
        labels.append("fomc_window")
    return ",".join(labels)
