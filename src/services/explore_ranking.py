"""Cross-sectional ranking mathematics, kept separate from the data fetch.

Pure functions over already-gathered numbers. Split out from the service so
the arithmetic that decides what a reader sees first can be tested without a
provider, a cache or a clock — the ordering is the product claim here, and a
claim you can only observe through eight network calls is a claim nobody
checks.

Two rules shape everything below.

**Rank is not verdict.** `overall_rank` answers "among the securities this
system can currently score, which combination of signal, confidence, risk and
evidence is strongest". It never answers "is this a buy" — that is the
scorecard's verdict and it is carried through untouched.

**Unknown is not good.** Every ranking input is either a measurement or a
reason to be excluded. Nothing defaults to a neutral middle, because a
neutral default lets a security with no data outrank one with bad data.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

#: Component weights for `overall_rank`. They sum to 1.0 and every component
#: is normalised to 0-100 before weighting, so the result is 0-100 too.
#:
#: Signal dominates because it is the model's actual output; the other three
#: are qualifiers on how much that output can be relied on. They are not
#: re-derived factor families — the scorecard has already combined momentum,
#: value, quality, news and reversal, and adding them again here would count
#: the same evidence twice.
WEIGHT_SIGNAL = 0.55
WEIGHT_CONFIDENCE = 0.20
WEIGHT_INVERSE_RISK = 0.15
WEIGHT_COMPLETENESS = 0.10

#: Trend components. Attention and movement, deliberately containing nothing
#: about whether either is good news.
TREND_WEIGHTS: dict[str, float] = {
    "momentum_21d": 0.35,
    "momentum_5d": 0.25,
    "relative_volume": 0.20,
    "news_activity": 0.10,
    "high_52w_proximity": 0.10,
}


def percentile_rank(value: Optional[float], population: Sequence[float]) -> Optional[float]:
    """Where `value` sits in `population`, as 0-100.

    The midpoint convention: ties share the average of the ranks they span,
    so N identical values all score the same rather than being ordered by
    whatever the sort was stable on. A ranking that silently breaks ties by
    list position is a ranking that changes when the input file is re-sorted.

    None in, None out. A missing measurement has no percentile, and inventing
    one — 50, "average" — is precisely how an unmeasured security climbs past
    a measured one.
    """
    if value is None or not math.isfinite(value):
        return None
    clean = [v for v in population if v is not None and math.isfinite(v)]
    if not clean:
        return None
    if len(clean) == 1:
        return 50.0
    below = sum(1 for v in clean if v < value)
    equal = sum(1 for v in clean if v == value)
    return round(100.0 * (below + 0.5 * equal) / len(clean), 2)


def overall_rank(
    *,
    signal_percentile: Optional[float],
    confidence: Optional[float],
    risk_score: Optional[float],
    data_completeness_pct: Optional[float],
) -> Optional[float]:
    """The composite 0-100 ordering score, or None when any input is missing.

    Strict rather than tolerant: a security missing one of the four is not
    ranked at all. Substituting a default for the missing term would let an
    absence of evidence behave like evidence, and the eligibility policy has
    already refused anything that cannot supply all four.
    """
    parts = (signal_percentile, confidence, risk_score, data_completeness_pct)
    if any(p is None or not math.isfinite(p) for p in parts):
        return None
    return round(
        WEIGHT_SIGNAL * float(signal_percentile)
        + WEIGHT_CONFIDENCE * float(confidence)
        + WEIGHT_INVERSE_RISK * (100.0 - float(risk_score))
        + WEIGHT_COMPLETENESS * float(data_completeness_pct),
        3,
    )


def trend_score(components: dict[str, Optional[float]]) -> Optional[float]:
    """Attention and movement, 0-100, over whichever components exist.

    **This is not a recommendation and must never be rendered as one.** A
    security collapsing on heavy volume and heavy coverage scores highly here
    and may carry a SELL verdict at the same time; both are true, and the
    interface has to show them together.

    Missing components are dropped and the surviving weights renormalised,
    rather than being filled with a neutral value. Renormalising says "scored
    on what we have"; filling says "we measured this and it was average".
    Returns None when nothing measurable survives.
    """
    present = {
        name: value
        for name, value in components.items()
        if name in TREND_WEIGHTS and value is not None and math.isfinite(value)
    }
    if not present:
        return None
    total_weight = sum(TREND_WEIGHTS[name] for name in present)
    if total_weight <= 0:
        return None
    score = sum(TREND_WEIGHTS[name] * float(value) for name, value in present.items())
    return round(score / total_weight, 3)


def trend_direction(momentum_21d: Optional[float], momentum_5d: Optional[float]) -> str:
    """Which way the attention is pointing.

    Reported beside the trend score because the score itself is unsigned: a
    reader who sees only "trending" cannot tell a rally from a collapse, and
    those are not the same fact.
    """
    readings = [m for m in (momentum_21d, momentum_5d) if m is not None and math.isfinite(m)]
    if not readings:
        return "high_attention"
    average = sum(readings) / len(readings)
    if average > 0.02:
        return "trending_up"
    if average < -0.02:
        return "trending_down"
    return "high_attention"


def risk_level(risk_score: Optional[float]) -> Optional[str]:
    """LOW / MEDIUM / HIGH from the production 0-100 risk score.

    None stays None. "Unknown risk" is not "low risk", and a security whose
    risk could not be computed must never be presented as the safe option.
    """
    if risk_score is None or not math.isfinite(risk_score):
        return None
    if risk_score < 34:
        return "LOW"
    if risk_score < 67:
        return "MEDIUM"
    return "HIGH"


def signal_strength(raw_score: Optional[float]) -> Optional[float]:
    """The scorecard's own score, reported as given.

    `raw_score` is a weighted sum of tanh-squashed family scores over weights
    that renormalise to 1, so it is bounded [-1, 1] — not 0-100, and not a
    percentage. It is passed through rather than rescaled here so that the
    number in an API response is the number the engine computed; the 0-100
    conversion happens once, in `percentile_rank`, and cross-sectionally.
    """
    if raw_score is None or not math.isfinite(raw_score):
        return None
    return round(float(raw_score), 4)
