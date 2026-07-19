"""
Graph traversal service — expand any node in the knowledge graph.

The company engine roots the graph at a ticker; this service makes every
node a valid starting point, which is what turns a set of company
ecosystems into one continuously explorable graph: open a company, click
its CEO, see every company they lead, click a product, see its owner.

Node ids are `{type}:{key}`. Companies expand through the full company
engine (SEC + Wikidata + web); every other node type expands through
Wikidata by QID. QIDs travel on the nodes themselves, so expansion never
needs a label re-lookup.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.providers.research_schemas import KnowledgeBundle
from src.providers.vendors.wikidata_vendor import WikidataVendor
from src.services import company_intelligence
from src.services.knowledge_graph import neighbors

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 21600.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_qid_index: dict[str, tuple[str, str]] = {}  # node_id → (qid, label)

_wikidata = WikidataVendor()


def remember_qids(bundle_nodes: list) -> None:
    """Record node → QID so later expansion is a direct lookup."""
    for node in bundle_nodes:
        qid = (node.metadata or {}).get("qid") or (node.metadata or {}).get("wikidata") or ""
        if qid.startswith("Q"):
            _qid_index[node.id] = (qid, node.label)


def expand(node_id: str, label_hint: str = "") -> dict[str, Any]:
    """Neighbours of one node, as a renderable graph slice."""
    node_id = node_id.strip()
    if not node_id or ":" not in node_id:
        return _empty(node_id)

    now = time.time()
    cached = _cache.get(node_id)
    if cached and cached[0] > now:
        return cached[1]

    node_type, key = node_id.split(":", 1)

    if node_type == "company" and key and not key.startswith("q"):
        result = _expand_company(key)
    else:
        result = _expand_entity(node_id, node_type, key, label_hint)

    _cache[node_id] = (now + CACHE_TTL_SECONDS, result)
    return result


def _expand_company(ticker: str) -> dict[str, Any]:
    intel = company_intelligence.build(ticker)
    center = {
        "id": f"company:{ticker}",
        "type": "company",
        "label": ticker,
        "route": f"/company/{ticker}",
    }
    edges: list[dict[str, Any]] = []
    for group in intel.get("ecosystem", []):
        for member in group["members"]:
            edges.append({
                "node": {
                    "id": member["id"],
                    "type": member["type"],
                    "label": member["label"],
                    "route": member["route"],
                },
                "types": member["edges"],
                "group": group["label"],
                "confidence": member["confidence"],
                "provider": member["provider"],
            })
    return {
        "center": center,
        "edges": edges,
        "timeline": intel.get("timeline", [])[:8],
        "findings": intel.get("findings", [])[:6],
    }


def _expand_entity(node_id: str, node_type: str, key: str, label_hint: str) -> dict[str, Any]:
    known = _qid_index.get(node_id)
    qid = known[0] if known else ""
    label = (known[1] if known else "") or label_hint or key.replace("-", " ").title()

    if not qid:
        # Never seen this node: resolve it by label once, then remember it.
        qid = _resolve_qid(label)
    if not qid:
        return _empty(node_id, label, node_type)

    bundle = _wikidata.expand_entity(qid, label, node_type, node_id)
    remember_qids(bundle.nodes)
    adjacent = neighbors(bundle, node_id)

    edges = [
        {
            "node": {
                "id": str(item["node"].id),
                "type": item["node"].type,
                "label": item["node"].label,
                "route": item["node"].route,
            },
            "types": [item["edge_type"]],
            "group": _GROUP_FOR_EDGE.get(str(item["edge_type"]), "Related"),
            "confidence": round(float(item["confidence"]), 2),
            "provider": item["provider"],
        }
        for item in adjacent
    ]
    return {
        "center": {"id": node_id, "type": node_type, "label": label,
                   "route": f"/terminal/graph?node={node_id}"},
        "edges": edges,
        "timeline": [],
        "findings": [],
    }


_GROUP_FOR_EDGE: dict[str, str] = {
    "ceo_of": "Leadership", "founded": "Leadership", "board_member_of": "Leadership",
    "parent_of": "Corporate structure", "subsidiary_of": "Corporate structure",
    "owns": "Corporate structure", "acquired": "Corporate structure",
    "produces": "Products & brands",
    "belongs_to": "Industry & market", "competes_with": "Industry & market",
    "listed_on": "Industry & market", "headquartered_in": "Footprint",
}


def _resolve_qid(label: str) -> str:
    safe = label.replace('"', "").replace("\\", "")
    if not safe:
        return ""
    try:
        # Exact label first, then aliases: many products are stored under a
        # fuller name ("Microsoft Azure") than the one users click ("Azure").
        # Bare label lookup is ambiguous — "Azure" matches the colour before
        # the cloud platform. Require the candidate to participate in at
        # least one business relationship (developer, manufacturer, owner,
        # produces, CEO), which is exactly what makes a node worth exploring.
        rows = _wikidata._query(f"""
            SELECT ?item (COUNT(?link) AS ?links) WHERE {{
              {{ ?item rdfs:label "{safe}"@en }}
              UNION
              {{ ?item skos:altLabel "{safe}"@en }}
              {{ ?item wdt:P178|wdt:P176|wdt:P127 ?link }}
              UNION
              {{ ?other wdt:P1056|wdt:P169|wdt:P355 ?item . BIND(?other AS ?link) }}
            }}
            GROUP BY ?item ORDER BY DESC(?links) LIMIT 1
        """)
    except Exception:  # noqa: BLE001 — expansion is always optional
        logger.info("qid resolution failed for %s", label, exc_info=True)
        return ""
    if not rows:
        return ""
    qid = rows[0]["item"]["value"].rsplit("/", 1)[-1]
    return qid if qid.startswith("Q") else ""


def _empty(node_id: str, label: str = "", node_type: str = "concept") -> dict[str, Any]:
    return {
        "center": {"id": node_id, "type": node_type, "label": label or node_id,
                   "route": f"/terminal/graph?node={node_id}"},
        "edges": [], "timeline": [], "findings": [],
    }


def reset_for_tests() -> None:
    _cache.clear()
    _qid_index.clear()


# ── V9 workspace operations ──────────────────────────────────────────────────
# Composed from graph_api primitives over a bundle assembled from the nodes
# the user has actually explored. No UI component implements traversal.

def _bundle_for(symbols: list[str]) -> KnowledgeBundle:
    """Merge the ecosystems of several companies into one working graph."""
    from src.providers.vendors.sec_vendor import SECVendor
    from src.services.knowledge_graph import merge_bundles

    bundles = []
    for symbol in symbols[:4]:  # bounded: a workspace, not a crawl
        try:
            bundles.append(_wikidata.get_knowledge(symbol, ""))
        except Exception:  # noqa: BLE001
            logger.info("workspace bundle failed for %s", symbol, exc_info=True)
    return merge_bundles(bundles) if bundles else KnowledgeBundle()


def workspace(symbols: list[str], hops: int = 2,
              node_types: Optional[set[str]] = None,
              edge_types: Optional[set[str]] = None,
              min_confidence: float = 0.0,
              before: Optional[str] = None) -> dict[str, Any]:
    """A filtered, bounded working graph plus its analytics — the payload
    behind the Knowledge Graph Workspace."""
    from src.services import graph_api

    symbols = [s.upper().strip() for s in symbols if s.strip()][:4]
    if not symbols:
        return {"nodes": [], "edges": [], "analytics": {}, "roots": []}

    cache_key = f"ws:{','.join(symbols)}:{hops}"
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and cached[0] > now and not (node_types or edge_types or min_confidence or before):
        return cached[1]

    bundle = _bundle_for(symbols)
    roots = [f"company:{s}" for s in symbols]

    # Expand from every root, then union the reachable sets.
    reached: list[str] = []
    for root in roots:
        reached.extend(n.id for n in graph_api.within_hops(bundle, root, hops=hops).nodes)
    view = graph_api.subgraph(bundle, reached)
    view = graph_api.filter_graph(
        view, node_types=node_types, edge_types=edge_types,
        min_confidence=min_confidence, before=before,
    )

    result = {
        "roots": roots,
        "nodes": [n.model_dump() for n in view.nodes],
        "edges": [e.model_dump() for e in view.edges],
        "analytics": graph_api.analytics(view),
        "shared": [
            {"node": row["node"].model_dump(), "connects_to": row["connects_to"]}
            for row in graph_api.shared_neighbors(view, roots)
        ] if len(roots) > 1 else [],
    }
    if not (node_types or edge_types or min_confidence or before):
        _cache[cache_key] = (now + CACHE_TTL_SECONDS, result)
    return result


def path_between(symbols: list[str], source: str, target: str) -> list[dict[str, Any]]:
    """Shortest deterministic path, explained edge by edge."""
    from src.services import graph_api

    bundle = _bundle_for([s.upper().strip() for s in symbols if s.strip()])
    chain = graph_api.shortest_path(bundle, source, target)
    return [
        {
            "node": step["node"].model_dump(),
            "edge": step["edge"].model_dump() if "edge" in step else None,
        }
        for step in chain
    ]
