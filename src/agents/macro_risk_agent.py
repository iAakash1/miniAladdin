"""The regime, and this security's exposure to it.

Reuses the existing macro and risk infrastructure rather than recomputing it,
so the regime an agent describes is the regime the score was gated by.

The rule that governs this agent: **missing macro data stays missing.** An
unreadable FRED is not a calm market, an absent multiplier is not 1.0, and a
regime that could not be measured is not STABLE. Every one of those
substitutions has been made in this codebase before and each one turned an
outage into an economic reading.
"""

from __future__ import annotations

import math
from typing import Optional

from src.agents.base import BaseAgent
from src.agents.schemas import AgentResult, AgentStatus, Period

INSTANT = Period(basis="instant")


def _finite(value) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class MacroRiskAgent(BaseAgent):
    name = "macro"

    def gather(self, context) -> AgentResult:
        result = AgentResult(agent=self.name)
        stats = context.macro_stats or {}
        status = stats.get("status")
        multiplier = _finite(context.macro_multiplier)

        if multiplier is None:
            result.status = AgentStatus.PARTIAL
            result.missing.append("risk_multiplier")
            ev = self.record(
                provider="fred", capability="macro", field="regime_status",
                value=status or "UNAVAILABLE", unit=None, period=INSTANT,
                quality="unavailable",
            )
            result.evidence.append(ev)
            result.claims.append(self.claim(
                "The macro regime could not be measured, so no regime gate was "
                "applied to this signal.",
                [ev], claim_type="state",
            ))
            result.warnings.append("macro unavailable — gate not applied")
        else:
            ev = self.record(
                provider="fred", capability="macro", field="risk_multiplier",
                value=round(multiplier, 4), unit="ratio", period=INSTANT,
                regime_status=status,
            )
            result.evidence.append(ev)
            result.claims.append(self.claim(
                f"Macro regime is {status or 'unlabelled'} with a systemic risk "
                f"multiplier of {multiplier:.2f}.",
                [ev], claim_type="state", numeric_value=round(multiplier, 4), unit="ratio",
            ))

        for field, label, unit in (
            ("yield_spread", "10Y-2Y term spread", "percent"),
            ("inflation_rate", "CPI inflation", "percent"),
            ("fed_funds_rate", "Federal Funds rate", "percent"),
        ):
            raw = stats.get(field)
            if raw is None:
                result.missing.append(field)
                continue
            # Some of these arrive pre-formatted as "3.52%"; the number is
            # kept as the measurement and the string only as its rendering.
            numeric = _finite(str(raw).rstrip("%")) if isinstance(raw, str) else _finite(raw)
            ev = self.record(
                provider="fred", capability="macro", field=field,
                value=numeric, unit=unit, period=INSTANT, rendered=str(raw),
            )
            result.evidence.append(ev)
            if numeric is not None:
                result.claims.append(self.claim(
                    f"{label} is {numeric:.2f}%.",
                    [ev], numeric_value=numeric, unit=unit,
                ))

        card = context.scorecard
        if card is not None:
            risk = getattr(card, "risk_score", None)
            if risk is not None:
                ev = self.record(
                    provider="scoring-engine", capability="risk", field="risk_score",
                    value=risk, unit="count", period=INSTANT,
                )
                result.evidence.append(ev)
                result.claims.append(self.claim(
                    f"Model risk score is {risk} out of 100.",
                    [ev], numeric_value=float(risk), unit="count",
                ))
            for component in getattr(card, "risk_components", []) or []:
                value = _finite(getattr(component, "value", None))
                name = getattr(component, "name", None) or getattr(component, "component", None)
                if value is None or not name:
                    continue
                ev = self.record(
                    provider="scoring-engine", capability="risk",
                    field=f"risk_{name}", value=round(value, 6), unit="ratio",
                    period=INSTANT,
                )
                result.evidence.append(ev)
        else:
            result.missing.append("scorecard")

        if result.missing and result.status is AgentStatus.OK:
            result.status = AgentStatus.PARTIAL
        return result
