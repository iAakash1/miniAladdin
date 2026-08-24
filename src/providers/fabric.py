"""
Evidence fabric — every capable vendor answers, in parallel, and none is
discarded.

## Why this exists alongside the fallback chain

`FallbackChain` walks vendors in order and stops at the first that answers.
That is the right shape for *serving a value*: one price, fast, with a
defined degradation path. It is the wrong shape for *building evidence*,
because the moment Polygon answers, the four other vendors that also knew the
price are never asked — and the fact that five independent sources agreed to
within a cent is thrown away before anyone can see it.

The fabric is the other mode. Given a capability and a symbol it asks
**every healthy vendor that can answer**, concurrently, and keeps all of the
replies. Nothing is chosen; everything is recorded and then reconciled.

Both modes coexist deliberately. The chain still backs `get_price` and
`get_series`, which the scoring engine and the quotes endpoint depend on and
which must stay fast and cheap. The fabric backs research and the provenance
ledger, where the interesting question is not "what is the price" but "what
does everyone who knows say, and do they agree".

## Cost

Fan-out is bounded by `map_concurrent` and every vendor keeps its own token
bucket, so a vendor at its limit fails its own item instantly rather than
blocking the others or exceeding quota. Latency is the slowest vendor, not
the sum — a five-vendor fan-out costs about what the one-vendor chain costs.
The fabric is used on research requests, not on the batch quote path, so the
multiplier applies to a page a user opened and not to a background sweep.

## What is deliberately not done

No averaging of things that should not be averaged. Prices get a consensus
because five quotes of the same instrument at the same moment are five
measurements of one quantity. Fundamentals do not: two vendors reporting
different revenue are usually reporting *different periods or definitions*,
and a mean of those is a number no company ever reported. Disagreement there
is surfaced, not resolved.
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

from src.providers.parallel import map_concurrent

logger = logging.getLogger(__name__)

# What a vendor can be asked for. Membership is decided by whether the
# adapter actually implements the method, not by a hand-kept table — a table
# drifts the first time someone adds a method and forgets to register it.
CAPABILITY_METHODS: dict[str, str] = {
    "quote": "get_price",
    "series": "get_series",
    "news": "get_news",
    "company": "get_company",
    "fundamentals": "get_fundamentals",
    "street": "get_street",
    "analyst_targets": "get_analyst_targets",
    # Visual capabilities. Deliberately two entries and not one: a brand mark
    # is a company's identity and a stock photograph is industry context, and
    # a single "image" capability would let a provider that can only do one
    # be asked for the other.
    "brand_mark": "get_brand",
    "image_search": "search_images",
    # Structured news sentiment — a capability only some news vendors have.
    # Kept separate from `news` so a vendor that returns headlines without
    # sentiment is not asked for something it cannot supply.
    "news_sentiment": "get_news_sentiment",
    # Primary-source regulatory evidence. SEC EDGAR is keyless and is the
    # only source here that is not a vendor's interpretation of a filing but
    # the filing itself — which is a different *kind* of evidence, not a
    # cheaper copy of the same kind, so it gets its own capabilities.
    "filings": "get_filings",
    "xbrl_facts": "get_xbrl_facts",
}

# Human labels for the diagnostics surface. A capability with no label is
# still discoverable; this only controls how it reads.
CAPABILITY_LABELS: dict[str, str] = {
    "quote": "Real-time quote",
    "series": "Daily price history",
    "news": "Headlines",
    "news_sentiment": "Scored news sentiment",
    "company": "Company profile",
    "fundamentals": "Reported fundamentals",
    "street": "Analyst & insider activity",
    "analyst_targets": "Price targets",
    "brand_mark": "Company logo",
    "image_search": "Editorial imagery",
    "filings": "SEC filings",
    "xbrl_facts": "XBRL reported facts",
}


def capability_matrix(groups: dict[str, Sequence[Any]]) -> dict[str, Any]:
    """What every provider in the system can do, right now.

    Introspection-driven rather than a hand-kept table: a table drifts the
    first time someone adds a method and forgets to register it, and the
    thing this exists to answer — "who can contribute to this request" — is
    exactly the question a stale table answers wrongly.

    Reports configuration and health separately because they fail for
    different reasons and are fixed by different people: `configured` is
    false when an API key is absent (a deploy concern), `healthy` is false
    when the circuit has tripped after repeated failures (an outage). A
    provider that is configured but unhealthy is a very different situation
    from one that was never set up.
    """
    seen: dict[str, dict[str, Any]] = {}
    for group, vendors in groups.items():
        for vendor in vendors:
            name = getattr(vendor, "NAME", "unknown")
            entry = seen.setdefault(name, {
                "provider": name,
                "groups": [],
                "configured": bool(getattr(vendor, "available", False)),
                "healthy": bool(getattr(vendor, "healthy", False)),
                "capabilities": [],
                "key_env": getattr(vendor, "KEY_ENV", None),
                "rpm": getattr(getattr(vendor, "rate_limiter", None), "capacity", None),
            })
            if group not in entry["groups"]:
                entry["groups"].append(group)
            for capability, method in CAPABILITY_METHODS.items():
                if hasattr(vendor, method) and capability not in entry["capabilities"]:
                    entry["capabilities"].append(capability)

    providers = sorted(seen.values(), key=lambda e: e["provider"])
    for entry in providers:
        entry["capabilities"].sort()

    # Inverted view: the question the orchestrator actually asks.
    by_capability: dict[str, dict[str, list[str]]] = {}
    for capability in CAPABILITY_METHODS:
        contributors = [e["provider"] for e in providers if capability in e["capabilities"]]
        if not contributors:
            continue
        by_capability[capability] = {
            "label": CAPABILITY_LABELS.get(capability, capability),
            "implemented_by": contributors,
            # Only these will actually be asked on the next fan-out.
            "live": [
                e["provider"] for e in providers
                if capability in e["capabilities"] and e["healthy"]
            ],
            "unconfigured": [
                e["provider"] for e in providers
                if capability in e["capabilities"] and not e["configured"]
            ],
        }

    return {
        "providers": providers,
        "by_capability": by_capability,
        "totals": {
            "providers": len(providers),
            "configured": sum(1 for e in providers if e["configured"]),
            "healthy": sum(1 for e in providers if e["healthy"]),
            "capabilities": len(by_capability),
        },
    }

# Prices within this fraction of the consensus are "agreeing". Half a percent
# is wider than a bid-ask spread on a liquid name and narrower than the gap
# between a live quote and a previous close, so it separates the two cases
# this actually needs to distinguish.
PRICE_AGREE_TOLERANCE = 0.005


@dataclass
class Evidence:
    """One vendor's answer to one question, kept whether or not it succeeded.

    A failure is evidence too: "Polygon was asked and timed out" is a fact the
    provenance ledger needs, and dropping it would make a degraded run
    indistinguishable from a narrow one.
    """

    provider: str
    capability: str
    symbol: str
    ok: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # "live" | "unavailable" | "not_entitled" | "rate_limited" | "timeout"
    status: str = "live"


def capable(vendors: Iterable[Any], capability: str) -> list[Any]:
    """Healthy vendors that implement this capability.

    `healthy` covers both "key configured" and "not cooling down after
    repeated failures", so a vendor in its circuit-breaker window is skipped
    without being asked — which is the point of the circuit.
    """
    method = CAPABILITY_METHODS.get(capability)
    if not method:
        return []
    return [v for v in vendors if getattr(v, "healthy", False) and hasattr(v, method)]


def _classify(error: BaseException) -> str:
    text = str(error).lower()
    if "rate limit" in text or "429" in text:
        return "rate_limited"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "403" in text or "not permissioned" in text or "401" in text:
        return "not_entitled"
    return "unavailable"


def collect(
    capability: str,
    symbol: str,
    vendors: Sequence[Any],
    call: Callable[[Any], Any],
    *,
    timeout: float = 12.0,
) -> list[Evidence]:
    """Ask every capable vendor concurrently. Keep every answer.

    Never raises: a vendor that fails produces a failed `Evidence`, and the
    caller decides what a partial set is worth. A research request with four
    of five sources is a valid research request.
    """
    targets = capable(vendors, capability)
    if not targets:
        return []

    def run(vendor: Any) -> Evidence:
        started = time.perf_counter()
        try:
            data = call(vendor)
        except BaseException as exc:  # noqa: BLE001 — a vendor must not break the fan-out
            return Evidence(
                provider=getattr(vendor, "NAME", "unknown"),
                capability=capability, symbol=symbol, ok=False,
                error=str(exc)[:200], status=_classify(exc),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )
        latency = round((time.perf_counter() - started) * 1000, 1)
        name = getattr(vendor, "NAME", "unknown")
        if data is None:
            # A clean `None` is "this vendor has nothing for this symbol" —
            # a different fact from an error, and the one that distinguishes
            # an unentitled endpoint from a broken one.
            return Evidence(provider=name, capability=capability, symbol=symbol,
                            ok=False, error="no data for symbol",
                            status="unavailable", latency_ms=latency)
        return Evidence(provider=name, capability=capability, symbol=symbol,
                        ok=True, data=data, latency_ms=latency)

    outcomes = map_concurrent(run, targets, timeout=timeout, label=f"fabric.{capability}")
    out: list[Evidence] = []
    for vendor, outcome in zip(targets, outcomes):
        if outcome.ok and outcome.value is not None:
            out.append(outcome.value)
        else:
            # The fan-out itself gave up on this item — a hang past the
            # backstop. Still recorded, so the ledger shows it was asked.
            out.append(Evidence(
                provider=getattr(vendor, "NAME", "unknown"),
                capability=capability, symbol=symbol, ok=False,
                error="exceeded fan-out timeout", status="timeout",
                latency_ms=round(outcome.seconds * 1000, 1),
            ))
    return out


# ── reconciliation ─────────────────────────────────────────────────────────

def reconcile_price(evidence: list[Evidence]) -> Optional[dict[str, Any]]:
    """Consensus across every vendor that quoted the same instrument.

    Median, not mean: one vendor returning a stale previous close while four
    return the live print should not drag the answer a third of the way to
    yesterday. The median ignores it and the dispersion reports it.

    Every individual reading is kept. The point of asking five vendors is not
    to compute one number — it is to be able to say *how much they agreed*,
    which is exactly what a single-vendor answer can never tell you.
    """
    readings = [
        {
            "provider": e.provider,
            "price": float(getattr(e.data, "price", 0) or 0),
            "basis": getattr(e.data, "price_basis", None),
            "bid": getattr(e.data, "bid", None),
            "ask": getattr(e.data, "ask", None),
            "spread_bps": getattr(e.data, "spread_bps", None),
            "volume": getattr(e.data, "volume", None),
            "as_of": getattr(e.data, "as_of", None),
            "latency_ms": e.latency_ms,
        }
        for e in evidence
        if e.ok and getattr(e.data, "price", None)
    ]
    if not readings:
        return None

    prices = sorted(r["price"] for r in readings)
    consensus = statistics.median(prices)
    low, high = prices[0], prices[-1]
    # Dispersion as a fraction of the consensus, so it is comparable across a
    # $3 stock and a $3,000 one.
    dispersion = (high - low) / consensus if consensus else 0.0
    agreeing = sum(1 for p in prices if abs(p - consensus) / consensus <= PRICE_AGREE_TOLERANCE) \
        if consensus else 0

    # Microstructure is taken from whichever vendor actually supplies a book;
    # it is not averaged, because a spread is a property of one venue.
    quoted = next((r for r in readings if r["bid"] is not None and r["ask"] is not None), None)

    return {
        "consensus": round(consensus, 4),
        "low": round(low, 4),
        "high": round(high, 4),
        "dispersion_pct": round(dispersion * 100, 4),
        "provider_count": len(readings),
        "agreeing": agreeing,
        "agreement": f"{agreeing}/{len(readings)}",
        # Material disagreement is a fact about the data, surfaced rather
        # than smoothed away.
        "conflict": len(readings) > 1 and dispersion > PRICE_AGREE_TOLERANCE * 2,
        "readings": sorted(readings, key=lambda r: r["provider"]),
        "bid": quoted["bid"] if quoted else None,
        "ask": quoted["ask"] if quoted else None,
        "spread_bps": quoted["spread_bps"] if quoted else None,
        "spread_source": quoted["provider"] if quoted else None,
        "volume": next((r["volume"] for r in readings if r["volume"]), None),
    }


def _canonical_title(title: str) -> str:
    """A title reduced to what makes two headlines the same story.

    Publishers rewrite the same wire copy with different punctuation,
    casing and a trailing outlet name. Comparing raw strings would call those
    four distinct stories and inflate an evidence count fourfold.
    """
    lowered = title.lower()
    kept = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
    words = [w for w in kept.split() if len(w) > 2]
    return " ".join(words[:12])


def merge_news(evidence: list[Evidence]) -> dict[str, Any]:
    """One stream from every news vendor, deduplicated, with corroboration.

    Two vendors carrying the same URL is one story seen twice, not two
    stories — and the fact that it was seen twice is worth keeping, because
    independent corroboration is the closest thing a news feed has to
    verification. So duplicates collapse into one headline whose
    `corroborated_by` names every vendor that carried it.

    URL first, then canonical title: syndication changes the URL while
    keeping the copy, so URL alone under-merges.
    """
    by_key: dict[str, Any] = {}
    order: list[str] = []
    total = 0

    for ev in evidence:
        if not ev.ok or not isinstance(ev.data, list):
            continue
        for item in ev.data:
            title = getattr(item, "title", "") or ""
            if not title:
                continue
            total += 1
            url = (getattr(item, "url", "") or "").split("?")[0].rstrip("/").lower()
            key = url or _canonical_title(title)
            if key in by_key:
                existing = by_key[key]
                if ev.provider not in existing.corroborated_by:
                    existing.corroborated_by.append(ev.provider)
                # Merge toward the *richest* record rather than keeping
                # whichever vendor happened to answer first. One vendor has
                # the summary, another the publisher's image, a third the
                # sentiment score — the union is strictly better than any
                # single copy, and this is the whole reason to fan out.
                if not existing.summary and getattr(item, "summary", ""):
                    existing.summary = item.summary
                if not existing.published_at and getattr(item, "published_at", ""):
                    existing.published_at = item.published_at
                if not existing.tags and getattr(item, "tags", None):
                    existing.tags = list(item.tags)
                if not existing.tickers and getattr(item, "tickers", None):
                    existing.tickers = list(item.tickers)
                # The publisher's own photograph. Never overwritten once set:
                # a second vendor's copy of the same story is not a better
                # source for the image than the first.
                if not existing.image_url and getattr(item, "image_url", ""):
                    existing.image_url = item.image_url
                # Only one vendor scores sentiment, so this fills in rather
                # than competing. `is None` and not falsy: a score of 0.0 is a
                # measurement of neutral, not an absence.
                if existing.sentiment_score is None and getattr(item, "sentiment_score", None) is not None:
                    existing.sentiment_score = item.sentiment_score
                    existing.sentiment_label = item.sentiment_label
                    existing.sentiment_relevance = item.sentiment_relevance
                    existing.sentiment_source = item.sentiment_source
                continue
            item.corroborated_by = [ev.provider]
            by_key[key] = item
            order.append(key)

    unique = [by_key[k] for k in order]
    contributing = sorted({e.provider for e in evidence if e.ok})

    # Vendor-scored tone, summarised only over the articles that actually
    # carry a score. Articles nobody scored are reported as unscored rather
    # than counted as neutral — "not measured" and "measured as neutral" are
    # different facts, and merging them would let a stream with two scored
    # articles look as well-evidenced as one with twenty.
    scored = [h for h in unique if h.sentiment_score is not None]
    sentiment = None
    if scored:
        positive = sum(1 for h in scored if (h.sentiment_score or 0) > 0.15)
        negative = sum(1 for h in scored if (h.sentiment_score or 0) < -0.15)
        sentiment = {
            "scored": len(scored),
            "unscored": len(unique) - len(scored),
            "positive": positive,
            "negative": negative,
            "neutral": len(scored) - positive - negative,
            "mean": round(sum(h.sentiment_score or 0 for h in scored) / len(scored), 3),
            "source": scored[0].sentiment_source,
        }

    return {
        "headlines": unique,
        "collected": total,
        "unique": len(unique),
        "providers": contributing,
        # Stories more than one vendor carried independently. The strongest
        # signal a headline stream offers about whether an event is real.
        "corroborated": sum(1 for h in unique if len(h.corroborated_by) > 1),
        "with_image": sum(1 for h in unique if h.image_url),
        "sentiment": sentiment,
    }


# Fields where two vendors disagreeing means a real conflict rather than a
# definitional difference. Balance-sheet levels are comparable; anything
# derived (margins, ratios) is not, and is left out.
_COMPARABLE_FUNDAMENTALS = (
    "revenue", "gross_profit", "operating_income", "net_income", "ebitda",
    "eps", "total_assets", "total_liabilities", "equity", "cash", "debt",
    "free_cash_flow", "operating_cash_flow", "shares_diluted",
)


# Identity fields where the *most complete* answer wins rather than the first.
# These are strings and integers, not measurements, so there is no median to
# take — but there is a defensible tie-break, and "longest description" /
# "most specific sector" is it.
_PROFILE_TEXT = (
    "name", "sector", "industry", "exchange", "website", "domain",
    "description", "ceo", "country", "ipo_date", "currency", "vendor_image",
)
_PROFILE_NUMERIC = ("market_cap", "employees", "beta")

def _text_rank(field: str, value: str) -> tuple[int, int]:
    """Tie-break for identity strings: (preference, length).

    Length alone was picking "ELECTRONIC COMPUTERS" — Polygon's SIC
    description — over yfinance's "Consumer Electronics", because SIC
    descriptions are long and shouty. SIC is a 1930s government taxonomy;
    GICS is what a company page should show and what an industry image query
    should be built from. All-caps is a reliable marker of the former, so it
    sorts below anything cased normally, and length only breaks ties inside
    a preference band.
    """
    if field in ("sector", "industry") and value.isupper() and len(value) > 3:
        return (0, len(value))
    return (1, len(value))


# Two vendors' market caps within this fraction are the same number measured
# at different moments, not a disagreement. Market cap moves with the price
# all day, so the tolerance is wider than a fundamentals figure would get.
_CAP_TOLERANCE = 0.05


def merge_profile(evidence: list[Evidence]) -> Optional[dict[str, Any]]:
    """Company identity as a union across every vendor that answered.

    No single vendor here carries a complete profile: Finnhub has the domain
    and the IPO date, Polygon the SIC description and headcount, yfinance the
    GICS sector and the business summary. Choosing one would throw away
    whatever the others uniquely hold, which is precisely the loss the fabric
    exists to prevent.

    Text fields resolve to the *longest* non-empty answer, which is a
    deliberate and narrow rule: between "Technology" and "Consumer
    Electronics" the longer string is the more specific classification, and
    between a truncated description and a full one it is the complete one.
    It is not a quality judgement — it is a tie-break that happens to
    correlate with completeness, and every contributing value is retained
    alongside it so a reader can see what was chosen over what.

    Numeric fields keep the median and flag disagreement, except market cap,
    which gets a wider tolerance because it moves with the price all day and
    two vendors quoting it minutes apart are not in conflict.
    """
    sources = [(e.provider, e.data) for e in evidence if e.ok and e.data is not None]
    if not sources:
        return None

    fields: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []

    for name in _PROFILE_TEXT:
        observations = [
            {"provider": provider, "value": str(getattr(data, name, "") or "").strip()}
            for provider, data in sources
            if str(getattr(data, name, "") or "").strip()
        ]
        if not observations:
            continue
        best = max(observations, key=lambda o: _text_rank(name, o["value"]))
        distinct = {o["value"].lower() for o in observations}
        fields[name] = {
            "value": best["value"],
            "chosen_from": best["provider"],
            "providers": [o["provider"] for o in observations],
            "observations": observations if len(distinct) > 1 else None,
            "agrees": len(distinct) == 1,
        }

    for name in _PROFILE_NUMERIC:
        observations = [
            {"provider": provider, "value": float(getattr(data, name))}
            for provider, data in sources
            if isinstance(getattr(data, name, None), (int, float))
        ]
        if not observations:
            continue
        values = [o["value"] for o in observations]
        value = statistics.median(values)
        spread = (max(values) - min(values)) / abs(value) if value else 0.0
        tolerance = _CAP_TOLERANCE if name == "market_cap" else 0.01
        agrees = len(observations) == 1 or spread <= tolerance
        fields[name] = {
            "value": value,
            "providers": [o["provider"] for o in observations],
            "observations": observations if len(observations) > 1 else None,
            "agrees": agrees,
        }
        if not agrees:
            conflicts.append({"field": name, "observations": observations,
                              "spread_pct": round(spread * 100, 2)})

    return {
        "fields": fields,
        "providers": sorted({p for p, _ in sources}),
        "conflicts": conflicts,
        # Flattened view for consumers that just want the profile. The
        # per-field provenance above is what makes the flat view auditable.
        "resolved": {name: entry["value"] for name, entry in fields.items()},
    }


def merge_fundamentals(evidence: list[Evidence]) -> Optional[dict[str, Any]]:
    """Union of every vendor's statement figures, with disagreement kept.

    A union rather than a choice, because no single fundamentals vendor here
    covers every line: one has revenue and net income, another has free cash
    flow, a third has EBITDA. Taking the "best" vendor would discard fields
    that only the others have — which is precisely the information a
    multi-provider system exists to recover.

    Where two vendors report the same field, **both values are kept** and the
    field is marked as conflicting if they differ by more than 1%. They are
    not averaged: two vendors reporting different revenue are usually
    reporting different periods or definitions, and their mean is a number
    no company ever reported.
    """
    sources = [(e.provider, e.data) for e in evidence if e.ok and e.data is not None]
    if not sources:
        return None

    fields: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []

    for name in _COMPARABLE_FUNDAMENTALS:
        observations = [
            {"provider": provider, "value": float(getattr(data, name))}
            for provider, data in sources
            if isinstance(getattr(data, name, None), (int, float))
        ]
        if not observations:
            continue
        values = [o["value"] for o in observations]
        # Median again: with three sources it resists one bad parse, and with
        # one source it is that source.
        value = statistics.median(values)
        spread = (max(values) - min(values)) / abs(value) if value else 0.0
        entry = {
            "value": value,
            "providers": [o["provider"] for o in observations],
            "observations": observations if len(observations) > 1 else None,
            "agrees": len(observations) == 1 or spread <= 0.01,
        }
        fields[name] = entry
        if len(observations) > 1 and spread > 0.01:
            conflicts.append({"field": name, "observations": observations,
                              "spread_pct": round(spread * 100, 2)})

    # The reporting period is taken from the newest statement any vendor has;
    # mixing periods across vendors is exactly the error this guards.
    period = max((getattr(d, "period", "") or "" for _, d in sources), default="")
    history = next((getattr(d, "history", []) for _, d in sources if getattr(d, "history", None)), [])

    return {
        "period": period,
        "fields": fields,
        "providers": sorted({p for p, _ in sources}),
        "conflicts": conflicts,
        "history": history,
    }
