"""
News evidence scoring — methodology layer (docs/QUANT-REVIEW.md §7).

Raw headlines in → weighted, clustered, categorized evidence out. The
sentiment factor then consumes EFFECTIVE evidence, not raw article count:

    n_eff = Σ_i  reliability_i · decay_i · novelty_i · confirmation_c(i)
    s_eff = Σ_i  w_i · s_i / Σ_i w_i

Every constant is named and literature-anchored:

  DECAY_HALF_LIFE_HOURS = 60
      News alpha is measured in days, not weeks (Chan 2003; Tetlock 2007);
      a 60h half-life leaves ~6% weight at one week — context, not signal.
  NOVELTY_* (Jaccard duplicate threshold 0.6, repeat weight 0.35)
      Stale, repeated news moves prices less and reverses more
      (Tetlock 2011). Repeats confirm rather than add: first article in a
      cluster keeps weight 1, repeats carry REPEAT_WEIGHT.
  CONFIRMATION_BONUS_PER_SOURCE = 0.2 (cap +0.5)
      Independent confirmation from distinct domains raises evidential
      value; capped so no cluster outweighs the shrinkage prior.
  Source reliability tiers
      Reused verbatim from the evidence pipeline (editorial standards).

Deterministic, pure, unit-tested. No model calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.services.evidence import reliability_of, recency_of

DECAY_HALF_LIFE_HOURS = 60.0
DUPLICATE_JACCARD = 0.6
REPEAT_WEIGHT = 0.35
CONFIRMATION_BONUS_PER_SOURCE = 0.2
CONFIRMATION_BONUS_CAP = 0.5

# Event taxonomy: transparent regex classes, reported per headline.
EVENT_TYPES: list[tuple[str, re.Pattern[str]]] = [
    ("earnings", re.compile(r"\b(earnings|eps|quarter(ly)? results|beats?|miss(es|ed)?|revenue)\b", re.I)),
    ("guidance", re.compile(r"\b(guidance|outlook|forecast|raises?|lowers?|cuts? (forecast|outlook))\b", re.I)),
    ("mna", re.compile(r"\b(merger|acquisition|acquires?|takeover|buyout|deal to buy)\b", re.I)),
    ("legal_regulatory", re.compile(r"\b(lawsuit|probe|investigation|antitrust|fine|settlement|regulator|sec charges)\b", re.I)),
    ("analyst_action", re.compile(r"\b(upgrades?|downgrades?|initiates?|price target|overweight|underweight)\b", re.I)),
    ("product", re.compile(r"\b(launch(es)?|unveils?|releases?|announces? new|patent)\b", re.I)),
    ("macro_passthrough", re.compile(r"\b(fed|rates?|inflation|tariff|cpi|jobs report|treasury)\b", re.I)),
]


@dataclass
class ScoredHeadline:
    title: str
    sentiment: float            # keyword score from SentimentAnalyzer, [-1, 1]
    source: str = ""
    url: str = ""
    published_at: str = ""
    event_type: str = "general"
    reliability: float = 0.5
    decay: float = 0.5
    novelty: float = 1.0        # 1 = first report; REPEAT_WEIGHT = duplicate
    confirmation: float = 1.0   # cluster-level multiplier
    cluster_id: int = 0
    weight: float = field(default=0.0)  # final: reliability·decay·novelty·confirmation


@dataclass
class NewsEvidence:
    headlines: list[ScoredHeadline]
    n_raw: int
    n_eff: float                # effective evidence count (Σ weights)
    s_eff: Optional[float]      # weight-averaged sentiment
    clusters: int
    note: str = (
        "n_eff = Σ reliability·decay·novelty·confirmation per headline; "
        "sentiment shrinkage uses n_eff, so stale or repeated stories "
        "cannot inflate confidence."
    )


_WORD = re.compile(r"[a-z0-9]+")


def _tokens(title: str) -> set[str]:
    return set(_WORD.findall(title.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def classify_event(title: str) -> str:
    for name, pattern in EVENT_TYPES:
        if pattern.search(title):
            return name
    return "general"


def score_headlines(
    rows: list[dict],
    now: Optional[datetime] = None,
) -> NewsEvidence:
    """
    rows: [{title, score, source, url, published_at}] — the analyzer's output.
    Deterministic given (rows, now).
    """
    now = now or datetime.now(timezone.utc)
    scored: list[ScoredHeadline] = []

    # Pass 1 — per-headline terms
    token_cache: list[set[str]] = []
    for row in rows:
        title = str(row.get("title", "")).strip()
        if not title:
            continue
        recency = recency_of(str(row.get("published_at", "") or ""), now=now)
        # recency_of uses 48h half-life; convert to the news 60h half-life:
        # weight = recency ^ (48/60)
        decay = recency ** (48.0 / DECAY_HALF_LIFE_HOURS)
        scored.append(ScoredHeadline(
            title=title,
            sentiment=float(row.get("score", 0.0)),
            source=str(row.get("source", "")),
            url=str(row.get("url", "")),
            published_at=str(row.get("published_at", "")),
            event_type=classify_event(title),
            reliability=reliability_of(str(row.get("url", "")), str(row.get("source", ""))),
            decay=round(decay, 4),
        ))
        token_cache.append(_tokens(title))

    # Pass 2 — duplicate clustering (greedy, order = input order = newest first
    # from providers; the FIRST member of each cluster is the novel report)
    cluster_of: list[int] = [-1] * len(scored)
    next_cluster = 0
    for i in range(len(scored)):
        if cluster_of[i] != -1:
            continue
        cluster_of[i] = next_cluster
        for j in range(i + 1, len(scored)):
            if cluster_of[j] == -1 and _jaccard(token_cache[i], token_cache[j]) >= DUPLICATE_JACCARD:
                cluster_of[j] = next_cluster
        next_cluster += 1

    # Pass 3 — novelty + cross-source confirmation per cluster
    members: dict[int, list[int]] = {}
    for index, cluster in enumerate(cluster_of):
        members.setdefault(cluster, []).append(index)

    for cluster, indexes in members.items():
        domains = {scored[i].source.lower() or scored[i].url.split("/")[2] if "://" in scored[i].url else scored[i].source.lower()
                   for i in indexes}
        distinct = len({d for d in domains if d})
        confirmation = 1.0 + min(CONFIRMATION_BONUS_CAP,
                                 CONFIRMATION_BONUS_PER_SOURCE * max(0, distinct - 1))
        for rank, i in enumerate(indexes):
            scored[i].cluster_id = cluster
            scored[i].novelty = 1.0 if rank == 0 else REPEAT_WEIGHT
            scored[i].confirmation = round(confirmation, 3)
            scored[i].weight = round(
                scored[i].reliability * scored[i].decay * scored[i].novelty * scored[i].confirmation, 4
            )

    n_eff = round(sum(h.weight for h in scored), 3)
    s_eff = (
        round(sum(h.weight * h.sentiment for h in scored) / n_eff, 4)
        if n_eff > 1e-9 else None
    )
    return NewsEvidence(
        headlines=scored,
        n_raw=len(scored),
        n_eff=n_eff,
        s_eff=s_eff,
        clusters=len(members),
    )
