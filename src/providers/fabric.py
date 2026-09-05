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

from . import capabilities, statements

from src.providers.parallel import map_concurrent

logger = logging.getLogger(__name__)

# What a vendor can be asked for.
#
# Both views are *derived* from the capability registry rather than written
# here. Membership is still decided by whether the adapter actually implements
# the method — introspection, not a hand-kept table — but the question itself
# is now declared exactly once, in `capabilities.py`, together with its
# reconciliation strategy and failure modes. Keeping a second copy here is how
# a capability ends up with a method and no label, or the reverse.
CAPABILITY_METHODS = capabilities.CAPABILITY_METHODS
CAPABILITY_LABELS = capabilities.CAPABILITY_LABELS



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
            # Session fields, carried per reading so the reconciler can
            # attribute each one to the vendor that supplied it.
            **{
                field: getattr(e.data, field, None)
                for field in ("day_open", "day_high", "day_low", "previous_close",
                              "change", "change_pct", "vwap", "trade_count",
                              "avg_volume", "ma_50", "ma_200", "market_cap")
            },
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

    # Session context, from whichever vendor supplied each field. Deliberately
    # *not* reconciled across vendors: a session high is a fact about one
    # venue's tape, an average volume is computed over a window each vendor
    # chooses for itself, and a moving average carries its vendor's own
    # adjustment conventions. Taking a median of any of them would produce a
    # number describing no actual venue. The contributing vendor is named so
    # the reader knows whose session they are looking at.
    def _first(field: str) -> tuple[Optional[float], Optional[str]]:
        for r in readings:
            value = r.get(field)
            if value is not None:
                return value, r["provider"]
        return None, None

    session: dict[str, Any] = {}
    for field in ("day_open", "day_high", "day_low", "previous_close",
                  "change", "change_pct", "vwap", "trade_count",
                  "avg_volume", "ma_50", "ma_200", "market_cap"):
        value, provider = _first(field)
        if value is not None:
            session[field] = {"value": value, "provider": provider}

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
        # Per-field, per-vendor session context — never a cross-vendor median.
        "session": session or None,
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
                # Search relevance and byline: same fill-if-absent rule. Each
                # comes from a vendor the others cannot supply, so the merged
                # record is strictly richer than any single copy.
                if existing.relevance is None and getattr(item, "relevance", None) is not None:
                    existing.relevance = item.relevance
                    existing.relevance_source = item.relevance_source
                if not existing.author and getattr(item, "author", ""):
                    existing.author = item.author
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
    #
    # In production this is always "". `FundamentalsData` — the model every
    # vendor here actually returns — has no `period` attribute, so the
    # `getattr` default is what survives. It is left in place because a model
    # that does carry a period should still be honoured, and the real period
    # information now travels per fact in `reported` below, where it belongs:
    # one period for a whole statement block was never right anyway, since
    # Finnhub returns annual, quarterly and trailing figures in one response.
    period = max((getattr(d, "period", "") or "" for _, d in sources), default="")
    history = next((getattr(d, "history", []) for _, d in sources if getattr(d, "history", None)), [])

    # ── The figures that were being thrown away ──────────────────────────────
    #
    # Every name in `_COMPARABLE_FUNDAMENTALS` except `eps` is absent from
    # `FundamentalsData`, so the loop above can only ever populate one field.
    # The statement figures themselves were never missing: they arrive in
    # `vendor_metrics` — 131 keys from Finnhub, 10 from yfinance — and were
    # dropped whole at the API boundary.
    #
    # They are not merged into `fields`. They cannot be: Finnhub reports
    # revenue per share and yfinance reports it absolute, and a dictionary
    # keyed by concept alone has nowhere to put that distinction. They are
    # grouped by what actually makes two numbers comparable — concept, basis,
    # period and unit together — so a spread inside a group is vendor
    # disagreement, and figures in different groups are never differenced.
    reported = statements.group([
        fact
        for provider, data in sources
        for fact in statements.normalise(provider, getattr(data, "vendor_metrics", None))
    ])

    return {
        "period": period,
        "fields": fields,
        "providers": sorted({p for p, _ in sources}),
        "conflicts": conflicts,
        "history": history,
        "reported": reported,
    }


