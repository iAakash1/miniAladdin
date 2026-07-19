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
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from src.providers.research_schemas import KnowledgeBundle
from src.providers.vendors.sec_vendor import SECVendor
from src.providers.vendors.wikidata_vendor import WikidataVendor
from src.services.knowledge_graph import merge_bundles, neighbors, timeline
from src.services.research import engine as research_engine

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 21600.0  # 6h: filings and encyclopedic facts move slowly
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

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


def _safe(label: str, fn) -> KnowledgeBundle:
    """A provider that fails contributes nothing — never raises upward."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 — research providers are always optional
        logger.info("knowledge provider %s unavailable", label, exc_info=True)
        return KnowledgeBundle()


def build(symbol: str, company_name: str = "") -> dict[str, Any]:
    """Merged company intelligence: graph, ecosystem, timeline, findings."""
    symbol = symbol.upper().strip()
    if not symbol:
        return _empty()

    now = time.time()
    cached = _cache.get(symbol)
    if cached and cached[0] > now:
        return cached[1]

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="knowledge") as pool:
        futures = [
            pool.submit(_safe, "sec", lambda: _sec.get_knowledge(symbol)),
            pool.submit(_safe, "wikidata", lambda: _wikidata.get_knowledge(symbol, company_name)),
        ]
        # Web research runs through the provider-agnostic engine: it walks
        # its own fallback chain (Brave → Tavily → Exa → news → Apify) and
        # returns merged, authority-ranked evidence. This engine neither
        # knows nor cares which provider answered.
        futures.append(pool.submit(_safe, "research",
                                   lambda: research_engine.research_company(symbol, company_name)))
        bundles = [future.result() for future in futures]

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
    }
    _cache[symbol] = (now + CACHE_TTL_SECONDS, result)
    return result


def _empty() -> dict[str, Any]:
    return {"symbol": "", "ecosystem": [], "claims": [], "timeline": [], "findings": [],
            "graph": {"nodes": 0, "edges": 0, "providers": []}}


def reset_for_tests() -> None:
    _cache.clear()
