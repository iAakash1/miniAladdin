"""High Conviction — when several independent things agree at once.

Not a stronger buy. The authoritative signal is the scoring engine's and this
does not touch it; conviction asks a different question — whether the *evidence
around* a positive signal is unusually well aligned. A security can carry a Buy
on thin evidence, high risk and no performance history behind it, and that is a
materially different proposition from a Buy where all four agree.

**Thresholds are measured, not chosen.** The obvious sketch for this feature —
"rank ≥ 80, confidence ≥ 75, data quality ≥ 75" — qualifies nobody in this
system. Measured across a live universe of 43 eligible securities, confidence
ran 29 to 51 with a median of 44: the engine starts every reading at 100 and
decays it multiplicatively through eight factors, so 75 is not a high bar, it
is an unreachable one. A gate nobody passes is not a strict gate, it is a
broken feature that looks strict.

So every threshold below is anchored to an observed percentile of the live
distribution, recorded with the measurement that set it, and versioned so a
later recalibration is visible rather than silent.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

#: Bumped whenever a threshold moves. A run that qualified under one policy and
#: not under the next is a policy change, not a market change, and the version
#: is how a reader tells those apart.
CONVICTION_POLICY_VERSION = "conviction-v1"


class Thresholds(BaseModel):
    """Each bound, with the observation that set it."""

    #: p75 of overall_rank was 68.2 and p90 was 74.6. 70 sits between them:
    #: comfortably in the top quartile without requiring the single best name.
    min_overall_rank: float = 70.0

    #: Median confidence was 44, p75 was 48, and the maximum observed was 51.
    #: 42 is just below the median — deliberately not a high bar, because on
    #: this engine's scale there is no such thing.
    min_confidence: int = 42

    #: 67 is where the product's own risk banding turns HIGH. Conviction does
    #: not require low risk; it requires that risk is not the highest band.
    max_risk_score: int = 67

    #: Observed completeness was 1.0 across every eligible security, so this
    #: bites only on a degraded run rather than in normal operation.
    min_data_completeness: float = 0.90

    #: Median performance was 55. Requiring the median is a confirmation that
    #: the market has not been pricing this against the model, not a demand
    #: for a top performer.
    min_performance_score: float = 50.0


DEFAULT_THRESHOLDS = Thresholds()


class Conviction(BaseModel):
    qualifies: bool
    policy_version: str = CONVICTION_POLICY_VERSION
    #: Which conditions were met, in the reader's language.
    met: list[str] = Field(default_factory=list)
    #: Which were not. Populated even when the security qualifies, so the
    #: interface can explain what a near miss was missing.
    blocked_by: list[str] = Field(default_factory=list)


def _is_positive(signal: Optional[str]) -> bool:
    return "buy" in (signal or "").lower()


def assess(
    *,
    model_signal: Optional[str],
    overall_rank: Optional[float],
    confidence: Optional[int],
    risk_score: Optional[int],
    data_completeness: Optional[float],
    performance_score: Optional[float],
    validation_state: Optional[str] = None,
    price_stale: bool = False,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Conviction:
    """Every condition, with what passed and what did not.

    Missing values block rather than pass. A security whose risk could not be
    measured has not demonstrated acceptable risk, and a conviction tier that
    treated silence as agreement would hand its strongest label to the names
    it understands least.
    """
    met: list[str] = []
    blocked: list[str] = []

    if _is_positive(model_signal):
        met.append(f"the model signal is {model_signal}")
    else:
        blocked.append(
            f"the model signal is {model_signal or 'unavailable'}, not a buy"
        )

    def gate(ok: Optional[bool], passed: str, failed: str) -> None:
        (met if ok else blocked).append(passed if ok else failed)

    gate(
        overall_rank is not None and overall_rank >= thresholds.min_overall_rank,
        f"it ranks {overall_rank:.0f} of 100 overall" if overall_rank is not None else "",
        f"its overall rank of {overall_rank:.0f} is below {thresholds.min_overall_rank:.0f}"
        if overall_rank is not None else "no overall rank could be computed",
    )
    gate(
        confidence is not None and confidence >= thresholds.min_confidence,
        f"analysis confidence is {confidence}" if confidence is not None else "",
        f"analysis confidence of {confidence} is below {thresholds.min_confidence}"
        if confidence is not None else "analysis confidence is unavailable",
    )
    gate(
        risk_score is not None and risk_score < thresholds.max_risk_score,
        f"risk is {risk_score}, below the high band" if risk_score is not None else "",
        f"risk of {risk_score} is in the high band" if risk_score is not None
        else "risk could not be measured, which is not the same as it being low",
    )
    gate(
        data_completeness is not None and data_completeness >= thresholds.min_data_completeness,
        f"{data_completeness * 100:.0f}% of the model's factors had their data"
        if data_completeness is not None else "",
        f"only {data_completeness * 100:.0f}% of factors had their data"
        if data_completeness is not None else "data coverage is unknown",
    )
    gate(
        performance_score is not None and performance_score >= thresholds.min_performance_score,
        f"risk-adjusted history scores {performance_score:.0f}"
        if performance_score is not None else "",
        f"risk-adjusted history scores {performance_score:.0f}, below "
        f"{thresholds.min_performance_score:.0f}" if performance_score is not None
        else "there is not enough history to score performance",
    )
    gate(
        validation_state not in ("CONFLICTED", "UNSUPPORTED"),
        "no evidence conflict was found",
        f"evidence validation returned {validation_state}",
    )
    gate(
        not price_stale,
        "the price is current",
        "the price is stale, so today's ranking rests on an old quote",
    )

    return Conviction(
        qualifies=not blocked,
        met=[m for m in met if m],
        blocked_by=[b for b in blocked if b],
    )
