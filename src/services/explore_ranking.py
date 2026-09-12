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


# ── risk-adjusted historical performance ─────────────────────────────────────
#
# A separate metric from `overall_rank`, and separate on purpose. Rank answers
# "what does the model think now"; this answers "how has this actually done,
# adjusted for what it put a holder through". They disagree often, and the
# product is more honest for showing both.
#
# It must never rewrite a verdict. Strong performance beside a HOLD is a real
# and common state — a security can have compounded beautifully and still be
# unattractive at today's price — and collapsing the two would turn the
# product into a momentum chaser wearing a model's name.

#: Component weights. Returns dominate, but never raw returns: every one is
#: measured against the benchmark, so a security that rose 20% while the market
#: rose 25% is not credited with the market's move.
#:
#: Risk-adjusted terms carry 35% between them, which is what stops a name that
#: returned +40% through a -35% drawdown from outranking one that returned +27%
#: through -8%. Ranking on return alone would call the first one better, and it
#: is not obviously better — it is a different instrument.
#: **The twelve-month term is deliberately absent.** Measured across the live
#: universe it was available for 0 of 43 eligible securities: the Explore sweep
#: fetches a one-year frame, which is a handful of sessions short of the 252 a
#: twelve-month window needs. `performance_score` would have renormalised
#: around it silently and produced correct numbers under a formula that named a
#: component never contributing to them — so it is declared out rather than
#: carried as decoration.
#:
#: `excess_return` still accepts that window, and the weight can be restored
#: the moment the sweep carries enough history. Fetching two years purely for
#: this term was rejected: the scorecard is computed from the same frame, and
#: lengthening it would move every factor in the production model to improve
#: one discovery metric.
PERFORMANCE_WEIGHTS: dict[str, float] = {
    "excess_3m": 0.30,
    "excess_6m": 0.30,
    "sharpe": 0.175,
    "sortino": 0.1125,
    "inverse_drawdown": 0.1125,
}

#: Sessions per window. Approximate trading days, not calendar days.
PERFORMANCE_WINDOWS: dict[str, int] = {"excess_3m": 63, "excess_6m": 126, "excess_12m": 252}

TRADING_DAYS = 252


def excess_return(frame, benchmark, days: int) -> Optional[float]:
    """A security's return over the window, minus the benchmark's.

    None when either side is unavailable. A security's own return is not
    substituted for the excess: +20% in a +25% market and +20% in a +2% market
    are different facts, and reporting the first as though it were the second
    is the mistake this function exists to prevent.
    """
    own = _window_return(frame, days)
    market = _window_return(benchmark, days)
    if own is None or market is None:
        return None
    value = own - market
    return value if math.isfinite(value) else None


def _window_return(frame, days: int) -> Optional[float]:
    if frame is None:
        return None
    try:
        closes = frame["Close"]
    except (TypeError, KeyError):
        return None
    if len(closes) <= days:
        return None
    try:
        base, last = float(closes.iloc[-1 - days]), float(closes.iloc[-1])
    except (TypeError, ValueError, IndexError):
        return None
    if not math.isfinite(base) or not math.isfinite(last) or base == 0:
        return None
    value = last / base - 1.0
    return value if math.isfinite(value) else None


def sharpe(frame, days: int = TRADING_DAYS) -> Optional[float]:
    """Annualised excess-of-zero Sharpe over the trailing window.

    No risk-free rate is subtracted, and the name says Sharpe anyway because
    that is what the rest of this codebase already reports; the omission is
    documented rather than hidden, and it is constant across the universe so
    the cross-sectional ranking is unaffected by it.
    """
    daily = _daily(frame, days)
    if daily is None:
        return None
    sigma = float(daily.std())
    if not math.isfinite(sigma) or sigma <= 0:
        return None
    value = (float(daily.mean()) * TRADING_DAYS) / (sigma * math.sqrt(TRADING_DAYS))
    return value if math.isfinite(value) else None


def sortino(frame, days: int = TRADING_DAYS) -> Optional[float]:
    """Sharpe's downside-only counterpart, annualised on the same convention.

    Returns None rather than infinity when nothing fell: a security with no
    down days has undefined downside deviation, and an infinite Sortino would
    sort straight to the top of a leaderboard on the strength of a division
    by zero.
    """
    daily = _daily(frame, days)
    if daily is None:
        return None
    downside = daily[daily < 0]
    if len(downside) < 2:
        return None
    sigma = float(downside.std())
    if not math.isfinite(sigma) or sigma <= 0:
        return None
    value = (float(daily.mean()) * TRADING_DAYS) / (sigma * math.sqrt(TRADING_DAYS))
    return value if math.isfinite(value) else None


def max_drawdown(frame, days: int = TRADING_DAYS) -> Optional[float]:
    """Deepest peak-to-trough decline over the window, as a negative fraction."""
    if frame is None:
        return None
    try:
        closes = frame["Close"].iloc[-days:]
    except (TypeError, KeyError):
        return None
    if len(closes) < 2:
        return None
    peak = closes.cummax()
    try:
        value = float(((closes - peak) / peak).min())
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) else None


def _daily(frame, days: int):
    if frame is None:
        return None
    try:
        closes = frame["Close"].iloc[-days:]
    except (TypeError, KeyError):
        return None
    daily = closes.pct_change().dropna()
    return daily if len(daily) >= 40 else None


def performance_score(components: dict[str, Optional[float]]) -> Optional[float]:
    """0-100 from whichever components are present.

    Each component arrives already converted to a cross-sectional percentile,
    so the weights combine like-for-like. Missing components are dropped and
    the surviving weights renormalised — the same rule `trend_score` follows,
    and for the same reason: renormalising says "scored on what we have",
    filling a neutral value says "we measured this and it was average".

    None when nothing measurable survives, which keeps a security with no
    history out of a performance leaderboard rather than at the middle of it.
    """
    present = {
        name: value
        for name, value in components.items()
        if name in PERFORMANCE_WEIGHTS and value is not None and math.isfinite(value)
    }
    if not present:
        return None
    total = sum(PERFORMANCE_WEIGHTS[name] for name in present)
    if total <= 0:
        return None
    score = sum(PERFORMANCE_WEIGHTS[name] * float(value) for name, value in present.items())
    return round(score / total, 3)


#: Grade bands over the cross-sectional score. Percentile-based rather than
#: fixed return thresholds: "+30% is an A" would grade the market, not the
#: security, and would mean something different every year.
PERFORMANCE_GRADES: tuple[tuple[float, str], ...] = (
    (80.0, "Exceptional"),
    (60.0, "Strong"),
    (40.0, "Moderate"),
    (0.0, "Weak"),
)


def performance_grade(score: Optional[float]) -> Optional[str]:
    """A word for the score, or None — never a default grade.

    An ungraded security is one we could not measure, and "Weak" would be a
    claim we have not earned.
    """
    if score is None or not math.isfinite(score):
        return None
    for threshold, label in PERFORMANCE_GRADES:
        if score >= threshold:
            return label
    return "Weak"