def reconcile_series(evidence: list[Evidence], tolerance_pct: float = 0.5) -> Optional[dict[str, Any]]:
    """Cross-vendor agreement on a daily close series.

    A single vendor's history cannot be checked against anything. Asking every
    history-capable vendor and comparing them on the sessions they share turns
    the series from an assertion into a measurement, and catches the one error
    that is invisible in a single series and ruinous downstream: **a raw close
    mixed in among adjusted ones**.

    That distinction is the reason this does not simply report a disagreement
    percentage. A vendor returning unadjusted closes for a stock that split
    4-for-1 disagrees with the others by 300% on every session before the
    split and by nothing after it — which is not noise, it is a systematic
    factor. Noise is small and varies by date; an adjustment mismatch is large
    and *nearly constant*. Separating them by the variance of the per-date
    ratio means a real split mismatch is reported as what it is rather than
    being averaged into a meaningless "sources disagree" figure, and a vendor
    quoting a different venue's close is not accused of a split error.

    Session coverage is reported separately from price agreement because the
    two have different causes and different fixes: a missing session is a
    vendor's calendar or backfill, a diverging close is its adjustment policy
    or its venue.
    """
    ok = [e for e in evidence if e.ok and e.data is not None]
    if len(ok) < 2:
        return None

    # date -> provider -> close
    by_date: dict[str, dict[str, float]] = {}
    coverage: dict[str, int] = {}
    for ev in ok:
        bars = getattr(ev.data, "bars", None) or []
        coverage[ev.provider] = len(bars)
        for bar in bars:
            close = getattr(bar, "close", None)
            date = getattr(bar, "date", None)
            if close is None or not date or close <= 0:
                continue
            by_date.setdefault(date, {})[ev.provider] = float(close)

    shared = {d: v for d, v in by_date.items() if len(v) >= 2}
    if not shared:
        return None

    providers = sorted(coverage)
    # Per-date dispersion, measured against the median so one bad vendor
    # cannot drag the reference the way a mean would.
    divergences: list[tuple[str, float]] = []
    conflicts: list[dict[str, Any]] = []
    for date in sorted(shared):
        closes = shared[date]
        mid = statistics.median(closes.values())
        if mid <= 0:
            continue
        worst = max(abs(c - mid) / mid * 100.0 for c in closes.values())
        divergences.append((date, worst))
        if worst > tolerance_pct:
            conflicts.append({
                "date": date,
                "divergence_pct": round(worst, 3),
                "readings": {p: round(c, 4) for p, c in sorted(closes.items())},
            })

    # Systematic adjustment mismatch: a vendor whose ratio to the cross-vendor
    # median is consistently off. `stdev/mean` rather than a raw spread so the
    # test is scale-free — a 0.2% wobble around 4.0 is still a clean 4:1.
    mismatches: list[dict[str, Any]] = []
    for provider in providers:
        ratios = []
        for date, closes in shared.items():
            if provider not in closes or len(closes) < 2:
                continue
            # Reference is the median of *all* vendors, this one included.
            # Excluding it looks more independent and is worse: with three
            # vendors it makes the median of the remaining two land between a
            # correct pair, and both correct vendors then read as mismatched
            # against a reference neither of them reported.
            mid = statistics.median(closes.values())
            if mid > 0:
                ratios.append(closes[provider] / mid)
        if len(ratios) < 5:
            continue
        mean_ratio = statistics.fmean(ratios)
        spread = statistics.pstdev(ratios) / mean_ratio if mean_ratio else 1.0
        # Off by more than the noise tolerance, but *stable* — the signature
        # of an adjustment policy difference rather than a wrong print.
        if abs(mean_ratio - 1.0) * 100 > tolerance_pct and spread < 0.02:
            mismatches.append({
                "provider": provider,
                "ratio": round(mean_ratio, 4),
                "stability": round(1.0 - spread, 4),
                "sessions": len(ratios),
                # Named only when it is close to a plain split ratio. A
                # suggestion, never a correction: nothing here rewrites the
                # series, because guessing at an adjustment is how a chart
                # becomes confidently wrong.
                "likely_split": _nearest_split(mean_ratio),
            })

    worst_overall = max((d for _, d in divergences), default=0.0)
    agreeing = sum(1 for _, d in divergences if d <= tolerance_pct)
    union_dates = set(by_date)
    # Gaps are counted only inside the window every vendor actually covers.
    #
    # Measured against the union this was actively misleading: vendors read
    # a period like "3mo" differently, and against live data Twelve Data
    # returned 92 sessions where Polygon returned 63. Differencing against
    # the union then reported Polygon as "missing 29 sessions" when it had
    # simply been asked for, and returned, a shorter window — a vendor
    # penalised for someone else's generosity. Restricting to the overlap
    # means a reported gap is a session the vendor genuinely lacks while
    # others have it, which is the only version of this number that supports
    # the conclusion a reader will draw from it.
    spans = {}
    for ev in ok:
        dates = [getattr(b, "date", None) for b in (getattr(ev.data, "bars", None) or [])]
        dates = [d for d in dates if d]
        if dates:
            spans[ev.provider] = (min(dates), max(dates))
    gaps: dict[str, int] = {}
    if spans:
        lo = max(s for s, _ in spans.values())
        hi = min(e for _, e in spans.values())
        window = {d for d in union_dates if lo <= d <= hi}
        gaps = {
            p: len(window) - sum(1 for d in window if p in by_date[d])
            for p in providers
        }
    return {
        "providers": providers,
        "coverage": coverage,
        "shared_sessions": len(shared),
        "union_sessions": len(union_dates),
        "agreeing_sessions": agreeing,
        "agreement_pct": round(agreeing / len(divergences) * 100, 2) if divergences else 0.0,
        "max_divergence_pct": round(worst_overall, 3),
        "tolerance_pct": tolerance_pct,
        # Only the worst few: a reader needs to see that conflicts exist and
        # what they look like, not every session of a disputed year.
        "conflicts": sorted(conflicts, key=lambda c: -c["divergence_pct"])[:8],
        "conflict_count": len(conflicts),
        "adjustment_mismatch": mismatches,
        "session_gaps": {p: n for p, n in gaps.items() if n},
    }


#: Plain share splits, largest first. Only used to *name* an observed ratio.
_SPLITS = (10.0, 7.0, 5.0, 4.0, 3.0, 2.0, 1.5)


def _nearest_split(ratio: float) -> Optional[str]:
    """Name a ratio as a split when it is unmistakably one, else None."""
    for s in _SPLITS:
        if abs(ratio - s) / s < 0.02:
            return f"{int(s) if s.is_integer() else s}:1"
        if abs(ratio - 1.0 / s) * s < 0.02:
            return f"1:{int(s) if s.is_integer() else s}"
    return None
