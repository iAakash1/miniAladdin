"""
Confidence policy — the single place any confidence number is decided.

Before this module, confidence was set in five places: literal 1.0 in the
SEC vendor, 0.9 in Wikidata, 0.55 in Apify, a +0.05/0.99 corroboration
rule in the merge engine, and the authority bands in the research layer.
That is exactly the duplicated logic the architecture forbids, and it made
"why is this 0.8?" unanswerable.

Now every confidence value comes from `score()`, which returns both the
number AND its reasoning, so any figure in the product can be explained
down to the inputs that produced it.

Inputs it considers:
    provider reliability   how much a source class is trusted at baseline
    source authority       what the URL/document actually is
    corroboration          how many independent providers agree
    contradiction          providers that disagree
    freshness              temporal decay for time-sensitive claims

Everything is overridable by environment variable, so tuning the policy
never requires a code change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

# ── tunables ─────────────────────────────────────────────────────────────────
# Named constants with stated reasons — no magic numbers at call sites.

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


# Baseline reliability per provider class. The ordering encodes a real
# claim: a company's own filing is the primary record; an encyclopedic
# database is curated but secondary; web research is corroborating context.
PROVIDER_BASELINE: dict[str, float] = {
    "sec": _env_float("CONF_SEC", 1.0),
    "wikidata": _env_float("CONF_WIKIDATA", 0.90),
    "finnhub": _env_float("CONF_FINNHUB", 0.85),
    "exa": _env_float("CONF_EXA", 0.60),
    "tavily": _env_float("CONF_TAVILY", 0.55),
    "brave": _env_float("CONF_BRAVE", 0.52),
    "newsapi": _env_float("CONF_NEWSAPI", 0.50),
    "news": _env_float("CONF_NEWS", 0.50),
    "gnews": _env_float("CONF_GNEWS", 0.48),
    "apify": _env_float("CONF_APIFY", 0.45),
}
DEFAULT_BASELINE = _env_float("CONF_DEFAULT", 0.50)

CORROBORATION_STEP = _env_float("CONF_CORROBORATION_STEP", 0.05)
CONTRADICTION_PENALTY = _env_float("CONF_CONTRADICTION_PENALTY", 0.15)

# Ceilings. Web evidence must never rival the primary record, and nothing
# ever reaches certainty — the graph asserts what providers said, not truth.
WEB_CEILING = _env_float("CONF_WEB_CEILING", 0.80)
ABSOLUTE_CEILING = _env_float("CONF_ABSOLUTE_CEILING", 0.99)
FLOOR = _env_float("CONF_FLOOR", 0.05)

# Freshness: claims about fast-moving facts decay; structural facts don't.
FRESHNESS_HALFLIFE_DAYS = _env_float("CONF_FRESHNESS_HALFLIFE_DAYS", 540.0)
MAX_FRESHNESS_PENALTY = _env_float("CONF_MAX_FRESHNESS_PENALTY", 0.20)


@dataclass
class ConfidenceResult:
    """A confidence value that can explain itself."""
    value: float
    reasons: list[str] = field(default_factory=list)

    def explain(self) -> str:
        return "; ".join(self.reasons)


def _baseline(provider: str) -> tuple[float, str]:
    key = (provider or "").split(".")[0].split(",")[0].strip().lower()
    if key in PROVIDER_BASELINE:
        return PROVIDER_BASELINE[key], f"{key} baseline {PROVIDER_BASELINE[key]:.2f}"
    return DEFAULT_BASELINE, f"unknown provider baseline {DEFAULT_BASELINE:.2f}"


def _freshness_penalty(published: Optional[str]) -> tuple[float, Optional[str]]:
    """Linear decay toward MAX_FRESHNESS_PENALTY over the half-life.

    Deliberately gentle: a two-year-old Reuters article is still evidence,
    it is simply weaker evidence about the present than today's filing.
    """
    if not published:
        return 0.0, None
    try:
        stamp = datetime.fromisoformat(published.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return 0.0, None
    age_days = (date.today() - stamp).days
    if age_days <= 0:
        return 0.0, None
    ratio = min(1.0, age_days / FRESHNESS_HALFLIFE_DAYS)
    penalty = round(ratio * MAX_FRESHNESS_PENALTY, 3)
    if penalty < 0.01:
        return 0.0, None
    return penalty, f"−{penalty:.2f} for age ({age_days}d)"


def score(
    provider: str,
    *,
    source_authority: Optional[float] = None,
    corroborating_providers: int = 1,
    contradicting_providers: int = 0,
    published_at: Optional[str] = None,
    is_web_source: bool = False,
) -> ConfidenceResult:
    """The one function that decides a confidence number.

    `source_authority` (0..1), when supplied, is what the SOURCE itself is
    worth — a SEC filing found by a news provider is still a SEC filing.
    It takes precedence over the provider baseline, because the document
    matters more than who handed it to us.
    """
    reasons: list[str] = []

    base, base_reason = _baseline(provider)
    reasons.append(base_reason)

    if source_authority is not None:
        if source_authority > base:
            reasons.append(f"source authority {source_authority:.2f} outranks provider")
            base = source_authority
        else:
            # Blend: a weak source found by a strong provider is still weak.
            base = round((base + source_authority) / 2, 3)
            reasons.append(f"blended with source authority {source_authority:.2f}")

    if corroborating_providers > 1:
        boost = CORROBORATION_STEP * (corroborating_providers - 1)
        base += boost
        reasons.append(f"+{boost:.2f} from {corroborating_providers} independent providers")

    if contradicting_providers > 0:
        penalty = CONTRADICTION_PENALTY * contradicting_providers
        base -= penalty
        reasons.append(f"−{penalty:.2f} from {contradicting_providers} contradicting source(s)")

    penalty, freshness_reason = _freshness_penalty(published_at)
    if penalty:
        base -= penalty
        reasons.append(freshness_reason or "")

    ceiling = WEB_CEILING if is_web_source else ABSOLUTE_CEILING
    if base > ceiling:
        reasons.append(f"capped at {ceiling:.2f}" + (" (web evidence)" if is_web_source else ""))
        base = ceiling

    value = round(max(FLOOR, min(ceiling, base)), 3)
    return ConfidenceResult(value=value, reasons=[r for r in reasons if r])


def for_provider(provider: str) -> float:
    """Baseline only — for structural graph edges with no source document."""
    return score(provider).value
