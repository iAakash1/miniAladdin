"""
Cross-sectional factor evaluation — does a factor rank names correctly?

## Why this exists

Every view in OmniSignal answered questions about *one* stock. That is the
wrong shape for the question a factor actually makes: a factor does not
predict that NVDA will rise, it predicts that names it ranks highly will
outperform names it ranks poorly. Judging it one ticker at a time cannot
distinguish a working factor from a rising market.

The point-in-time panel was built for exactly this — wide layout, one column
per factor, so ranking reads a single column across every symbol on a date —
and until now nothing consumed it that way.

## What it measures

**Rank IC** (information coefficient): the Spearman correlation, on each
date, between a factor's cross-sectional ranking and the *subsequent*
forward return. One number per date; a factor that works has a positive
mean.

Rank rather than Pearson because factor scores are already squashed through
`tanh` and returns are fat-tailed — a linear correlation on that pair
measures the tails, not the ordering, and the ordering is the claim.

**Quantile spread**: mean forward return of the top bucket minus the bottom.
The IC says "ordering carries information"; the spread says "how much, if you
traded it". They can disagree, and when they do the disagreement is the
finding.

## The statistic that matters most

A 21-day forward return sampled every 5 days means consecutive observations
share 16 of their 21 days. They are not independent, and the naive
`mean / (std / √n)` t-statistic is inflated — often by 2× — because it
assumes they are.

`newey_west_tstat` corrects for that with a Bartlett kernel over
`ceil(horizon / step) - 1` lags. This is the difference between a factor that
looks significant and one that is, and it is the single most important line
in this module.

## What it deliberately does not do

No p-value gets rounded up into a verdict. `Evaluation.assessment` reports
what the numbers support and stops — including, frequently, "no evidence of
predictive power on this sample". A research tool that never returns a
negative result is not measuring anything.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date as Date
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.research.cross_section")

#: Below this, a cross-sectional rank is noise rather than a ranking. Ten
#: names give deciles of one, which is already thin; fewer is not a
#: cross-section at all.
MIN_NAMES_PER_DATE = 10

#: Below this many dates, the mean IC has no meaningful standard error and
#: any t-statistic computed from it is theatre.
MIN_DATES = 12

#: |t| above this is conventionally "significant". Stated as a named constant
#: because it is a convention, not a law, and the reports say so.
SIGNIFICANCE_T = 2.0


@dataclass(frozen=True)
class Evaluation:
    """One factor's out-of-sample record. Every field is evidence, not opinion."""

    factor: str
    dates: int
    names_median: int
    mean_ic: float
    std_ic: float
    t_stat: float                    # Newey-West corrected
    naive_t_stat: float              # uncorrected, for comparison
    hit_rate: float                  # share of dates with positive IC
    ic_series: list[tuple[str, float]]
    top_minus_bottom: Optional[float]
    quantiles: int
    horizon_days: int
    newey_west_lags: int
    saturation: float                # share of cells clipped at the winsor bound

    @property
    def significant(self) -> bool:
        return abs(self.t_stat) >= SIGNIFICANCE_T

    @property
    def inflation(self) -> float:
        """How much the naive t-statistic overstated significance."""
        if self.t_stat == 0:
            return float("inf")
        return abs(self.naive_t_stat / self.t_stat)

    @property
    def assessment(self) -> str:
        """Plain English, and willing to say a factor does not work."""
        if not self.significant:
            direction = "no evidence of predictive power"
            if self.mean_ic < -0.01:
                direction = "no reliable signal (mean IC is negative)"
            return (
                f"{direction} on this sample — mean rank IC {self.mean_ic:+.4f}, "
                f"t={self.t_stat:.2f} over {self.dates} dates"
            )
        direction = "ranks names correctly" if self.mean_ic > 0 else "ranks names inversely"
        return (
            f"{direction} — mean rank IC {self.mean_ic:+.4f}, t={self.t_stat:.2f} "
            f"over {self.dates} dates"
        )


