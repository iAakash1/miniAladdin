"""
OmniSignal Decision Logic — single source of truth.

The verdict/confidence/rationale synthesis previously lived only in
AsyncDataPipeline._compute_verdict, so the HTTP API and the CLI report
pipeline could drift apart (the API returned no confidence at all).
Both paths now call these pure functions.

The logic is moved verbatim from data_pipeline.py, not rewritten.
"""

from __future__ import annotations

from typing import Optional

from src.models import (
    AggregateSentiment,
    RiskAssessment,
    SignalVerdict,
    TechnicalAnalysis,
)

SIGNAL_ORDER = [
    SignalVerdict.STRONG_SELL,
    SignalVerdict.SELL,
    SignalVerdict.HOLD,
    SignalVerdict.BUY,
    SignalVerdict.STRONG_BUY,
]

# Sentiment thresholds for verdict adjustment (unchanged from pipeline logic)
SENTIMENT_BOOST_THRESHOLD = 0.3
SENTIMENT_DAMPEN_THRESHOLD = -0.3

# Deterministic risk-level thresholds (documented in docs/AUDIT.md §3)
VOLATILITY_HIGH = 0.45
VOLATILITY_MEDIUM = 0.25
SRM_HIGH = 1.3
SRM_MEDIUM = 1.2
BETA_HIGH = 2.0
BETA_MEDIUM = 1.4
DRAWDOWN_HIGH = -0.35


def compute_decision(
    macro: RiskAssessment,
    technicals: TechnicalAnalysis,
    sentiment: AggregateSentiment,
) -> tuple[SignalVerdict, float, str]:
    """
    Synthesize (verdict, confidence, rationale) from the three factors.

    Moved verbatim from AsyncDataPipeline._compute_verdict so the API and
    the report pipeline share one implementation.
    """
    tech_signal = technicals.risk_adjusted_signal or SignalVerdict.HOLD
    idx = SIGNAL_ORDER.index(tech_signal)

    rationale_parts: list[str] = []

    # Sentiment adjustment
    if sentiment.headline_count > 0:
        if sentiment.average_score > SENTIMENT_BOOST_THRESHOLD:
            idx = min(len(SIGNAL_ORDER) - 1, idx + 1)
            rationale_parts.append(
                f"Positive sentiment (avg score {sentiment.average_score:.2f}) "
                f"boosted signal"
            )
        elif sentiment.average_score < SENTIMENT_DAMPEN_THRESHOLD:
            idx = max(0, idx - 1)
            rationale_parts.append(
                f"Negative sentiment (avg score {sentiment.average_score:.2f}) "
                f"dampened signal"
            )
        else:
            rationale_parts.append(
                f"Neutral sentiment (avg score {sentiment.average_score:.2f})"
            )
    else:
        rationale_parts.append("No sentiment data available")

    # Macro context
    if macro.recession_warning:
        rationale_parts.append("⚠️ Recession warning: yield curve is inverted")
    if macro.status.value == "CRITICAL":
        rationale_parts.append(f"Macro environment is CRITICAL (SRM={macro.risk_multiplier})")
    elif macro.status.value == "ELEVATED":
        rationale_parts.append(f"Macro environment is ELEVATED (SRM={macro.risk_multiplier})")
    else:
        rationale_parts.append(f"Macro environment is STABLE (SRM={macro.risk_multiplier})")

    verdict = SIGNAL_ORDER[idx]

    # Confidence = higher when all signals agree
    base_confidence = 0.5
    if tech_signal == verdict:
        base_confidence += 0.2
    if sentiment.headline_count >= 3:
        base_confidence += 0.1
    if macro.status.value == "STABLE":
        base_confidence += 0.1
    confidence = min(1.0, round(base_confidence, 2))

    rationale = "; ".join(rationale_parts)
    return verdict, confidence, rationale


def derive_risk_level(
    volatility: Optional[float],
    risk_multiplier: float,
    max_drawdown: Optional[float] = None,
    beta: Optional[float] = None,
) -> str:
    """
    Deterministic LOW / MEDIUM / HIGH classification from already-computed
    metrics. Used as a fact fed to (and enforced on) the LLM explanation
    layer — the model never invents a risk level.
    """
    if (
        (volatility is not None and volatility > VOLATILITY_HIGH)
        or risk_multiplier >= SRM_HIGH
        or (beta is not None and beta > BETA_HIGH)
        or (max_drawdown is not None and max_drawdown < DRAWDOWN_HIGH)
    ):
        return "HIGH"
    if (
        volatility is None  # unknown volatility should never read as calm
        or volatility > VOLATILITY_MEDIUM
        or risk_multiplier >= SRM_MEDIUM
        or (beta is not None and beta > BETA_MEDIUM)
    ):
        return "MEDIUM"
    return "LOW"


def confidence_breakdown(
    macro: RiskAssessment,
    technicals: TechnicalAnalysis,
    sentiment: AggregateSentiment,
    verdict: SignalVerdict,
) -> list[dict[str, object]]:
    """
    Itemized composition of the confidence score, mirroring compute_decision's
    formula exactly (points are percentage contributions; they sum to the
    confidence value). Consumed by the API response and by the LLM payload so
    the model can explain the confidence without inventing arithmetic.
    """
    items: list[dict[str, object]] = [
        {"component": "Base confidence", "points": 50},
    ]
    tech_signal = technicals.risk_adjusted_signal or SignalVerdict.HOLD
    if tech_signal == verdict:
        items.append({
            "component": "Technical signal agrees with the final verdict",
            "points": 20,
        })
    if sentiment.headline_count >= 3:
        items.append({
            "component": f"Sentiment sample is meaningful ({sentiment.headline_count} headlines)",
            "points": 10,
        })
    if macro.status.value == "STABLE":
        items.append({"component": "Stable macro regime", "points": 10})
    return items


def verdict_to_recommendation(verdict: SignalVerdict) -> str:
    """Map the five-step verdict onto the LLM contract's BUY / SELL / HOLD."""
    if verdict in (SignalVerdict.STRONG_BUY, SignalVerdict.BUY):
        return "BUY"
    if verdict in (SignalVerdict.STRONG_SELL, SignalVerdict.SELL):
        return "SELL"
    return "HOLD"
