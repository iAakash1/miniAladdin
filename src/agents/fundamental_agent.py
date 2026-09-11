"""Valuation, profitability and quality — with their periods attached.

The discipline this agent exists to enforce is period hygiene. TTM revenue and
fiscal-year revenue are different measurements; a margin computed over a
trailing twelve months and one reported for a fiscal year are different
measurements. Comparing them produces a confident, wrong claim that nothing
downstream can detect, so every value here carries the basis it was measured
on and the validator refuses to compare across bases.
"""

from __future__ import annotations

import math
from typing import Optional

from src.agents.base import BaseAgent
from src.agents.schemas import AgentResult, AgentStatus, Period

TTM = Period(basis="ttm", label="trailing twelve months")
INSTANT = Period(basis="instant")

#: field -> (label, unit, period, how to phrase it)
_METRICS: list[tuple[str, str, str, Period]] = [
    ("pe_ratio", "Price/earnings", "ratio", TTM),
    ("forward_pe", "Forward price/earnings", "ratio", Period(basis="window", label="forward estimate")),
    ("price_to_book", "Price/book", "ratio", INSTANT),
    ("ev_to_ebitda", "EV/EBITDA", "ratio", TTM),
    ("gross_margin_ttm", "Gross margin", "percent", TTM),
    ("operating_margin_ttm", "Operating margin", "percent", TTM),
    ("net_margin_ttm", "Net margin", "percent", TTM),
    ("roe_ttm", "Return on equity", "percent", TTM),
    ("roa_ttm", "Return on assets", "percent", TTM),
    ("revenue_growth_ttm_yoy", "Revenue growth", "percent", TTM),
    ("eps_growth_ttm_yoy", "EPS growth", "percent", TTM),
    ("debt_to_equity", "Debt/equity", "ratio", INSTANT),
]


def _finite(value) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class FundamentalAgent(BaseAgent):
    name = "fundamental"

    def gather(self, context) -> AgentResult:
        result = AgentResult(agent=self.name)
        payload = context.fundamentals
        if payload is None:
            result.status = AgentStatus.UNAVAILABLE
            result.missing = ["fundamentals"]
            return result

        provider = getattr(payload, "_provider", None) or "fundamentals-chain"

        for field, label, unit, period in _METRICS:
            value = _finite(getattr(payload, field, None))
            if value is None:
                result.missing.append(field)
                continue
            ev = self.record(
                provider=provider, capability="fundamentals", field=field,
                value=round(value, 6), unit=unit, currency="USD",
                period=period,
            )
            result.evidence.append(ev)
            shown = f"{value:.2f}%" if unit == "percent" else f"{value:.2f}"
            result.claims.append(self.claim(
                f"{label} is {shown} ({period.label or period.basis}).",
                [ev], numeric_value=round(value, 6), unit=unit, period=period,
            ))

        # Analyst target, only where both sides of the comparison exist. An
        # upside computed against a price from a different day is a number
        # about two different worlds.
        targets = context.analyst_targets
        target = _finite(getattr(targets, "target_mean", None)) if targets is not None else None
        price = None
        frame = context.price_frame
        if frame is not None and len(frame):
            price = _finite(frame["Close"].iloc[-1])

        if target is not None and price is not None and price > 0:
            upside = _finite(target / price - 1.0)
            count = getattr(targets, "analyst_count", None)
            target_ev = self.record(
                provider=getattr(targets, "_provider", "analyst-chain"),
                capability="analyst_targets", field="target_mean",
                value=round(target, 4), unit="usd", currency="USD",
                period=Period(basis="window", label="forward estimate"),
                analyst_count=count,
            )
            result.evidence.append(target_ev)
            if upside is not None:
                result.claims.append(self.claim(
                    f"Mean analyst target implies {upside * 100:.1f}% "
                    f"{'upside' if upside >= 0 else 'downside'} from the last close"
                    + (f", from {count} analysts." if count else "."),
                    [target_ev],
                    claim_type="comparison", numeric_value=round(upside, 6), unit="fraction",
                ))
            if not count:
                result.warnings.append(
                    "analyst count unknown — one target is not a consensus"
                )
        else:
            result.missing.append("analyst_target")

        for key, label in (
            ("gross_profit_over_assets", "Gross profitability"),
            ("net_issuance_yoy", "Net share issuance"),
            ("asset_growth_yoy", "Asset growth"),
        ):
            value = _finite(context.quality_inputs.get(key))
            if value is None:
                result.missing.append(key)
                continue
            ev = self.record(
                provider=context.quality_inputs.get("source") or "fundamentals-chain",
                capability="quality", field=key, value=round(value, 6),
                unit="fraction", period=TTM,
            )
            result.evidence.append(ev)
            result.claims.append(self.claim(
                f"{label} is {value:.4f} (trailing twelve months).",
                [ev], numeric_value=round(value, 6), unit="fraction", period=TTM,
            ))

        if not result.evidence:
            result.status = AgentStatus.UNAVAILABLE
        elif result.missing:
            result.status = AgentStatus.PARTIAL
        return result