def spearman_ic(factor: pd.Series, forward: pd.Series) -> Optional[float]:
    """Rank correlation between a factor and forward returns on one date.

    None rather than 0.0 when undefined: a date where every name shares the
    same factor value has no ranking, and calling that "zero correlation"
    would fold a missing observation into the mean as if it were evidence.
    """
    paired = pd.concat([factor, forward], axis=1).dropna()
    if len(paired) < MIN_NAMES_PER_DATE:
        return None
    left, right = paired.iloc[:, 0], paired.iloc[:, 1]
    if left.nunique() < 2 or right.nunique() < 2:
        return None
    value = left.rank().corr(right.rank())
    return None if pd.isna(value) else float(value)


def newey_west_tstat(values: np.ndarray, lags: int) -> float:
    """t-statistic for the mean, robust to autocorrelation.

    Overlapping forward returns make consecutive IC observations dependent,
    which inflates the naive t-statistic. This applies a Bartlett kernel over
    `lags` autocovariances:

        var = γ₀ + 2·Σ_{j=1..L} (1 − j/(L+1)) · γ_j
        t   = mean / sqrt(var / n)

    `lags=0` reduces to the naive statistic computed with the *population*
    variance (ddof=0), not the sample variance — a distinction worth stating
    because the two differ by sqrt(n/(n-1)) and the tests assert the exact
    identity rather than an approximate one.
    """
    count = len(values)
    if count < 2:
        return 0.0

    centered = values - values.mean()
    variance = float(centered @ centered) / count           # γ₀
    for lag in range(1, min(lags, count - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)                   # Bartlett
        autocov = float(centered[lag:] @ centered[:-lag]) / count
        variance += 2.0 * weight * autocov

    # Autocovariances can drive the estimate non-positive on short samples.
    # Falling back to the naive variance is the honest response: it reports a
    # *larger* t than the correction would, so it never manufactures
    # significance the correction was going to remove.
    if variance <= 0:
        variance = float(centered @ centered) / count
        if variance <= 0:
            return 0.0

    return float(values.mean() / math.sqrt(variance / count))


def quantile_spread(
    factor: pd.Series, forward: pd.Series, buckets: int
) -> Optional[float]:
    """Mean forward return of the top bucket minus the bottom, on one date."""
    paired = pd.concat([factor, forward], axis=1).dropna()
    if len(paired) < buckets * 2:
        return None
    left, right = paired.iloc[:, 0], paired.iloc[:, 1]
    try:
        labels = pd.qcut(left.rank(method="first"), buckets, labels=False)
    except ValueError:
        return None  # too few distinct values to bucket
    top = right[labels == buckets - 1].mean()
    bottom = right[labels == 0].mean()
    if pd.isna(top) or pd.isna(bottom):
        return None
    return float(top - bottom)


def forward_returns(
    prices: dict[str, pd.Series], dates: list[Date], horizon: int
) -> pd.DataFrame:
    """Realised return over the `horizon` bars following each date.

    Deliberately **not** stored in the panel. The panel records what was
    knowable at `as_of`; a forward return is an evaluation artifact that is
    knowable only later. Its two-timestamp schema could represent that
    honestly, but keeping outcomes out of the factor store preserves a
    sharper line: the panel is what the engine saw, this is what happened
    next, and nothing in the panel can accidentally depend on the future.

    Returns a long frame of (symbol, date, forward_return).
    """
    rows: list[dict[str, object]] = []
    for symbol, series in prices.items():
        if series.empty:
            continue
        index = series.index
        for observed_on in dates:
            stamp = pd.Timestamp(observed_on)
            position = index.searchsorted(stamp, side="right") - 1
            if position < 0 or position + horizon >= len(series):
                continue
            base = float(series.iloc[position])
            if base <= 0:
                continue
            rows.append({
                "symbol": symbol,
                "date": observed_on,
                "forward_return": float(series.iloc[position + horizon]) / base - 1.0,
            })
    return pd.DataFrame(rows, columns=["symbol", "date", "forward_return"])


def saturation_rate(values: pd.Series) -> float:
    """Share of scores sitting exactly on the winsorization bound.

    The engine clips every z-score to ±`WINSOR_Z` before squashing, so any
    name beyond that bound lands on the identical score. Those names are not
    ranked relative to each other — the ordering among them is whatever the
    sort happened to produce.

    That matters for a factor's *measured* IC: a factor saturating a quarter
    of the universe has discarded ordering information at exactly the end a
    long/short reading cares about, and no amount of forward-return data can
    recover it. Measured on the mega-cap universe, `r12_1` clips 24% of names
    while every other price factor clips under 5%.
    """
    from src.scoring.engine import WINSOR_Z, squash

    bound = abs(squash(WINSOR_Z))
    clean = values.dropna()
    if clean.empty:
        return 0.0
    return float((clean.abs() >= bound - 1e-9).mean())


def evaluate_factor(
    panel: pd.DataFrame,
    factor: str,
    horizon: int,
    step_days: int,
    quantiles: int = 5,
) -> Optional[Evaluation]:
    """Evaluate one factor across the cross-section. None when unevaluable.

    `panel` must carry `symbol`, `date`, `forward_return` and the factor
    column. Returning None rather than a zeroed Evaluation keeps "we could
    not measure this" distinct from "we measured no effect".
    """
    if factor not in panel.columns:
        return None

    ic_by_date: list[tuple[Date, float]] = []
    spreads: list[float] = []
    name_counts: list[int] = []
    saturations: list[float] = []

    for observed_on, group in panel.groupby("date", sort=True):
        value = spearman_ic(group[factor], group["forward_return"])
        if value is None:
            continue
        ic_by_date.append((observed_on, value))
        name_counts.append(int(group[[factor, "forward_return"]].dropna().shape[0]))
        saturations.append(saturation_rate(group[factor]))
        spread = quantile_spread(group[factor], group["forward_return"], quantiles)
        if spread is not None:
            spreads.append(spread)

    if len(ic_by_date) < MIN_DATES:
        logger.info(
            "cross-section: %s has %d evaluable dates, need %d",
            factor, len(ic_by_date), MIN_DATES,
        )
        return None

    values = np.array([value for _, value in ic_by_date])
    # Observations overlap whenever the horizon exceeds the sampling step.
    lags = max(0, math.ceil(horizon / max(step_days, 1)) - 1)
    naive = (
        float(values.mean() / (values.std(ddof=1) / math.sqrt(len(values))))
        if values.std(ddof=1) > 0 else 0.0
    )

    return Evaluation(
        factor=factor,
        dates=len(values),
        names_median=int(np.median(name_counts)) if name_counts else 0,
        mean_ic=float(values.mean()),
        std_ic=float(values.std(ddof=1)),
        t_stat=newey_west_tstat(values, lags),
        naive_t_stat=naive,
        hit_rate=float((values > 0).mean()),
        ic_series=[(str(day), round(value, 4)) for day, value in ic_by_date],
        top_minus_bottom=float(np.mean(spreads)) if spreads else None,
        quantiles=quantiles,
        horizon_days=horizon,
        newey_west_lags=lags,
        saturation=float(np.mean(saturations)) if saturations else 0.0,
    )


def rank_cross_section(
    panel: pd.DataFrame, factor: str, observed_on: Date, limit: int = 0
) -> list[dict[str, object]]:
    """Every name on one date, ranked by one factor.

    The view the panel's wide layout exists to serve: one column, every
    symbol, one date. Percentile is reported alongside the raw score because
    a `tanh`-squashed score is not interpretable on its own — "0.42" means
    nothing, "87th percentile of this universe today" means something.
    """
    if factor not in panel.columns:
        return []
    day = panel[(panel["date"] == observed_on) & panel[factor].notna()]
    if day.empty:
        return []

    ordered = day.sort_values(factor, ascending=False).reset_index(drop=True)
    percentiles = ordered[factor].rank(pct=True)

    rows = [
        {
            "rank": position + 1,
            "symbol": row["symbol"],
            "score": round(float(row[factor]), 4),
            "percentile": round(float(percentiles.iloc[position]) * 100, 1),
            "forward_return": (
                round(float(row["forward_return"]), 4)
                if "forward_return" in ordered.columns and pd.notna(row["forward_return"])
                else None
            ),
        }
        for position, row in ordered.iterrows()
    ]
    return rows[:limit] if limit else rows
