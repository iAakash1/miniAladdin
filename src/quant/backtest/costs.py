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
    slippage: float = 0.0

    @property
    def total(self) -> float:
        return self.commission + self.spread + self.impact + self.slippage

    def as_dict(self) -> dict[str, Any]:
        return {
            "traded_notional": round(self.traded_notional, 2),
            "commission": round(self.commission, 4),
            "spread": round(self.spread, 4),
            "slippage": round(self.slippage, 4),
            "impact": round(self.impact, 4),
            "total": round(self.total, 4),
            "total_bps": (
                round(self.total / self.traded_notional * 10000, 2)
                if self.traded_notional > 0
                else 0.0
            ),
        }


#: Slippage: adverse fill relative to the decision price, beyond the quoted
#: spread. Distinct from `half_spread_bps` because they have different causes —
#: spread is what the book charges to cross, slippage is the price moving while
#: an order works. Defaulting to 0 keeps every historical figure unchanged;
#: the parameter exists so the assumption is explicit rather than absent.
DEFAULT_SLIPPAGE_BPS = 0.0


@dataclass(frozen=True)
class CostWaterfall:
    """Return decomposed one cost layer at a time.

    A single "net of costs" figure hides which assumption is load-bearing. This
    project's central finding is that a strategy with a POSITIVE gross Sharpe
    has a NEGATIVE net one, so the step where the sign flips is the result — and
    a scalar cannot show it.
    """

    gross: float
    after_commission: float
    after_spread: float
    after_slippage: float
    net: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "gross": round(self.gross, 8),
            "after_commission": round(self.after_commission, 8),
            "after_spread": round(self.after_spread, 8),
            "after_slippage": round(self.after_slippage, 8),
            "net": round(self.net, 8),
            "commission_drag": round(self.gross - self.after_commission, 8),
            "spread_drag": round(self.after_commission - self.after_spread, 8),
            "slippage_drag": round(self.after_spread - self.after_slippage, 8),
            "impact_drag": round(self.after_slippage - self.net, 8),
            "total_drag": round(self.gross - self.net, 8),
            "sign_flips": bool(self.gross > 0 >= self.net),
            "order": [
                "gross", "after_commission", "after_spread",
                "after_slippage", "net (after impact)",
            ],
        }


@dataclass(frozen=True)
class SimpleCostModel:
    """Commission + half-spread + slippage + square-root impact, per rebalance."""

    commission_bps: float = DEFAULT_COMMISSION_BPS
    half_spread_bps: float = DEFAULT_HALF_SPREAD_BPS
    impact_coefficient: float = DEFAULT_IMPACT_COEFFICIENT
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS

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
            return CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0)

        commission = traded * self.commission_bps / 10000.0
        spread = traded * self.half_spread_bps / 10000.0
        slippage = traded * self.slippage_bps / 10000.0

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

        return CostBreakdown(traded, commission, spread, impact, slippage)

    def assumptions(self) -> dict[str, Any]:
        return {
            "commission_bps": self.commission_bps,
            "half_spread_bps": self.half_spread_bps,
            "slippage_bps": self.slippage_bps,
            "rate_bps": self.commission_bps + self.half_spread_bps + self.slippage_bps,
            # Without this line the rate is unreconcilable. Costs are charged on
            # the ROUND-TRIP notional, sum|dw| * capital: replacing a 100%-gross
            # book end to end trades 200% of capital, not 100%. Reported turnover
            # is the one-way convention, sum|dw|/2, so
            #
            #     cost_return = 2 * turnover_one_way * rate_bps / 10_000
            #
            # and multiplying the reported turnover by the reported rate gives
            # exactly half the cost actually charged.
            "charged_on": "round-trip traded notional = sum|delta_w| * capital",
            "turnover_convention_in_reports": "one-way = sum|delta_w| / 2",
            "reconciliation": (
                "cost_return = turnover_round_trip * rate_bps / 10000 "
                "= 2 * turnover * rate_bps / 10000 (impact excluded, which is "
                "non-linear in traded notional)"
            ),
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


def waterfall(
    gross_return: float,
    breakdown: CostBreakdown,
    *,
    capital: float,
) -> CostWaterfall:
    """Peel cost layers off a gross return, one at a time.

    Order is commission, spread, slippage, impact — cheapest and most certain
    first, most model-dependent last, so a reader can stop at whichever layer
    they are willing to believe.
    """
    if capital <= 0:
        return CostWaterfall(gross_return, gross_return, gross_return, gross_return, gross_return)
    commission = breakdown.commission / capital
    spread = breakdown.spread / capital
    slippage = breakdown.slippage / capital
    impact = breakdown.impact / capital

    after_commission = gross_return - commission
    after_spread = after_commission - spread
    after_slippage = after_spread - slippage
    return CostWaterfall(
        gross=gross_return,
        after_commission=after_commission,
        after_spread=after_spread,
        after_slippage=after_slippage,
        net=after_slippage - impact,
    )


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
