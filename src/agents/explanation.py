"""A useful explanation with no model available.

Every language model in the stack is optional, and a product whose explanation
panel goes blank when a vendor rate-limits is a product that stops being usable
at the worst moment. So the deterministic summary is not a degraded mode that
exists on paper — it is the default, built from the authoritative numbers, and
the generated narrative is an improvement on top of it rather than a
replacement for it.

Everything here is a template over values the scoring engine already produced.
Nothing is computed, nothing is estimated, and no sentence can say anything the
factor rows do not support.
"""

from __future__ import annotations

import math
from typing import Any, Optional

#: Grammar for the three bands, so the prose reads naturally rather than
#: stitching "risk is MEDIUM" into every sentence.
_RISK_WORDS = {"LOW": "low", "MEDIUM": "moderate", "HIGH": "elevated"}


def _band(risk_score: Optional[int]) -> Optional[str]:
    if risk_score is None:
        return None
    if risk_score < 34:
        return "LOW"
    return "MEDIUM" if risk_score < 67 else "HIGH"


def _named(factors: Optional[list[Any]], positive: bool, limit: int = 2) -> list[str]:
    """The strongest contributors by name, from what the engine weighted."""
    rows = [
        f for f in (factors or [])
        if getattr(f, "score", None) is not None
        and getattr(f, "contribution", None) is not None
        and math.isfinite(f.contribution)
        and (f.contribution > 0 if positive else f.contribution < 0)
    ]
    rows.sort(key=lambda f: f.contribution, reverse=positive)
    return [str(f.name).replace("_", " ") for f in rows[:limit]]


def deterministic_summary(
    *,
    signal: Optional[str],
    confidence: Optional[int],
    risk_score: Optional[int],
    data_completeness: Optional[float],
    factors: Optional[list[Any]] = None,
    validation: Optional[Any] = None,
) -> dict[str, Any]:
    """The shape the Beginner surface renders, with no model involved.

    Absences are stated rather than filled. "The model could not produce a
    signal" is a useful sentence; a confident summary of a security that was
    never scored is not.
    """
    if not signal:
        return {
            "summary": (
                "OmniSignal could not produce a signal for this security. The "
                "evidence needed to score it was not available on this run."
            ),
            "why_positive": [],
            "why_cautious": [],
            "risk_explanation": (
                "Risk could not be measured, which is not the same as it being low."
            ),
            "what_could_change": ["The data the model needs becoming available."],
            "source": "deterministic",
        }

    supports = _named(factors, positive=True)
    against = _named(factors, positive=False)
    band = _band(risk_score)

    sentences = [f"OmniSignal currently produces a {signal.upper()} signal for this security."]
    if supports:
        sentences.append(
            f"The strongest support comes from {' and '.join(supports)}."
        )
    if against:
        sentences.append(
            f"The main concern is {against[0]}."
            if len(against) == 1 else
            f"The main concerns are {' and '.join(against)}."
        )
    if band:
        sentences.append(
            f"Risk is {_RISK_WORDS[band]}"
            + (f" at {risk_score} out of 100." if risk_score is not None else ".")
        )
    if confidence is not None:
        sentences.append(
            f"Analysis confidence is {confidence} out of 100, which describes how "
            "complete and consistent the evidence was rather than the chance of a gain."
        )
    if data_completeness is not None:
        sentences.append(
            f"{round(data_completeness * 100)}% of the factors the model can compute "
            "had the data they needed."
        )

    changes: list[str] = []
    for name in supports:
        changes.append(f"{name} weakening would remove support for this signal.")
    for name in against:
        changes.append(f"{name} deteriorating further would outweigh the support.")
    changes.append("A shift in the macro regime changes the gate applied to every signal.")

    summary = {
        "summary": " ".join(sentences),
        "why_positive": supports,
        "why_cautious": against,
        "risk_explanation": (
            f"Risk is {_RISK_WORDS[band]}."
            if band else
            "Risk could not be measured, which is not the same as it being low."
        ),
        "what_could_change": changes[:4],
        "source": "deterministic",
    }
    if validation is not None:
        summary["validation_status"] = getattr(
            getattr(validation, "status", None), "value", None,
        )
    return summary
