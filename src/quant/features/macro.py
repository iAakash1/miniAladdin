"""
Macro features — the rates curve and the market regime, published with a lag.

## The publication lag is the whole point

A macro series describes a day and becomes available *after* it. The Treasury
par yield curve for 2024-03-14 is published that evening; a model forming a
view during 2024-03-14 has 2024-03-13's curve and no more. Getting this wrong
is a one-session leak that looks like nothing and is worth a surprising amount
of spurious accuracy, because rates move with the same news equities do.

So every function here takes an **already-lagged** frame, and the lag is
applied once, in `lagged_macro_frame`, rather than remembered at each call
site. `availability_lag_sessions=1` on each definition records the claim, and
`tests/quant/test_leakage.py` checks it by perturbing the final row.

## What is deliberately absent

No CPI, no unemployment, no GDP. Not because they lack value — they are among
the most informative macro series there are — but because each is released on
a schedule *and revised afterwards*, so using one honestly needs a vintage
database (ALFRED) that is not ingested here. Adding them from a current-value
API would date every revision to today and backdate it through the whole
history: the exact failure `docs/PANEL.md` §5.3 refuses for fundamentals.

The Treasury curve is used because it is not revised. Published once, correct
thereafter. That is why it is here and CPI is not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.quant.features.registry import (
    REGISTRY,
    Direction,
    FeatureDefinition,
    FeatureGroup,
)

#: Sessions between a macro observation and its availability. One session for
#: the Treasury curve: published after the close of the day it describes.
MACRO_LAG_SESSIONS = 1

_CURVE_COLUMNS = (
    "3_month", "6_month", "1_year", "2_year", "5_year", "10_year", "30_year",
)


def lagged_macro_frame(curve: pd.DataFrame, *, lag: int = MACRO_LAG_SESSIONS) -> pd.DataFrame:
    """Shift the curve forward so each date carries only prior-session data.

    Applied once, here. Every macro feature downstream consumes the output of
    this function, which is the same structural argument `src/panel/builder.py`
    makes for `_pit_window`: the future is *absent*, not merely unused.
    """
    if curve.empty:
        return curve
    frame = curve.sort_values("date", kind="mergesort").reset_index(drop=True)
    columns = [c for c in frame.columns if c != "date"]
    shifted = frame[columns].shift(lag)
    shifted.insert(0, "date", frame["date"])
    shifted.attrs["macro_lag_sessions"] = lag
    return shifted


def compute_macro_features(curve: pd.DataFrame) -> pd.DataFrame:
    """Rates level, slope, curvature and their changes, from a lagged curve.

    Level/slope/curvature is the standard three-factor decomposition of a yield
    curve (Litterman-Scheinkman): almost all of the curve's variation lives in
    those three, so carrying seven raw tenors would add collinearity rather
    than information.
    """
    if curve.empty:
        return pd.DataFrame(columns=["date"])

    frame = lagged_macro_frame(curve)
    available = [c for c in _CURVE_COLUMNS if c in frame.columns]
    if not available:
        raise ValueError(f"treasury curve has none of the expected tenors: {_CURVE_COLUMNS}")

    out = pd.DataFrame({"date": frame["date"]})
    # Source is in percent; convert once so downstream units are unambiguous.
    ten = pd.to_numeric(frame.get("10_year"), errors="coerce") / 100.0
    two = pd.to_numeric(frame.get("2_year"), errors="coerce") / 100.0
    three_month = pd.to_numeric(frame.get("3_month"), errors="coerce") / 100.0

    out["rates_level"] = ten
    out["rates_slope"] = ten - two
    out["rates_curvature"] = 2.0 * two - three_month - ten
    # 63 sessions ~ one quarter: long enough that the change is a policy or
    # growth move rather than a day's noise.
    out["rates_change_63"] = ten - ten.shift(63)
    out["rates_short"] = three_month
    return out


def compute_market_features(market_returns: pd.Series, dates: pd.Series) -> pd.DataFrame:
    """Market-wide regime descriptors from the universe's own aggregate return.

    Built from the equal-weighted cross-sectional mean rather than a purchased
    index, for one reason worth stating: the aggregate of the point-in-time
    universe *includes the names that later failed*, so its 2023 drawdown
    contains the regional banks. An index proxy reconstructed from today's
    membership would not, and would understate exactly the stress the regime
    feature exists to detect.
    """
    frame = pd.DataFrame({"date": dates.values, "market_return": market_returns.values})
    frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)
    returns = pd.to_numeric(frame["market_return"], errors="coerce")

    frame["market_mom_21"] = np.expm1(
        np.log1p(returns).rolling(21, min_periods=21).sum()
    )
    frame["market_mom_252"] = np.expm1(
        np.log1p(returns).rolling(252, min_periods=252).sum()
    )
    frame["market_vol_21"] = returns.rolling(21, min_periods=21).std(ddof=1) * np.sqrt(252)
    frame["market_vol_63"] = returns.rolling(63, min_periods=63).std(ddof=1) * np.sqrt(252)

    # Where today's volatility sits in its own trailing two-year distribution.
    # A percentile rather than a level, so "high volatility" means the same
    # thing in 2013 as in 2020 rather than tracking the era's absolute level.
    frame["market_vol_percentile"] = (
        frame["market_vol_21"]
        .rolling(504, min_periods=252)
        .rank(pct=True)
    )

    wealth = np.log1p(returns).fillna(0.0).cumsum()
    peak = wealth.rolling(252, min_periods=63).max()
    frame["market_drawdown"] = -np.expm1(wealth - peak)
    return frame.drop(columns=["market_return"])


def _register() -> None:
    definitions = [
        FeatureDefinition(
            name="rates_level",
            group=FeatureGroup.MACRO,
            description="10-year US Treasury par yield, prior session.",
            rationale="The discount rate every equity valuation is anchored to.",
            formula="10_year / 100, lagged one session",
            lookback_sessions=1,
            required_columns=("10_year",),
            direction=Direction.DESCRIPTIVE,
            availability_lag_sessions=MACRO_LAG_SESSIONS,
        ),
        FeatureDefinition(
            name="rates_slope",
            group=FeatureGroup.MACRO,
            description="10-year minus 2-year yield, prior session.",
            rationale="The curve's growth/recession signal; inversion is its best-known form.",
            formula="(10_year - 2_year) / 100, lagged one session",
            lookback_sessions=1,
            required_columns=("10_year", "2_year"),
            direction=Direction.DESCRIPTIVE,
            availability_lag_sessions=MACRO_LAG_SESSIONS,
        ),
        FeatureDefinition(
            name="rates_curvature",
            group=FeatureGroup.MACRO,
            description="2*2y - 3m - 10y, prior session.",
            rationale="The third Litterman-Scheinkman factor; policy-cycle position.",
            formula="(2*2_year - 3_month - 10_year) / 100, lagged one session",
            lookback_sessions=1,
            required_columns=("2_year", "3_month", "10_year"),
            direction=Direction.DESCRIPTIVE,
            availability_lag_sessions=MACRO_LAG_SESSIONS,
            citation="Litterman & Scheinkman (1991)",
        ),
        FeatureDefinition(
            name="rates_change_63",
            group=FeatureGroup.MACRO,
            description="Quarterly change in the 10-year yield.",
            rationale="Direction of the discount rate, not just its level.",
            formula="10_year(T) - 10_year(T-63), lagged one session",
            lookback_sessions=64,
            required_columns=("10_year",),
            direction=Direction.NEGATIVE,
            availability_lag_sessions=MACRO_LAG_SESSIONS,
        ),
        FeatureDefinition(
            name="rates_short",
            group=FeatureGroup.MACRO,
            description="3-month Treasury bill yield, prior session.",
            rationale="The policy rate proxy and the cash alternative equities compete with.",
            formula="3_month / 100, lagged one session",
            lookback_sessions=1,
            required_columns=("3_month",),
            direction=Direction.DESCRIPTIVE,
            availability_lag_sessions=MACRO_LAG_SESSIONS,
        ),
        FeatureDefinition(
            name="market_mom_21",
            group=FeatureGroup.MACRO,
            description="Equal-weighted universe return over 21 sessions.",
            rationale="Market state; the same move means different things in a rally and a fall.",
            formula="compounded cross-sectional mean return over 21 sessions",
            lookback_sessions=21,
            required_columns=("total_return",),
            direction=Direction.DESCRIPTIVE,
        ),
        FeatureDefinition(
            name="market_mom_252",
            group=FeatureGroup.MACRO,
            description="Equal-weighted universe return over 252 sessions.",
            rationale="Bull/bear state at the horizon regimes are usually defined over.",
            formula="compounded cross-sectional mean return over 252 sessions",
            lookback_sessions=252,
            required_columns=("total_return",),
            direction=Direction.DESCRIPTIVE,
        ),
        FeatureDefinition(
            name="market_vol_21",
            group=FeatureGroup.MACRO,
            description="Annualised volatility of the equal-weighted universe return, 21 sessions.",
            rationale="The volatility regime, measured from the survivorship-free cross-section.",
            formula="std(market return, 21) * sqrt(252)",
            lookback_sessions=21,
            required_columns=("total_return",),
            direction=Direction.DESCRIPTIVE,
        ),
        FeatureDefinition(
            name="market_vol_63",
            group=FeatureGroup.MACRO,
            description="Annualised market volatility over 63 sessions.",
            rationale="Slower volatility state, for regime persistence.",
            formula="std(market return, 63) * sqrt(252)",
            lookback_sessions=63,
            required_columns=("total_return",),
            direction=Direction.DESCRIPTIVE,
        ),
        FeatureDefinition(
            name="market_vol_percentile",
            group=FeatureGroup.MACRO,
            description="Rank of current market volatility in its trailing 2-year distribution.",
            rationale=(
                "A percentile rather than a level, so 'high volatility' means the "
                "same thing across eras with different absolute volatility."
            ),
            formula="rolling(504).rank(pct=True) of market_vol_21",
            lookback_sessions=504,
            required_columns=("total_return",),
            direction=Direction.DESCRIPTIVE,
        ),
        FeatureDefinition(
            name="market_drawdown",
            group=FeatureGroup.MACRO,
            description="Market drawdown from its trailing-year peak, positive.",
            rationale="Stress state; distinguishes a fall from a low-return period.",
            formula="1 - index / max(index over 252)",
            lookback_sessions=252,
            required_columns=("total_return",),
            direction=Direction.DESCRIPTIVE,
        ),
    ]
    for definition in definitions:
        # No per-symbol computer: these are join-stage features, produced once
        # per date and broadcast across the cross-section.
        REGISTRY.register(definition)


_register()
