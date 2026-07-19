"""
Graph API — every traversal operation the workspace needs, as pure
functions over a KnowledgeBundle.

No UI component implements graph logic; it calls these. Each function is
deterministic: the same graph and arguments always produce the same
result, in the same order. That is what lets the frontend build stable
layouts and lets these be unit-tested without a browser.

Operations: neighbors (in knowledge_graph), subgraph, shortest_path,
within_hops, filtering, shared_neighbors (multi-select / compare) and
analytics.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

from src.providers.research_schemas import GraphEdge, GraphNode, KnowledgeBundle


# ── indexing ─────────────────────────────────────────────────────────────────

def adjacency(bundle: KnowledgeBundle) -> dict[str, list[tuple[str, GraphEdge]]]:
    """Undirected adjacency: node id → [(neighbour id, edge)].

    Traversal is undirected because relationships are navigable both ways
    (a CEO leads a company; the company is led by them), while the edge
    itself keeps its direction and meaning.
    """
    index: dict[str, list[tuple[str, GraphEdge]]] = {}
    known = {node.id for node in bundle.nodes}
    for edge in bundle.edges:
        if edge.source_id not in known or edge.target_id not in known:
            continue  # dangling edges are never traversable
        index.setdefault(edge.source_id, []).append((edge.target_id, edge))
        index.setdefault(edge.target_id, []).append((edge.source_id, edge))
    # Deterministic ordering: confidence, then id.
    for node_id, entries in index.items():
        entries.sort(key=lambda item: (-item[1].confidence, item[0]))
    return index


def node_index(bundle: KnowledgeBundle) -> dict[str, GraphNode]:
    return {node.id: node for node in bundle.nodes}


# ── traversal ────────────────────────────────────────────────────────────────

def within_hops(bundle: KnowledgeBundle, start: str, hops: int = 2,
                limit: int = 200) -> KnowledgeBundle:
    """Every node reachable from `start` in ≤ hops, as a sub-bundle.

    Breadth-first, so results are ordered by distance — the basis of
    "everything connected to NVIDIA within 3 hops".
    """
    if hops < 0:
        return KnowledgeBundle()
    nodes = node_index(bundle)
    if start not in nodes:
        return KnowledgeBundle()
    index = adjacency(bundle)

    reached: dict[str, int] = {start: 0}
    order: list[str] = [start]
    queue: deque[str] = deque([start])
    while queue and len(order) < limit:
        current = queue.popleft()
        depth = reached[current]
        if depth >= hops:
            continue
        for neighbour, _edge in index.get(current, []):
            if neighbour in reached:
                continue
            reached[neighbour] = depth + 1
            order.append(neighbour)
            queue.append(neighbour)
            if len(order) >= limit:
                break
    return subgraph(bundle, order)


def subgraph(bundle: KnowledgeBundle, node_ids: Iterable[str]) -> KnowledgeBundle:
    """The induced sub-bundle: these nodes and every edge between them."""
    wanted = list(dict.fromkeys(node_ids))  # de-dupe, preserve order
    wanted_set = set(wanted)
    nodes = node_index(bundle)
    return KnowledgeBundle(
        nodes=[nodes[nid] for nid in wanted if nid in nodes],
        edges=[
            edge for edge in bundle.edges
            if edge.source_id in wanted_set and edge.target_id in wanted_set
        ],
    )


def shortest_path(bundle: KnowledgeBundle, source: str, target: str,
                  max_hops: int = 6) -> list[dict[str, object]]:
    """Shortest deterministic path between two nodes.

    Returns the alternating node/edge chain so the UI can explain HOW two
    entities connect ("OpenAI —invested_in← Microsoft"), not merely that
    they do. Empty when unreachable within max_hops.
    """
    nodes = node_index(bundle)
    if source not in nodes or target not in nodes:
        return []
    if source == target:
        return [{"node": nodes[source]}]

    index = adjacency(bundle)
    previous: dict[str, tuple[str, GraphEdge]] = {}
    seen = {source}
    queue: deque[tuple[str, int]] = deque([(source, 0)])

    while queue:
        current, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for neighbour, edge in index.get(current, []):
            if neighbour in seen:
                continue
            seen.add(neighbour)
            previous[neighbour] = (current, edge)
            if neighbour == target:
                queue.clear()
                break
            queue.append((neighbour, depth + 1))

    if target not in previous:
        return []

    chain: list[dict[str, object]] = []
    cursor = target
    while cursor != source:
        parent, edge = previous[cursor]
        chain.append({"node": nodes[cursor], "edge": edge})
        cursor = parent
    chain.append({"node": nodes[source]})
    chain.reverse()
    return chain


def shared_neighbors(bundle: KnowledgeBundle, node_ids: list[str]) -> list[dict[str, object]]:
    """Entities connected to ALL of the given nodes — the multi-select and
    compare primitive ("what do NVDA, AMD and INTC have in common?")."""
    if len(node_ids) < 2:
        return []
    index = adjacency(bundle)
    nodes = node_index(bundle)
    sets = [
        {neighbour for neighbour, _ in index.get(node_id, [])}
        for node_id in node_ids
    ]
    common = set.intersection(*sets) if sets else set()
    common -= set(node_ids)
    return sorted(
        (
            {
                "node": nodes[nid],
                "connects_to": sorted(node_ids),
            }
            for nid in common if nid in nodes
        ),
        key=lambda row: str(row["node"].label).lower(),  # type: ignore[union-attr]
    )


# ── filtering ────────────────────────────────────────────────────────────────

def supports_historical_reconstruction(bundle: KnowledgeBundle) -> bool:
    """True only when providers have populated real validity intervals.

    Guards any as-of UI: while this is False, the product must not offer
    historical reconstruction, because `observed_at` records when we
    fetched an edge, not when it was true.
    """
    return any(edge.valid_from for edge in bundle.edges)


def filter_graph(
    bundle: KnowledgeBundle,
    node_types: Optional[set[str]] = None,
    edge_types: Optional[set[str]] = None,
    min_confidence: float = 0.0,
    providers: Optional[set[str]] = None,
    before: Optional[str] = None,
    as_of: Optional[str] = None,
) -> KnowledgeBundle:
    """Filtered view.

    `before` (ISO date) filters on `observed_at` — when OmniSignal RECORDED
    a relationship, not when it began. Providers (Wikidata, SEC) supply no
    relationship start dates, so this cannot reconstruct history: it shows
    what was known by a date. True historical reconstruction would need
    Wikidata P580/P582 start/end qualifiers, which is future work.
    """
    keep_nodes = [
        node for node in bundle.nodes
        if node_types is None or node.type in node_types
    ]
    keep_ids = {node.id for node in keep_nodes}
    keep_edges = []
    for edge in bundle.edges:
        if edge.source_id not in keep_ids or edge.target_id not in keep_ids:
            continue
        if edge_types is not None and edge.type not in edge_types:
            continue
        if edge.confidence < min_confidence:
            continue
        if providers is not None and not (set(edge.provider.split(",")) & providers):
            continue
        if before and edge.observed_at and edge.observed_at > before:
            continue
        # True as-of filtering, active only for edges carrying real validity
        # intervals; edges without them are never silently excluded.
        if as_of and edge.valid_from:
            if edge.valid_from > as_of:
                continue
            if edge.valid_to and edge.valid_to < as_of:
                continue
        keep_edges.append(edge)
    return KnowledgeBundle(nodes=keep_nodes, edges=keep_edges)


# ── analytics ────────────────────────────────────────────────────────────────

def analytics(bundle: KnowledgeBundle) -> dict[str, object]:
    """Structural facts about the graph — all counted, none estimated."""
    index = adjacency(bundle)
    degrees = {node.id: len(index.get(node.id, [])) for node in bundle.nodes}
    nodes = node_index(bundle)
    node_count = len(bundle.nodes)
    edge_count = len(bundle.edges)

    by_type: dict[str, int] = {}
    for node in bundle.nodes:
        by_type[node.type] = by_type.get(node.type, 0) + 1

    by_edge_type: dict[str, int] = {}
    provider_coverage: dict[str, int] = {}
    confidence_sum = 0.0
    for edge in bundle.edges:
        by_edge_type[edge.type] = by_edge_type.get(edge.type, 0) + 1
        confidence_sum += edge.confidence
        for provider in edge.provider.split(","):
            if provider:
                provider_coverage[provider] = provider_coverage.get(provider, 0) + 1

    # Density of a simple undirected graph: edges / (n choose 2).
    possible = node_count * (node_count - 1) / 2
    density = round(edge_count / possible, 4) if possible else 0.0

    most_connected = sorted(
        ({"id": nid, "label": nodes[nid].label, "type": nodes[nid].type, "degree": degree}
         for nid, degree in degrees.items() if degree > 0),
        key=lambda row: (-int(row["degree"]), str(row["label"]).lower()),
    )[:10]

    return {
        "nodes": node_count,
        "edges": edge_count,
        "density": density,
        "avg_confidence": round(confidence_sum / edge_count, 3) if edge_count else 0.0,
        "node_types": dict(sorted(by_type.items())),
        "edge_types": dict(sorted(by_edge_type.items())),
        "provider_coverage": dict(sorted(provider_coverage.items())),
        "most_connected": most_connected,
    }
