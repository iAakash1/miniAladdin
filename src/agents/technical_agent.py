"""Trend, dispersion and drawdown.

Interpretation only. This agent describes the technical state of a security;
it does not score it and it does not conclude anything about what to do. The
factor values that *do* enter the score are computed by the scoring engine
from the same frame, so a reading here and a factor there cannot drift apart.
"""

from __future__ import annotations

import math
from typing import Optional

from src.agents.base import BaseAgent
from src.agents.schemas import AgentResult, AgentStatus, Period


def _finite(value) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class TechnicalAgent(BaseAgent):
    name = "technical"

    def gather(self, context) -> AgentResult:
        result = AgentResult(agent=self.name)
        frame = context.price_frame
        if frame is None or len(frame) < 40:
            result.status = AgentStatus.UNAVAILABLE
            result.missing = ["price_series"]
            return result

        provider = getattr(context.series_result, "source", "unknown") or "unknown"
        closes = frame["Close"]
        window = Period(basis="window", label=f"{len(frame)} sessions")

        daily = closes.pct_change().dropna()
        if len(daily) >= 40:
            sigma = _finite(daily.std())
            if sigma is not None and sigma > 0:
                annualised = _finite(sigma * math.sqrt(252))
                if annualised is not None:
                    ev = self.record(
                        provider=provider, capability="price_series",
                        field="realised_volatility", value=round(annualised, 6),
                        unit="fraction", period=window,
                    )
                    result.evidence.append(ev)
                    result.claims.append(self.claim(
                        f"Realised volatility is {annualised * 100:.1f}% annualised.",
                        [ev], numeric_value=round(annualised, 6), unit="fraction", period=window,
                    ))
            else:
                result.missing.append("realised_volatility")

        peak = closes.cummax()
        drawdown = _finite(((closes - peak) / peak).min())
        if drawdown is not None:
            ev = self.record(
                provider=provider, capability="price_series", field="max_drawdown",
                value=round(drawdown, 6), unit="fraction", period=window,
            )
            result.evidence.append(ev)
            result.claims.append(self.claim(
                f"Deepest peak-to-trough decline in the window is {drawdown * 100:.1f}%.",
                [ev], numeric_value=round(drawdown, 6), unit="fraction", period=window,
            ))
        else:
            result.missing.append("max_drawdown")

        recent = closes.iloc[-252:] if len(closes) >= 252 else closes
        high = _finite(recent.max())
        last = _finite(closes.iloc[-1])
        if high is not None and last is not None and high > 0:
            proximity = _finite(last / high)
            if proximity is not None:
                ev = self.record(
                    provider=provider, capability="price_series",
                    field="high_52w_proximity", value=round(proximity, 4),
                    unit="fraction", period=Period(basis="window", label="52 weeks"),
                )
                result.evidence.append(ev)
                result.claims.append(self.claim(
                    f"Trading at {proximity * 100:.1f}% of its 52-week high.",
                    [ev], numeric_value=round(proximity, 4), unit="fraction",
                ))
        else:
            result.missing.append("high_52w_proximity")

        benchmark = context.benchmark_frame
        if benchmark is not None and len(benchmark) > 21 and len(closes) > 21:
            own = _finite(closes.iloc[-1] / closes.iloc[-22] - 1.0)
            bench = _finite(benchmark["Close"].iloc[-1] / benchmark["Close"].iloc[-22] - 1.0)
            if own is not None and bench is not None:
                excess = _finite(own - bench)
                if excess is not None:
                    ev = self.record(
                        provider=provider, capability="price_series",
                        field="excess_return_21d", value=round(excess, 6),
                        unit="fraction", period=Period(basis="window", label="21 sessions"),
                        benchmark="SPY",
                    )
                    result.evidence.append(ev)
                    result.claims.append(self.claim(
                        f"Over 21 sessions it has {'out' if excess >= 0 else 'under'}performed "
                        f"the benchmark by {abs(excess) * 100:.1f} percentage points.",
                        [ev], claim_type="comparison", numeric_value=round(excess, 6),
                        unit="fraction",
                    ))
        else:
            result.missing.append("benchmark_comparison")

        if not result.evidence:
            result.status = AgentStatus.UNAVAILABLE
        elif result.missing:
            result.status = AgentStatus.PARTIAL
        return result
