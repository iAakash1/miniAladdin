"""
Factor portfolios — what a factor would have done to actual money.

Rank IC says a factor orders names correctly. Quantile spread says the top
beat the bottom on average. Neither says whether you would have made money,
because neither compounds, neither accounts for the trading a rebalance
implies, and neither shows the path — and the path is what a person actually
lives through.

Each rebalance date: rank the universe on the factor, go equal-weight long
the top bucket and equal-weight short the bottom, hold until the next
rebalance, repeat.

**Non-overlapping by construction.** The holding period equals the rebalance
interval, so period returns never share days. This is the deliberate
difference from `evaluate_factor`, which uses a longer horizon and needs a
Newey-West correction precisely because its observations do overlap. Here the
overlap is designed out rather than corrected for, which is why the Sharpe
ratio below needs no such adjustment.

Costs are not modelled. A long/short book rebalanced weekly at 40% turnover
is not free, and the `turnover` field is reported so the reader can apply
their own assumption rather than inherit one invented here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as Date
from typing import Optional

import numpy as np
import pandas as pd

#: Trading days per year, for annualising.
PERIODS_PER_YEAR = 252

#: Fewer names than this cannot form two distinct buckets worth trading.
MIN_NAMES = 10


@dataclass(frozen=True)
class PortfolioResult:
    """One factor's simulated long/short record."""

    factor: str
    buckets: int
    rebalances: int
    total_return: float
    annualised_return: float
    annualised_volatility: float
    sharpe: float
    max_drawdown: float
    hit_rate: float
    turnover: float
    long_leg_return: float
    short_leg_return: float
    benchmark_return: float
    equity_curve: list[dict[str, object]]

    @property
    def beat_benchmark(self) -> bool:
        return self.total_return > self.benchmark_return

    @property
    def assessment(self) -> str:
        if self.rebalances < 20:
            return f"too few rebalances ({self.rebalances}) to judge"
        if self.sharpe > 1.0:
            quality = "strong risk-adjusted return"
        elif self.sharpe > 0.5:
            quality = "modest risk-adjusted return"
        elif self.sharpe > 0:
            quality = "positive but weak"
        else:
            quality = "lost money"
        return (
            f"{quality} — {self.total_return * 100:+.1f}% total, Sharpe "
            f"{self.sharpe:.2f}, max drawdown {self.max_drawdown * 100:.1f}%, "
            f"{self.turnover * 100:.0f}% turnover per rebalance"
        )


def _drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity / peak - 1.0)) if len(equity) else 0.0


def simulate(
    panel: pd.DataFrame,
    factor: str,
    buckets: int = 5,
    periods_per_year: int = PERIODS_PER_YEAR // 5,
) -> Optional[PortfolioResult]:
    """Simulate a long/short factor portfolio. None when unsimulatable.

    `panel` needs `symbol`, `date`, `period_return` (the return realised over
    the holding period following that date) and the factor column.
    `periods_per_year` defaults to weekly rebalancing.
    """
    if factor not in panel.columns or "period_return" not in panel.columns:
        return None

    period_returns: list[float] = []
    long_returns: list[float] = []
    short_returns: list[float] = []
    benchmark_returns: list[float] = []
    turnovers: list[float] = []
    dates: list[Date] = []

    previous_long: set[str] = set()
    previous_short: set[str] = set()

    for observed_on, group in panel.groupby("date", sort=True):
        usable = group[[factor, "period_return", "symbol"]].dropna()
        if len(usable) < MIN_NAMES:
            continue

        ranked = usable.sort_values(factor, ascending=False)
        size = max(1, len(ranked) // buckets)
        long_side = ranked.head(size)
        short_side = ranked.tail(size)

        long_return = float(long_side["period_return"].mean())
        short_return = float(short_side["period_return"].mean())

        long_names = set(long_side["symbol"])
        short_names = set(short_side["symbol"])
        if previous_long or previous_short:
            changed = (
                len(long_names ^ previous_long) + len(short_names ^ previous_short)
            )
            held = len(long_names) + len(short_names)
            turnovers.append(changed / (2 * held) if held else 0.0)
        previous_long, previous_short = long_names, short_names

        dates.append(observed_on)
        long_returns.append(long_return)
        short_returns.append(short_return)
        period_returns.append(long_return - short_return)
        benchmark_returns.append(float(usable["period_return"].mean()))

    if len(period_returns) < 4:
        return None

    returns = np.array(period_returns)
    equity = np.cumprod(1.0 + returns)
    benchmark_equity = np.cumprod(1.0 + np.array(benchmark_returns))

    years = len(returns) / periods_per_year
    total = float(equity[-1] - 1.0)
    volatility = float(returns.std(ddof=1) * math.sqrt(periods_per_year))
    annualised = float(equity[-1] ** (1 / years) - 1.0) if years > 0 and equity[-1] > 0 else 0.0

    return PortfolioResult(
        factor=factor,
        buckets=buckets,
        rebalances=len(returns),
        total_return=total,
        annualised_return=annualised,
        annualised_volatility=volatility,
        sharpe=float(annualised / volatility) if volatility > 0 else 0.0,
        max_drawdown=_drawdown(equity),
        hit_rate=float((returns > 0).mean()),
        turnover=float(np.mean(turnovers)) if turnovers else 0.0,
        long_leg_return=float(np.cumprod(1.0 + np.array(long_returns))[-1] - 1.0),
        short_leg_return=float(np.cumprod(1.0 + np.array(short_returns))[-1] - 1.0),
        benchmark_return=float(benchmark_equity[-1] - 1.0),
        equity_curve=[
            {
                "date": str(day),
                "strategy": round(float(value), 5),
                "benchmark": round(float(mark), 5),
            }
            for day, value, mark in zip(dates, equity, benchmark_equity)
        ],
    )
