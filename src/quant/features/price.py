"""
Price, volume, structure and volatility features.

Every function here takes one symbol's history — sorted ascending by date,
carrying the point-in-time `total_return` produced by
`src/quant/pit/adjust.py` — and returns a series aligned to its index.

## The structural rule

Backward-looking windows only. `rolling(...)`, `shift(n)` for positive `n`,
`cumprod`, `expanding`. Never `shift(-n)`; never `center=True`. That is not
style: `shift(-1)` is a label, and a label in the feature matrix is the
canonical way a model reaches 99% accuracy and zero value.

`min_periods` is always set to the full window. A 252-day momentum computed
from 30 observations is a different statistic wearing the same column name,
and it appears exactly at the start of every symbol's history — which is where
walk-forward training begins.

## Why this list is short

The brief warned against "500 correlated technical indicators to inflate
feature count", and this repository has already measured the cost of that
instinct: `src/research/redundancy.py` computes the participation ratio of the
factor correlation matrix and reports that the engine's seven price factors
carry far fewer than seven independent bets. Adding a fifth momentum horizon
does not add a fifth signal, it adds a fifth vote for the same one.

So each feature below is here because it measures something the others do not,
and `docs/modeling-methodology.md` records the redundancy analysis that has to
pass before any feature is added.
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

#: Sessions per year, for annualising.
TRADING_DAYS = 252

#: Guards a ratio whose denominator can legitimately reach zero (a name with a
#: flat window has zero realised volatility). Returning NULL there is right;
#: returning a huge number is not, and returning 0.0 is worse still.
_EPSILON = 1e-12


def _returns(frame: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(frame["total_return"], errors="coerce").astype(float)


def _cumulative_return(returns: pd.Series, window: int) -> pd.Series:
    """Compounded return over a trailing window, NULL until it is full."""
    log_returns = np.log1p(returns)
    rolled = log_returns.rolling(window, min_periods=window).sum()
    return np.expm1(rolled)


# ── momentum ─────────────────────────────────────────────────────────────────


def momentum_21(frame: pd.DataFrame) -> pd.Series:
    return _cumulative_return(_returns(frame), 21)


def momentum_63(frame: pd.DataFrame) -> pd.Series:
    return _cumulative_return(_returns(frame), 63)


def momentum_252_21(frame: pd.DataFrame) -> pd.Series:
    """12-1 momentum: the trailing year excluding the most recent month.

    The month is skipped because short-horizon reversal and momentum point in
    opposite directions over it, so including it mixes two effects into one
    column and mutes both. Jegadeesh-Titman (1993); the skip is the standard
    construction in the cross-sectional momentum literature.
    """
    returns = _returns(frame)
    year = _cumulative_return(returns, TRADING_DAYS)
    month = _cumulative_return(returns, 21)
    return (1.0 + year) / (1.0 + month) - 1.0


def reversal_5(frame: pd.DataFrame) -> pd.Series:
    """Short-horizon reversal — the negated trailing week.

    Negated so the hypothesised direction is positive like every other feature:
    a name that fell last week is expected to bounce. Signing it here rather
    than at the model means the sign convention lives in one place.
    """
    return -_cumulative_return(_returns(frame), 5)


def acceleration(frame: pd.DataFrame) -> pd.Series:
    """Recent momentum minus older momentum — is the trend strengthening?

    Distinct from momentum itself: two names with identical 63-day returns
    differ if one earned it in the first month and the other in the last.
    """
    returns = _returns(frame)
    recent = _cumulative_return(returns, 21)
    older = _cumulative_return(returns, 63).shift(21)
    return recent - older


# ── volatility ───────────────────────────────────────────────────────────────


def realised_volatility_21(frame: pd.DataFrame) -> pd.Series:
    return _returns(frame).rolling(21, min_periods=21).std(ddof=1) * np.sqrt(TRADING_DAYS)


def realised_volatility_63(frame: pd.DataFrame) -> pd.Series:
    return _returns(frame).rolling(63, min_periods=63).std(ddof=1) * np.sqrt(TRADING_DAYS)


def downside_volatility_63(frame: pd.DataFrame) -> pd.Series:
    """Volatility of negative returns only.

    Total volatility punishes upside and downside identically, which is not how
    a holder experiences them. The denominator is the full window, not the
    count of negative days, so this is downside deviation rather than the
    standard deviation of a filtered sample.
    """
    returns = _returns(frame)
    negative = returns.where(returns < 0, 0.0)
    squared = negative.pow(2).rolling(63, min_periods=63).mean()
    valid = returns.rolling(63, min_periods=63).count() >= 63
    return (np.sqrt(squared) * np.sqrt(TRADING_DAYS)).where(valid)


def volatility_ratio(frame: pd.DataFrame) -> pd.Series:
    """Short-horizon volatility against long — a volatility regime change.

    Above 1 means the name is currently more volatile than its own recent norm.
    Self-referencing rather than cross-sectional, so it is comparable across
    names of very different absolute volatility.
    """
    short = realised_volatility_21(frame)
    long = realised_volatility_63(frame)
    return (short / long.where(long.abs() > _EPSILON)).replace([np.inf, -np.inf], np.nan)


def max_drawdown_252(frame: pd.DataFrame) -> pd.Series:
    """Deepest peak-to-trough fall inside the trailing year, as a positive number."""
    returns = _returns(frame)
    index = np.log1p(returns).rolling(TRADING_DAYS, min_periods=TRADING_DAYS).sum()
    wealth = np.log1p(returns).fillna(0.0).cumsum()
    peak = wealth.rolling(TRADING_DAYS, min_periods=TRADING_DAYS).max()
    return (-(np.expm1(wealth - peak))).where(index.notna())


# ── liquidity ────────────────────────────────────────────────────────────────


def log_dollar_volume_21(frame: pd.DataFrame) -> pd.Series:
    """Log mean dollar volume — the size control.

    Logged because dollar volume spans six orders of magnitude across the
    cross-section, and a linear model fed the raw number is fitting the largest
    two names. Dollar volume rather than share volume because it is continuous
    through splits with no adjustment (see `pit/adjust.py`).
    """
    dollar = pd.to_numeric(frame["dollar_volume"], errors="coerce").astype(float)
    mean = dollar.rolling(21, min_periods=21).mean()
    return np.log(mean.where(mean > 0))


def volume_shock(frame: pd.DataFrame) -> pd.Series:
    """Today's dollar volume against its own trailing quarter, in z-scores.

    A crowding/attention proxy. Standardised per symbol rather than
    cross-sectionally so it means "unusual for this name" rather than "large".
    """
    dollar = pd.to_numeric(frame["dollar_volume"], errors="coerce").astype(float)
    mean = dollar.rolling(63, min_periods=63).mean()
    std = dollar.rolling(63, min_periods=63).std(ddof=1)
    return ((dollar - mean) / std.where(std.abs() > _EPSILON)).replace(
        [np.inf, -np.inf], np.nan
    )


def amihud_illiquidity_21(frame: pd.DataFrame) -> pd.Series:
    """Amihud (2002): mean |return| per dollar traded.

    Price impact per unit of volume — how much a name moves when someone trades
    it. Scaled by 1e6 to keep the values in a range a linear model can carry
    without the coefficient underflowing, and logged for the same reason as
    dollar volume.
    """
    returns = _returns(frame).abs()
    dollar = pd.to_numeric(frame["dollar_volume"], errors="coerce").astype(float)
    ratio = (returns / dollar.where(dollar > 0)) * 1e6
    mean = ratio.rolling(21, min_periods=21).mean()
    return np.log(mean.where(mean > 0))


# ── structure ────────────────────────────────────────────────────────────────


def distance_to_52w_high(frame: pd.DataFrame) -> pd.Series:
    """How far below the trailing-year high the name sits, as a fraction.

    George-Hwang (2004) find the 52-week-high proximity carries information
    momentum does not. Computed from the point-in-time return index rather than
    raw close, so a split does not manufacture a new "high".
    """
    wealth = np.log1p(_returns(frame)).fillna(0.0).cumsum()
    high = wealth.rolling(TRADING_DAYS, min_periods=TRADING_DAYS).max()
    return np.expm1(wealth - high)


def trend_strength_63(frame: pd.DataFrame) -> pd.Series:
    """Trailing return divided by trailing volatility — a path-quality measure.

    Two names with the same 63-day return are different propositions if one
    walked there and the other lurched. This is the trailing information ratio,
    unannualised in the numerator and annualised in the denominator, which is
    why it is used as an ordering rather than read as a Sharpe.
    """
    momentum = _cumulative_return(_returns(frame), 63)
    volatility = realised_volatility_63(frame)
    return (momentum / volatility.where(volatility.abs() > _EPSILON)).replace(
        [np.inf, -np.inf], np.nan
    )


def moving_average_gap(frame: pd.DataFrame) -> pd.Series:
    """Log gap between the 21- and 126-session moving averages of the return index."""
    wealth = np.log1p(_returns(frame)).fillna(0.0).cumsum()
    fast = wealth.rolling(21, min_periods=21).mean()
    slow = wealth.rolling(126, min_periods=126).mean()
    return fast - slow


def _register() -> None:
    """Declare every feature. Definitions carry the point-in-time contract."""

    def add(definition: FeatureDefinition, fn) -> None:
        REGISTRY.register(definition, fn)

    add(
        FeatureDefinition(
            name="mom_21",
            group=FeatureGroup.PRICE,
            description="Compounded total return over the trailing 21 sessions.",
            rationale="One-month momentum; also the leg excluded from mom_252_21.",
            formula="prod(1 + r_t) over t in (T-20, T] - 1",
            lookback_sessions=21,
            required_columns=("total_return",),
            direction=Direction.TWO_SIDED,
        ),
        momentum_21,
    )
    add(
        FeatureDefinition(
            name="mom_63",
            group=FeatureGroup.PRICE,
            description="Compounded total return over the trailing 63 sessions.",
            rationale="Quarter-horizon momentum, the shortest horizon at which the effect is usually reported.",
            formula="prod(1 + r_t) over t in (T-62, T] - 1",
            lookback_sessions=63,
            required_columns=("total_return",),
            direction=Direction.POSITIVE,
        ),
        momentum_63,
    )
    add(
        FeatureDefinition(
            name="mom_252_21",
            group=FeatureGroup.PRICE,
            description="12-1 momentum: trailing year excluding the most recent month.",
            rationale=(
                "The canonical cross-sectional momentum construction. The skipped "
                "month keeps short-horizon reversal out of the signal."
            ),
            formula="(1 + r_252) / (1 + r_21) - 1",
            lookback_sessions=TRADING_DAYS,
            required_columns=("total_return",),
            direction=Direction.POSITIVE,
            citation="Jegadeesh & Titman (1993)",
        ),
        momentum_252_21,
    )
    add(
        FeatureDefinition(
            name="reversal_5",
            group=FeatureGroup.PRICE,
            description="Negated trailing 5-session return.",
            rationale="Short-horizon reversal; negated so the hypothesis is positive.",
            formula="-(prod(1 + r_t) over the last 5 sessions - 1)",
            lookback_sessions=5,
            required_columns=("total_return",),
            direction=Direction.POSITIVE,
            citation="Lehmann (1990); Jegadeesh (1990)",
        ),
        reversal_5,
    )
    add(
        FeatureDefinition(
            name="acceleration",
            group=FeatureGroup.PRICE,
            description="Trailing-month return minus the quarter-return ending a month ago.",
            rationale="Separates a strengthening trend from a decaying one at equal total return.",
            formula="r_21(T) - r_63(T - 21)",
            lookback_sessions=84,
            required_columns=("total_return",),
            direction=Direction.TWO_SIDED,
        ),
        acceleration,
    )
    add(
        FeatureDefinition(
            name="vol_21",
            group=FeatureGroup.VOLATILITY,
            description="Annualised realised volatility over 21 sessions.",
            rationale="Risk scaling and the base of the low-volatility effect.",
            formula="std(r, 21) * sqrt(252)",
            lookback_sessions=21,
            required_columns=("total_return",),
            direction=Direction.NEGATIVE,
        ),
        realised_volatility_21,
    )
    add(
        FeatureDefinition(
            name="vol_63",
            group=FeatureGroup.VOLATILITY,
            description="Annualised realised volatility over 63 sessions.",
            rationale="Slower risk estimate; the denominator of trend_strength_63.",
            formula="std(r, 63) * sqrt(252)",
            lookback_sessions=63,
            required_columns=("total_return",),
            direction=Direction.NEGATIVE,
        ),
        realised_volatility_63,
    )
    add(
        FeatureDefinition(
            name="downside_vol_63",
            group=FeatureGroup.VOLATILITY,
            description="Downside deviation over 63 sessions, annualised.",
            rationale="Investors do not experience upside and downside variance alike.",
            formula="sqrt(mean(min(r, 0)^2, 63)) * sqrt(252)",
            lookback_sessions=63,
            required_columns=("total_return",),
            direction=Direction.NEGATIVE,
        ),
        downside_volatility_63,
    )
    add(
        FeatureDefinition(
            name="vol_ratio",
            group=FeatureGroup.VOLATILITY,
            description="21-session volatility divided by 63-session volatility.",
            rationale="Volatility regime change, self-referencing so it is comparable across names.",
            formula="vol_21 / vol_63",
            lookback_sessions=63,
            required_columns=("total_return",),
            direction=Direction.TWO_SIDED,
        ),
        volatility_ratio,
    )
    add(
        FeatureDefinition(
            name="max_drawdown_252",
            group=FeatureGroup.VOLATILITY,
            description="Deepest peak-to-trough decline in the trailing year, positive.",
            rationale="Path risk that neither volatility nor total return expresses.",
            formula="max over the window of (peak - value) / peak",
            lookback_sessions=TRADING_DAYS,
            required_columns=("total_return",),
            direction=Direction.NEGATIVE,
        ),
        max_drawdown_252,
    )
    add(
        FeatureDefinition(
            name="log_dollar_volume_21",
            group=FeatureGroup.VOLUME,
            description="Log of mean daily dollar volume over 21 sessions.",
            rationale="Liquidity and size control; split-invariant by construction.",
            formula="log(mean(close * volume, 21))",
            lookback_sessions=21,
            required_columns=("dollar_volume",),
            direction=Direction.DESCRIPTIVE,
        ),
        log_dollar_volume_21,
    )
    add(
        FeatureDefinition(
            name="volume_shock",
            group=FeatureGroup.VOLUME,
            description="Dollar volume z-scored against its own trailing 63 sessions.",
            rationale="Attention or crowding, measured relative to the name's own norm.",
            formula="(dv - mean(dv, 63)) / std(dv, 63)",
            lookback_sessions=63,
            required_columns=("dollar_volume",),
            direction=Direction.TWO_SIDED,
        ),
        volume_shock,
    )
    add(
        FeatureDefinition(
            name="amihud_21",
            group=FeatureGroup.VOLUME,
            description="Log Amihud illiquidity over 21 sessions.",
            rationale="Price impact per dollar traded; the standard illiquidity premium proxy.",
            formula="log(mean(|r| / dollar_volume * 1e6, 21))",
            lookback_sessions=21,
            required_columns=("total_return", "dollar_volume"),
            direction=Direction.POSITIVE,
            citation="Amihud (2002)",
        ),
        amihud_illiquidity_21,
    )
    add(
        FeatureDefinition(
            name="dist_52w_high",
            group=FeatureGroup.STRUCTURE,
            description="Fractional distance below the trailing-year high (<= 0).",
            rationale="Carries information beyond momentum; anchoring to a salient level.",
            formula="index_T / max(index over 252) - 1",
            lookback_sessions=TRADING_DAYS,
            required_columns=("total_return",),
            direction=Direction.POSITIVE,
            citation="George & Hwang (2004)",
        ),
        distance_to_52w_high,
    )
    add(
        FeatureDefinition(
            name="trend_strength_63",
            group=FeatureGroup.STRUCTURE,
            description="63-session return divided by 63-session annualised volatility.",
            rationale="Path quality: distinguishes a steady climb from a volatile one.",
            formula="mom_63 / vol_63",
            lookback_sessions=63,
            required_columns=("total_return",),
            direction=Direction.POSITIVE,
        ),
        trend_strength_63,
    )
    add(
        FeatureDefinition(
            name="ma_gap",
            group=FeatureGroup.STRUCTURE,
            description="Log-index 21-session mean minus 126-session mean.",
            rationale="Trend state as a level rather than a crossing event.",
            formula="mean(log_index, 21) - mean(log_index, 126)",
            lookback_sessions=126,
            required_columns=("total_return",),
            direction=Direction.POSITIVE,
        ),
        moving_average_gap,
    )


_register()
