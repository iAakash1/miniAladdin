"""Why one security ranks above another, by arithmetic rather than by narrative.

`overall_rank` is a weighted sum of four terms, so the gap between two
securities decomposes **exactly** into four contributions that add back up to
it. That is the whole design: this module performs no estimation, consults no
model and makes no judgement. It re-states a subtraction the ranking already
did, in the order the terms mattered.

The alternative was a generated explanation of the difference, and it would
have been wrong in a way that is hard to see. A model asked why NVDA ranks
above AMD produces fluent, plausible reasons — business quality, market
position, the things a reader expects — none of which are in `overall_rank` at
all. The reader would come away believing the ranking considered something it
has never looked at.

**Rank is not verdict.** Ranking above is an ordering over one composite score;
it is not a claim that one security is the better holding, and this module's
output must never be presented as one. A security can rank above another and
carry the same HOLD.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.services.explore_ranking import (
    WEIGHT_COMPLETENESS, WEIGHT_CONFIDENCE, WEIGHT_INVERSE_RISK, WEIGHT_SIGNAL,
)

ATTRIBUTION_VERSION = "rank-attribution-v1"

#: Each term of `overall_rank`, with the weight it carries and how to read it.
#: `inverted` marks the one term where a lower raw number is the better one,
#: so the interface can say "lower risk" rather than printing a negative
#: difference and leaving the reader to work out the sign.
COMPONENTS: tuple[dict[str, Any], ...] = (
    {"key": "signal_percentile", "label": "Signal strength",
     "weight": WEIGHT_SIGNAL, "inverted": False,
     "reading": "where the model's signal sits against the rest of the universe"},
    {"key": "confidence", "label": "Confidence",
     "weight": WEIGHT_CONFIDENCE, "inverted": False,
     "reading": "how much agreement the evidence showed, not a probability of profit"},
    {"key": "risk_score", "label": "Risk",
     "weight": WEIGHT_INVERSE_RISK, "inverted": True,
     "reading": "measured risk, where lower contributes more, not a probability of loss"},
    {"key": "data_completeness_pct", "label": "Data completeness",
     "weight": WEIGHT_COMPLETENESS, "inverted": False,
     "reading": "how much of the evidence arrived, not how accurate it is"},
)


class Contribution(BaseModel):
    key: str
    label: str
    reading: str
    weight: float
    a_value: Optional[float] = None
    b_value: Optional[float] = None
    #: a − b on the raw measure, before weighting. For risk this is negative
    #: when A is the safer of the two, which is why `inverted` exists.
    difference: Optional[float] = None
    #: The weighted, sign-corrected amount this term added to A's lead.
    #: Positive favours A, negative favours B. These sum to `rank_gap`.
    contribution: float = 0.0
    #: Share of the total absolute movement, so a reader can see which term
    #: did the work. Not a share of the gap: terms can point opposite ways and
    #: a share of a near-zero gap would be meaningless or enormous.
    share: float = 0.0
    inverted: bool = False


class Attribution(BaseModel):
    version: str = ATTRIBUTION_VERSION
    a: str
    b: str
    a_rank: Optional[float] = None
    b_rank: Optional[float] = None
    #: A's rank minus B's. Negative means B leads.
    rank_gap: Optional[float] = None
    leader: Optional[str] = None
    level: bool = False
    contributions: list[Contribution] = Field(default_factory=list)
    #: Set when no attribution is possible, and why.
    unavailable_reason: Optional[str] = None
    #: Stated on every response. Ranking above is not a recommendation.
    caveat: str = (
        "This explains an ordering, not a recommendation. Ranking above is a "
        "position on one composite score; it is not a claim that one security "
        "is the better holding, and both can carry the same signal."
    )


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _measures(row: Any) -> dict[str, Optional[float]]:
    """The four raw inputs, read off a row in the ranking's own units.

    `data_completeness` is stored as a 0-1 fraction and enters the rank as a
    percentage. Reading it here rather than at each call site is the difference
    between one conversion and four chances to forget one.
    """
    completeness = _finite(getattr(row, "data_completeness", None))
    return {
        "signal_percentile": _finite(getattr(row, "signal_percentile", None)),
        "confidence": _finite(getattr(row, "confidence", None)),
        "risk_score": _finite(getattr(row, "risk_score", None)),
        "data_completeness_pct": None if completeness is None else completeness * 100.0,
    }


def attribute(row_a: Any, row_b: Any) -> Attribution:
    """Decompose the ranking gap between two securities.

    Returns an attribution with `unavailable_reason` set — rather than a
    partial one — when either security is unranked. A gap explained from three
    of four terms is not the gap, and presenting it as one would be the exact
    failure this module exists to avoid.
    """
    symbol_a = str(getattr(row_a, "symbol", "") or "").upper()
    symbol_b = str(getattr(row_b, "symbol", "") or "").upper()
    rank_a = _finite(getattr(row_a, "overall_rank", None))
    rank_b = _finite(getattr(row_b, "overall_rank", None))

    base = Attribution(a=symbol_a, b=symbol_b, a_rank=rank_a, b_rank=rank_b)

    if rank_a is None or rank_b is None:
        unranked = [s for s, r in ((symbol_a, rank_a), (symbol_b, rank_b)) if r is None]
        base.unavailable_reason = (
            f"{' and '.join(unranked)} {'is' if len(unranked) == 1 else 'are'} not ranked, "
            "so there is no gap to explain. A security is ranked only when all four "
            "inputs are present."
        )
        return base

    measures_a, measures_b = _measures(row_a), _measures(row_b)
    contributions: list[Contribution] = []

    for spec in COMPONENTS:
        key = str(spec["key"])
        a_value, b_value = measures_a[key], measures_b[key]
        if a_value is None or b_value is None:
            # Should not happen for two ranked securities — the rank requires
            # all four — but a ranked row missing an input would silently drop
            # a term and break the identity below, so it is refused loudly.
            base.unavailable_reason = (
                f"{key} is missing for one of the two despite both being ranked, "
                "so the gap cannot be decomposed."
            )
            return base

        difference = a_value - b_value
        weight = float(spec["weight"])
        # Risk enters the rank as (100 − risk), so its contribution is the
        # negated difference. The subtraction of the two constants cancels.
        contribution = weight * (-difference if spec["inverted"] else difference)
        contributions.append(Contribution(
            key=key, label=str(spec["label"]), reading=str(spec["reading"]),
            weight=weight, a_value=a_value, b_value=b_value,
            difference=difference, contribution=round(contribution, 4),
            inverted=bool(spec["inverted"]),
        ))

    movement = sum(abs(c.contribution) for c in contributions)
    for c in contributions:
        c.share = round(100.0 * abs(c.contribution) / movement, 1) if movement > 0 else 0.0

    # Largest mover first, so the answer to "why" is the first row.
    contributions.sort(key=lambda c: (-abs(c.contribution), c.key))

    gap = round(rank_a - rank_b, 3)
    base.rank_gap = gap
    base.contributions = contributions
    base.level = abs(gap) < 0.001
    base.leader = None if base.level else (symbol_a if gap > 0 else symbol_b)
    return base


def summary(attribution: Attribution) -> str:
    """One deterministic sentence. No model, and none of its vocabulary.

    Says only what the arithmetic says: who leads, by how much, and which term
    contributed most. It does not say why that term is high, because the
    ranking does not know.
    """
    if attribution.unavailable_reason:
        return attribution.unavailable_reason
    if attribution.level:
        return f"{attribution.a} and {attribution.b} rank level."

    leader = attribution.leader
    trailer = attribution.b if leader == attribution.a else attribution.a
    gap = abs(attribution.rank_gap or 0.0)
    top = attribution.contributions[0] if attribution.contributions else None
    if top is None:
        return f"{leader} ranks {gap:.1f} points above {trailer}."

    # The largest mover may favour the security that is behind overall, which
    # is worth saying plainly rather than implying it helped the leader.
    favours_leader = (top.contribution > 0) == (leader == attribution.a)
    if favours_leader:
        return (
            f"{leader} ranks {gap:.1f} points above {trailer}, and {top.label.lower()} "
            f"accounts for the largest part of that gap ({top.share:.0f}% of the movement)."
        )
    return (
        f"{leader} ranks {gap:.1f} points above {trailer} despite {top.label.lower()}, "
        f"which favours {trailer} and is the largest single term "
        f"({top.share:.0f}% of the movement)."
    )
