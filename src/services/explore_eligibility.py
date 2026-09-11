"""Whether a security may be ranked at all.

One policy, in one place, returning explicit reasons. It lives outside the
rendering code on purpose: a gate buried in a component is a gate that gets
copied, diverges, and eventually lets a security onto a "top ideas" list
because one of the two copies forgot to check freshness.

The governing rule is that **an absence must never help**. Every gate below
is written so that missing information excludes a security rather than
letting it through on a default. The failure this prevents is specific: a
name with 30% data completeness has few factors, few factors mean little
disagreement, little disagreement means high confidence and low measured
risk — so on a naive ranking the security we know least about sorts to the
top and gets shown first.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

#: A scorecard needs history; the engine itself refuses below 60 bars. Asked
#: for here as well so the exclusion is reported as a reason rather than
#: surfacing as a bare "no scorecard".
MIN_BARS = 60

#: Below this the factor set is too thin to compare cross-sectionally. It is
#: not a statement about the company — it is a statement about how much of
#: our model actually ran for it.
MIN_DATA_COMPLETENESS = 0.55

#: Confidence already folds in dispersion, freshness and conflict. A reading
#: beneath this means the engine itself is unsure, and promoting an unsure
#: reading to a ranked list overstates it.
#:
#: Calibrated against the engine rather than guessed. `confidence` starts at
#: 100 and is reduced multiplicatively by eight separate factors before being
#: clipped to [5, 95], so healthy readings are nowhere near 100. Measured over
#: twelve well-covered large caps the band was 33-48 (median 44, all at full
#: data completeness), which is what a *good* reading looks like here.
#:
#: An earlier draft used 35 and excluded a mega-cap sitting at 33 — a gate
#: that fires on the ordinary bottom of the healthy band is excluding noise,
#: not uncertainty. 25 sits clearly below that band and comfortably above the
#: floor of 5, so it catches genuinely unsure readings without quietly
#: deleting half the universe.
MIN_CONFIDENCE = 25

#: A price older than this is a different claim from a current one. Ranking
#: is cross-sectional, so one stale member distorts every other member's
#: percentile, not just its own row.
MAX_PRICE_AGE_DAYS = 7.0


class Eligibility(BaseModel):
    eligible: bool
    #: Machine-readable reasons, all of them — a security can fail several
    #: gates and reporting only the first makes the fix look smaller.
    reasons: list[str] = []


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
) -> Eligibility:
    """Apply every gate and return all failures.

    `data_completeness` is the scorecard's own 0-1 fraction, not a
    percentage; `confidence` and any risk score are 0-100. Mixing those
    scales is the obvious way to write a gate that never fires, so the units
    are named here rather than assumed.
    """
    reasons: list[str] = []

    if asset_type and asset_type != "common_equity":
        reasons.append("not_common_equity")

    if bars is None or bars < MIN_BARS:
        reasons.append("insufficient_history")

    if price is None or not (price > 0):
        reasons.append("no_valid_price")

    # `is None` rather than truthiness: an age of exactly 0.0 days is the
    # freshest possible reading, and the most common one during market hours.
    if price_age_days is None or price_age_days > MAX_PRICE_AGE_DAYS:
        reasons.append("price_stale")

    if not has_scorecard:
        reasons.append("no_scorecard")

    if data_completeness is None or data_completeness < MIN_DATA_COMPLETENESS:
        reasons.append("insufficient_data_completeness")

    if confidence is None or confidence < MIN_CONFIDENCE:
        reasons.append("low_confidence")

    if validation_state in ("CONFLICTED", "UNSUPPORTED"):
        reasons.append("unresolved_evidence_conflict")

    return Eligibility(eligible=not reasons, reasons=reasons)
