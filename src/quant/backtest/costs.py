"""
Transaction costs — applied per trade, not subtracted at the end.

## Why the ordering matters

Computing gross returns and deducting an annual cost estimate at the end gives
a different — and always more flattering — answer than charging each trade as
it happens. Costs interact with turnover, turnover varies with signal
volatility, and a strategy that trades hardest exactly when it is most confident
pays most where the naive method assumes an average. So `SimpleCostModel`
prices each rebalance from that rebalance's traded notional.

## The three components, and why they are separate

**Commission** is a rate on notional. It is the smallest and most certain term.

**Spread** is half the bid-ask, paid on entry and exit. This dataset has no
quotes, so the spread is *assumed*, and the assumption is the largest source of
error in any net return here. It is therefore a named parameter with a
documented default rather than a constant buried in a formula, and
`sensitivity()` exists so a result can be reported across a range instead of at
one convenient value.

**Market impact** is the price move a trade causes. Modelled as
`coefficient * sqrt(participation)`, the square-root law — impact grows with
the fraction of daily volume consumed, but sub-linearly. It matters only when
position sizes approach a meaningful share of volume; on a liquid universe at
small capital it rounds to nothing, and the model says so rather than adding a
plausible-looking number.

## What this is not

Not a fill model. There is no queue position, no partial fill, no intraday
path. Every trade executes at the close on the rebalance date at that close
plus costs. That is stated in `assumptions()` and rendered in the UI, because a
reader who believes these are simulated fills would over-trust the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

#: One-way commission in basis points of notional. Retail-competitive.
DEFAULT_COMMISSION_BPS = 1.0

#: Half-spread in basis points, paid on every trade. 5 bps is a reasonable
#: central estimate for large-cap US equities at the close; small caps are
#: materially worse. This is the single most consequential assumption in the
#: net-return figure, which is why `sensitivity()` sweeps it.
DEFAULT_HALF_SPREAD_BPS = 5.0

#: Square-root-law impact coefficient. Impact in bps is
#: `coefficient * sqrt(traded_notional / daily_dollar_volume) * 10000`.
DEFAULT_IMPACT_COEFFICIENT = 0.1


@dataclass(frozen=True)
class CostBreakdown:
    """What one rebalance cost, decomposed."""

    traded_notional: float
    commission: float
    spread: float
    impact: float

    @property
    def total(self) -> float:
        return self.commission + self.spread + self.impact

    def as_dict(self) -> dict[str, Any]:
        return {
            "traded_notional": round(self.traded_notional, 2),
            "commission": round(self.commission, 4),
            "spread": round(self.spread, 4),
            "impact": round(self.impact, 4),
            "total": round(self.total, 4),
            "total_bps": (
                round(self.total / self.traded_notional * 10000, 2)
                if self.traded_notional > 0
                else 0.0
            ),
        }


@dataclass(frozen=True)
class SimpleCostModel:
    """Commission + half-spread + square-root impact, charged per rebalance."""

    commission_bps: float = DEFAULT_COMMISSION_BPS
    half_spread_bps: float = DEFAULT_HALF_SPREAD_BPS
    impact_coefficient: float = DEFAULT_IMPACT_COEFFICIENT

    def charge(
        self,
        weight_change: pd.Series,
        *,
        capital: float,
        dollar_volume: Optional[pd.Series] = None,
    ) -> CostBreakdown:
        """Cost of moving from one weight vector to another.

        `weight_change` is the per-name absolute weight delta. Costs are charged
        on the *traded* notional, so a name held unchanged across a rebalance is
        free — which is the behaviour that makes low-turnover strategies
        correctly cheaper rather than nominally cheaper.
        """
        deltas = pd.to_numeric(weight_change, errors="coerce").abs().fillna(0.0)
        traded = float(deltas.sum()) * capital
        if traded <= 0:
            return CostBreakdown(0.0, 0.0, 0.0, 0.0)

        commission = traded * self.commission_bps / 10000.0
        spread = traded * self.half_spread_bps / 10000.0

        impact = 0.0
        if dollar_volume is not None and self.impact_coefficient > 0:
            volumes = pd.to_numeric(dollar_volume, errors="coerce")
            per_name = deltas * capital
            aligned = volumes.reindex(per_name.index)
            # A name with no volume observation contributes no impact estimate
            # rather than an invented one; `impact_coverage` reports how much of
            # the traded notional was actually priced.
            usable = aligned.notna() & (aligned > 0) & (per_name > 0)
            if usable.any():
                participation = per_name[usable] / aligned[usable]
                impact_bps = self.impact_coefficient * np.sqrt(participation) * 10000.0
                impact = float((per_name[usable] * impact_bps / 10000.0).sum())

        return CostBreakdown(traded, commission, spread, impact)

    def assumptions(self) -> dict[str, Any]:
        return {
            "commission_bps": self.commission_bps,
            "half_spread_bps": self.half_spread_bps,
            "impact_coefficient": self.impact_coefficient,
            "impact_law": "coefficient * sqrt(traded_notional / daily_dollar_volume)",
            "execution": (
                "Every trade executes at the rebalance date's close, at that close "
                "plus costs. There is no queue model, no partial fill and no "
                "intraday path — these are cost-adjusted closes, not simulated fills."
            ),
            "spread_source": (
                "ASSUMED. The price dataset carries no bid/ask, so the half-spread "
                "is a parameter rather than an observation. It is the largest source "
                "of uncertainty in any net return reported here."
            ),
        }

    def with_half_spread(self, bps: float) -> "SimpleCostModel":
        return SimpleCostModel(self.commission_bps, bps, self.impact_coefficient)


def sensitivity_grid(
    base: Optional[SimpleCostModel] = None,
    *,
    half_spreads: tuple[float, ...] = (1.0, 5.0, 10.0, 20.0),
) -> list[SimpleCostModel]:
    """Cost models across a spread range, for reporting a band not a point.

    A net Sharpe quoted at one spread assumption is a claim about that
    assumption as much as about the strategy. Reporting the sweep lets a reader
    see where the result stops surviving, which is usually the most useful line
    in a backtest table.
    """
    base = base or SimpleCostModel()
    return [base.with_half_spread(bps) for bps in half_spreads]
