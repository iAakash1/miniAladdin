"""Whether this analysis is trustworthy enough to act on — not whether it is
good news.

Every other status in this product answers "what does the evidence say".
This one answers a different, harder question: "how much should the reader
trust that the evidence says enough". A security can carry a confident BUY
built from thin, stale, conflicted evidence, and nothing about the verdict
itself signals that — a verdict is a conclusion, not a self-assessment of how
sound the inputs were.

**This is not a probability of profit and must never be presented as one.**
STRONG decision quality means the evidence is complete, fresh and internally
consistent. It says nothing about whether the security will go up.

## Reuses the eligibility gate, does not duplicate it

`INSUFFICIENT` is exactly `not explore_eligibility.assess(...).eligible`, with
the same reasons — the same bar that excludes a security from Top Ranked
Ideas is the bar below which this module refuses to grade the evidence at
all. A second, slightly different threshold here would let a security read
"WEAK" in one place and "excluded" in another for the same underlying reason,
which is a worse outcome than either the ranking or this module refusing.

Above that floor, STRONG / ACCEPTABLE / WEAK are graduated by how far the
same inputs sit above their eligibility minimums — not a new set of
thresholds invented for this module, but a reading of distance from the ones
that already govern the ranking.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.services import explore_eligibility

DECISION_QUALITY_VERSION = "decision-quality-v1"


class DecisionQuality(BaseModel):
    grade: str  # "STRONG" | "ACCEPTABLE" | "WEAK" | "INSUFFICIENT"
    version: str = DECISION_QUALITY_VERSION
    #: Present only for INSUFFICIENT — the same machine-readable reasons
    #: explore_eligibility produces, so a UI never has to reconcile two
    #: vocabularies for the same failure.
    reasons: list[str] = Field(default_factory=list)
    #: One sentence, for the reader. Never implies a probability of profit.
    summary: str


def _grade_above_floor(*, data_completeness: float, confidence: int) -> str:
    """Eligible, but how comfortably.

    Margins are read against the eligibility floor rather than against new
    numbers, so raising `MIN_CONFIDENCE` or `MIN_DATA_COMPLETENESS` moves
    these grades with it automatically instead of leaving them calibrated to
    a floor that already moved.

    Takes no `validation_state`: a CONFLICTED or UNSUPPORTED reading already
    fails `explore_eligibility.assess()` and returns INSUFFICIENT before this
    function is ever called, so a second check for the same two values here
    would be dead code — unreachable, and worth removing rather than leaving
    in a code path a reader would reasonably expect to run.
    """
    completeness_margin = data_completeness - explore_eligibility.MIN_DATA_COMPLETENESS
    confidence_margin = confidence - explore_eligibility.MIN_CONFIDENCE

    # STRONG: comfortably clear of both floors — full data coverage, and
    # confidence not just past the gate but past it by a real margin.
    if data_completeness >= 0.90 and confidence_margin >= 15:
        return "STRONG"
    # WEAK: eligible, but only barely — within a third of the completeness
    # gap to full coverage, or within a third of the confidence gate itself.
    span = 1.0 - explore_eligibility.MIN_DATA_COMPLETENESS
    if completeness_margin < span / 3 or confidence_margin < (explore_eligibility.MIN_CONFIDENCE / 3):
        return "WEAK"
    return "ACCEPTABLE"


def assess(
    *,
    asset_type: Optional[str],
    bars: Optional[int],
    price: Optional[float],
    price_age_days: Optional[float],
    has_scorecard: bool,
    data_completeness: Optional[float],
    confidence: Optional[int],
    validation_state: Optional[str] = None,
) -> DecisionQuality:
    """Same inputs as `explore_eligibility.assess` — this calls it first."""
    eligibility = explore_eligibility.assess(
        asset_type=asset_type, bars=bars, price=price, price_age_days=price_age_days,
        has_scorecard=has_scorecard, data_completeness=data_completeness,
        confidence=confidence, validation_state=validation_state,
    )
    if not eligibility.eligible:
        return DecisionQuality(
            grade="INSUFFICIENT",
            reasons=eligibility.reasons,
            summary=(
                "OmniSignal can score this company, but current evidence is "
                "incomplete. It is excluded from Top Ranked Ideas."
            ),
        )

    # Both are guaranteed non-None by eligibility having passed, but the
    # types stay Optional at the boundary — asserted rather than assumed.
    assert data_completeness is not None and confidence is not None
    grade = _grade_above_floor(data_completeness=data_completeness, confidence=confidence)
    summary = {
        "STRONG": "The evidence behind this analysis is complete, fresh and internally consistent.",
        "ACCEPTABLE": "The evidence behind this analysis clears OmniSignal's bar, without much margin to spare.",
        "WEAK": "The evidence behind this analysis is thin or only just past OmniSignal's minimum bar. Treat the conclusion cautiously.",
    }[grade]
    return DecisionQuality(grade=grade, summary=summary)
