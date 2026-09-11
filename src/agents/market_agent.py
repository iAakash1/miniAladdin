"""Price, volume and how current they are.

Deterministic throughout. Every number here is arithmetic over a price frame
the orchestrator already fetched, and routing arithmetic through a language
model would turn a checkable figure into an unverifiable one.
"""

from __future__ import annotations

import math
from typing import Optional

from src.agents.base import BaseAgent
from src.agents.schemas import AgentResult, AgentStatus, Period


def _finite(value) -> Optional[float]:
    """None unless this is a real number.

    NaN and infinity both arrive from real arithmetic — a zero denominator,
    an empty window — and both would otherwise travel as measurements.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _window_return(frame, days: int) -> Optional[float]:
    closes = frame["Close"]
    if len(closes) <= days:
        return None
    base = _finite(closes.iloc[-1 - days])
    last = _finite(closes.iloc[-1])
    if base is None or last is None or base == 0:
        return None
    return _finite(last / base - 1.0)


class MarketAgent(BaseAgent):
    name = "market"

    def gather(self, context) -> AgentResult:
        result = AgentResult(agent=self.name)
        frame = context.price_frame
        if frame is None or len(frame) < 2:
            result.status = AgentStatus.UNAVAILABLE
            result.missing = ["price_series"]
            return result

        series = context.series_result
        source = getattr(series, "source", "unknown") or "unknown"
        stale = bool(getattr(series, "stale", False))
        observed = None
        data = getattr(series, "data", None)
        if data is not None and getattr(data, "bars", None):
            observed = data.bars[-1].date

        price = _finite(frame["Close"].iloc[-1])
        if price is None:
            result.status = AgentStatus.UNAVAILABLE
            result.missing = ["last_close"]
            return result

        price_ev = self.record(
            provider=source, capability="price_series", field="last_close",
            value=round(price, 4), unit="usd", currency="USD",
            period=Period(basis="instant", end=observed), observed_at=observed,
            stale=stale, quality="stale" if stale else "live",
            bars=len(frame),
        )
        result.evidence.append(price_ev)
        result.claims.append(self.claim(
            f"Last close {price:.2f} USD on {observed or 'an unrecorded session'}.",
            [price_ev], numeric_value=round(price, 4), unit="usd",
            period=Period(basis="instant", end=observed), as_of=observed,
        ))

        for label, days in (("5-session", 5), ("21-session", 21), ("252-session", 252)):
            value = _window_return(frame, days)
            if value is None:
                result.missing.append(f"return_{days}d")
                continue
            ev = self.record(
                provider=source, capability="price_series", field=f"return_{days}d",
                value=round(value, 6), unit="fraction",
                period=Period(basis="window", end=observed, label=f"{days} sessions"),
                observed_at=observed, stale=stale,
            )
            result.evidence.append(ev)
            result.claims.append(self.claim(
                f"{label} price return {value * 100:.2f}%.",
                [ev], numeric_value=round(value, 6), unit="fraction",
                period=Period(basis="window", label=f"{days} sessions"), as_of=observed,
            ))

        volume = frame.get("Volume")
        if volume is not None and len(volume) >= 30:
            recent = _finite(volume.iloc[-5:].mean())
            baseline = _finite(volume.iloc[-60:].mean() if len(volume) >= 60 else volume.mean())
            if recent is not None and baseline is not None and baseline > 0:
                ratio = _finite(recent / baseline)
                if ratio is not None:
                    ev = self.record(
                        provider=source, capability="price_series", field="relative_volume",
                        value=round(ratio, 4), unit="ratio",
                        period=Period(basis="window", label="5 vs 60 sessions"),
                        observed_at=observed, stale=stale,
                    )
                    result.evidence.append(ev)
                    result.claims.append(self.claim(
                        f"Recent volume is {ratio:.2f}x its 60-session average.",
                        [ev], numeric_value=round(ratio, 4), unit="ratio", as_of=observed,
                    ))
            else:
                result.missing.append("relative_volume")

        # Disagreement between vendors is a fact about our confidence, so it
        # is recorded as evidence rather than resolved silently.
        confidence = getattr(series, "confidence", None)
        if getattr(series, "disagreement", False):
            ev = self.record(
                provider=source, capability="price_series", field="source_disagreement",
                value=True, unit=None, observed_at=observed,
                consulted=list(getattr(series, "sources_consulted", []) or []),
            )
            result.evidence.append(ev)
            result.claims.append(self.claim(
                "Price sources disagree materially on this security.",
                [ev], claim_type="state", as_of=observed,
            ))
            result.warnings.append("price sources disagree")

        if stale:
            result.warnings.append("price series served from stale cache")
        if confidence is not None and confidence < 0.8:
            result.warnings.append(f"price confidence {confidence:.2f}")
        if result.missing:
            result.status = AgentStatus.PARTIAL
        return result
