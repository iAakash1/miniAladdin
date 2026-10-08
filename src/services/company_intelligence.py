"""
Company Intelligence engine — composes every research-grade provider into
one deterministic view of a company's ecosystem.

Providers run in parallel; each is independently optional. A provider that
fails, times out, or has no data for a symbol simply contributes nothing —
the engine always returns a valid (possibly smaller) result, because
research must never break analysis.

Output is the merged knowledge graph plus the derived views the product
consumes: ecosystem groups, timeline, and findings — all deterministic,
all evidence-bearing.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.providers.research_schemas import KnowledgeBundle
from src.providers import identity
from src.providers.vendors.sec_vendor import SECVendor
from src.providers.vendors.wikidata_vendor import WikidataVendor
from src.services.knowledge_graph import merge_bundles, neighbors, timeline
from src.services.research import engine as research_engine
from src.services.cache_policy import put_ttl

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 21600.0  # 6h: filings and encyclopedic facts move slowly
#: A result built while one source was down is short-lived. Holding it for six
#: hours made a thirty-second outage read as "no ecosystem found" all day; a
#: minute is long enough to stop a refresh storm hammering a struggling source
#: and short enough that recovery is visible almost at once. A result built
#: while *every* source was down is not cached at all.
DEGRADED_TTL_SECONDS = 60.0
MAX_CACHE_ENTRIES = 128
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()

_sec = SECVendor()
_wikidata = WikidataVendor()

# Edge types grouped into the ecosystem views the company page renders.
ECOSYSTEM_GROUPS: list[tuple[str, str, set[str]]] = [
    ("leadership", "Leadership", {"ceo_of", "founded", "board_member_of"}),
    ("structure", "Corporate structure", {"parent_of", "subsidiary_of", "owns", "acquired"}),
    ("products", "Products & brands", {"produces"}),
    ("market", "Industry & market", {"belongs_to", "competes_with", "listed_on"}),
    ("footprint", "Footprint", {"headquartered_in"}),
]


#: What one source did. "empty" and "unavailable" both contribute nothing to
#: the graph, but only one of them is a statement about the world.
SOURCE_OK = "ok"
SOURCE_EMPTY = "empty"
SOURCE_UNAVAILABLE = "unavailable"


def _is_empty(bundle: KnowledgeBundle) -> bool:
    return not (bundle.nodes or bundle.edges or bundle.claims or bundle.events or bundle.findings)


def _safe(label: str, fn) -> tuple[KnowledgeBundle, str]:
    """A provider that fails contributes nothing - and says that it failed.

    Never raises upward (research is additive to the deterministic record),
    but the failure is returned rather than discarded: an empty bundle from a
    source that answered "nothing here" and one from a source that could not
    be reached look identical once merged, and only the first is a finding.
    """
    try:
        bundle = fn()
    except Exception:  # noqa: BLE001 — research providers are always optional
        logger.info("knowledge provider %s unavailable", label, exc_info=True)
        return KnowledgeBundle(), SOURCE_UNAVAILABLE
    return bundle, (SOURCE_EMPTY if _is_empty(bundle) else SOURCE_OK)


def _research(symbol: str, company_name: str) -> KnowledgeBundle:
    """Web research through the engine, raising when no provider could answer."""
    bundle, outcome = research_engine.research_company_checked(symbol, company_name)
    if outcome.unavailable:
        raise RuntimeError("every research provider failed")
    return bundle


def _overall(sources: dict[str, str]) -> str:
    """complete | partial | unavailable, from what each source did."""
    states = list(sources.values())
    if not states or all(state == SOURCE_UNAVAILABLE for state in states):
        return "unavailable"
    if any(state == SOURCE_UNAVAILABLE for state in states):
        return "partial"
    return "complete"


def build(symbol: str, company_name: str = "") -> dict[str, Any]:
    """Merged company intelligence: graph, ecosystem, timeline, findings."""
    symbol = symbol.upper().strip()
    if not symbol:
        return _empty()

    now = time.time()
    with _cache_lock:
        cached = _cache.get(symbol)
    if cached and cached[0] > now:
        return cached[1]

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="knowledge") as pool:
        futures = {
            "sec": pool.submit(_safe, "sec", lambda: _sec.get_knowledge(symbol)),
            "wikidata": pool.submit(
                _safe, "wikidata", lambda: _wikidata.get_knowledge(symbol, company_name),
            ),
            # Web research runs through the provider-agnostic engine: it walks
            # its own fallback chain (Brave → Tavily → Exa → news → Apify) and
            # returns merged, authority-ranked evidence. This engine neither
            # knows nor cares which provider answered.
            "research": pool.submit(_safe, "research", lambda: _research(symbol, company_name)),
        }
        if identity.openfigi.available:
            futures["openfigi"] = pool.submit(
                _safe, "openfigi", lambda: identity.openfigi.get_instrument_identity(symbol),
            )
        settled = {name: future.result() for name, future in futures.items()}

    bundles = [bundle for bundle, _state in settled.values()]
    sources = {name: state for name, (_bundle, state) in settled.items()}
    status = _overall(sources)
    merged = merge_bundles(bundles)
    company_id = f"company:{symbol}"
    adjacent = neighbors(merged, company_id)

    ecosystem = []
    for key, label, edge_types in ECOSYSTEM_GROUPS:
        # One row per node per group: a founder who is also CEO is one
        # person, with both roles listed, not two entries.
        by_node: dict[str, dict[str, Any]] = {}
        for item in adjacent:
            if item["edge_type"] not in edge_types:
                continue
            node_id = str(item["node"].id)
            existing = by_node.get(node_id)
            if existing is None:
                by_node[node_id] = {
                    "id": node_id,
                    "label": item["node"].label,
                    "type": item["node"].type,
                    "route": item["node"].route,
                    "edges": [item["edge_type"]],
                    "confidence": round(float(item["confidence"]), 2),
                    "provider": item["provider"],
                }
            elif item["edge_type"] not in existing["edges"]:
                existing["edges"].append(str(item["edge_type"]))
                existing["confidence"] = max(existing["confidence"], round(float(item["confidence"]), 2))
        if by_node:
            ecosystem.append({"key": key, "label": label, "members": list(by_node.values())})

    result: dict[str, Any] = {
        "symbol": symbol,
        "ecosystem": ecosystem,
        "claims": [claim.model_dump() for claim in merged.claims],
        "timeline": [event.model_dump() for event in timeline(merged, limit=24)],
        "findings": [finding.model_dump() for finding in merged.findings],
        "graph": {
            "nodes": len(merged.nodes),
            "edges": len(merged.edges),
            "providers": sorted({p for edge in merged.edges for p in edge.provider.split(",") if p}),
        },
        # What each source did, and whether the picture is whole. An empty
        # ecosystem with status "unavailable" means we could not look.
        "status": status,
        "sources": sources,
    }
    # complete: held for hours. partial: held briefly. unavailable: not held at
    # all - the vendors' own cooldowns already stop a retry storm, and caching
    # "we could not look" would only delay noticing that we now can.
    if status != "unavailable":
        ttl = CACHE_TTL_SECONDS if status == "complete" else DEGRADED_TTL_SECONDS
        with _cache_lock:
            put_ttl(_cache, symbol, now + ttl, result,
                    max_entries=MAX_CACHE_ENTRIES, now=now)
    return result


def _empty() -> dict[str, Any]:
    return {"symbol": "", "ecosystem": [], "claims": [], "timeline": [], "findings": [],
            "graph": {"nodes": 0, "edges": 0, "providers": []},
            "status": "complete", "sources": {}}


def reset_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
