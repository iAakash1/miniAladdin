"""
Knowledge graph engine — merges KnowledgeBundles from every provider into
one canonical, deduplicated view.

The merge rules are the whole point of this module:

  * Nodes are canonical by id. When two providers describe the same node,
    fields are filled in rather than overwritten (first non-empty wins for
    description/route; metadata unions, so `sec` and `wikidata` provenance
    coexist on one node).
  * Edges are canonical by (source, type, target). Corroboration is real
    signal: an edge asserted by N providers gets its confidence raised,
    and every contributing provider is recorded.
  * Nothing is invented. If no provider asserted it, it is not in the graph.

Pure functions over pydantic models — no I/O, fully unit-testable.
"""

from __future__ import annotations

from typing import Iterable

from src.providers.research_schemas import (
    GraphEdge,
    GraphNode,
    KnowledgeBundle,
    ResearchClaim,
    ResearchFinding,
    TimelineEvent,
)


def merge_bundles(bundles: Iterable[KnowledgeBundle]) -> KnowledgeBundle:
    """Fuse many providers' output into one deduplicated bundle."""
    nodes: dict[str, GraphNode] = {}
    edges: dict[tuple[str, str, str], GraphEdge] = {}
    edge_providers: dict[tuple[str, str, str], set[str]] = {}
    findings: dict[str, ResearchFinding] = {}
    claims: dict[str, ResearchClaim] = {}
    events: dict[str, TimelineEvent] = {}

    for bundle in bundles:
        for node in bundle.nodes:
            existing = nodes.get(node.id)
            if existing is None:
                nodes[node.id] = node.model_copy(deep=True)
                continue
            # Enrich, never clobber: a later provider fills the gaps a
            # previous one left.
            if not existing.description and node.description:
                existing.description = node.description
            if not existing.route and node.route:
                existing.route = node.route
            existing.metadata = {**node.metadata, **existing.metadata}

        for edge in bundle.edges:
            key = (edge.source_id, edge.type, edge.target_id)
            providers = edge_providers.setdefault(key, set())
            providers.add(edge.provider)
            existing = edges.get(key)
            if existing is None:
                edges[key] = edge.model_copy(deep=True)
            else:
                # Corroboration handled by the confidence policy — the one
                # place that decides any confidence number.
                from src.services.confidence import score as _score

                existing.confidence = _score(
                    edge.provider,
                    source_authority=max(existing.confidence, edge.confidence),
                    corroborating_providers=len(providers),
                ).value
                if edge.observed_at > existing.observed_at:
                    existing.observed_at = edge.observed_at

        for finding in bundle.findings:
            findings.setdefault(finding.id, finding)
        for claim in bundle.claims:
            existing_claim = claims.get(claim.id)
            if existing_claim is None:
                claims[claim.id] = claim.model_copy(deep=True)
            else:
                # Same statement corroborated by another source: union the
                # evidence rather than keeping one arbitrary copy.
                known = {e.source.url for e in existing_claim.evidence}
                existing_claim.evidence.extend(e for e in claim.evidence if e.source.url not in known)
        for event in bundle.events:
            events.setdefault(event.id, event)

    for key, edge in edges.items():
        provider_list = sorted(edge_providers.get(key, {edge.provider}))
        edge.provider = ",".join(provider_list)

    return KnowledgeBundle(
        nodes=sorted(nodes.values(), key=lambda n: (n.type, n.label)),
        edges=sorted(edges.values(), key=lambda e: (e.source_id, e.type, e.target_id)),
        findings=sorted(findings.values(), key=lambda f: f.label),
        claims=sorted(claims.values(), key=lambda c: c.id),
        events=sorted(events.values(), key=lambda e: e.date, reverse=True),
    )


def neighbors(bundle: KnowledgeBundle, node_id: str) -> list[dict[str, object]]:
    """Everything adjacent to a node, in either direction, with the edge
    that connects it — the data behind "no dead ends"."""
    by_id = {node.id: node for node in bundle.nodes}
    out: list[dict[str, object]] = []
    for edge in bundle.edges:
        if edge.source_id == node_id:
            other = by_id.get(edge.target_id)
            direction = "out"
        elif edge.target_id == node_id:
            other = by_id.get(edge.source_id)
            direction = "in"
        else:
            continue
        if other is None:
            continue
        out.append({
            "node": other,
            "edge_type": edge.type,
            "direction": direction,
            "confidence": edge.confidence,
            "provider": edge.provider,
        })
    out.sort(key=lambda item: (-float(item["confidence"]), str(item["edge_type"])))
    return out


def timeline(bundle: KnowledgeBundle, limit: int = 40) -> list[TimelineEvent]:
    """One chronological view over every provider's dated events."""
    return sorted(
        (event for event in bundle.events if event.date),
        key=lambda event: event.date,
        reverse=True,
    )[:limit]
