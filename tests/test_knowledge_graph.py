"""Knowledge graph merge semantics + company intelligence composition."""

from __future__ import annotations

from src.providers.research_schemas import (
    GraphEdge,
    GraphNode,
    KnowledgeBundle,
    ResearchFinding,
    TimelineEvent,
)
from src.services.knowledge_graph import merge_bundles, neighbors, timeline


def _bundle(nodes=None, edges=None, findings=None, events=None) -> KnowledgeBundle:
    return KnowledgeBundle(
        nodes=nodes or [], edges=edges or [], findings=findings or [], events=events or []
    )


class TestNodeMerge:
    def test_same_node_from_two_providers_becomes_one(self):
        a = _bundle([GraphNode(id="company:NVDA", type="company", label="NVIDIA", metadata={"source": "sec"})])
        b = _bundle([GraphNode(id="company:NVDA", type="company", label="NVIDIA",
                               description="GPU maker", route="/company/NVDA",
                               metadata={"source": "wikidata"})])
        merged = merge_bundles([a, b])
        assert len(merged.nodes) == 1
        node = merged.nodes[0]
        # Gaps filled, provenance unioned — neither provider clobbers the other.
        assert node.description == "GPU maker"
        assert node.route == "/company/NVDA"
        assert node.metadata["source"] in {"sec", "wikidata"}

    def test_distinct_nodes_preserved(self):
        merged = merge_bundles([
            _bundle([GraphNode(id="company:NVDA", type="company", label="NVIDIA")]),
            _bundle([GraphNode(id="person:jensen-huang", type="person", label="Jensen Huang")]),
        ])
        assert len(merged.nodes) == 2


class TestEdgeMerge:
    def test_corroborated_edge_gains_confidence_and_records_providers(self):
        edge_a = GraphEdge(source_id="person:x", target_id="company:NVDA", type="ceo_of",
                           provider="wikidata", confidence=0.9)
        edge_b = GraphEdge(source_id="person:x", target_id="company:NVDA", type="ceo_of",
                           provider="sec", confidence=0.9)
        merged = merge_bundles([_bundle(edges=[edge_a]), _bundle(edges=[edge_b])])
        assert len(merged.edges) == 1
        assert merged.edges[0].confidence > 0.9
        assert merged.edges[0].provider == "sec,wikidata"

    def test_confidence_never_reaches_certainty(self):
        edges = [
            GraphEdge(source_id="a", target_id="b", type="owns", provider=f"p{i}", confidence=0.99)
            for i in range(8)
        ]
        merged = merge_bundles([_bundle(edges=[e]) for e in edges])
        assert merged.edges[0].confidence <= 0.99

    def test_different_edge_types_are_not_merged(self):
        merged = merge_bundles([_bundle(edges=[
            GraphEdge(source_id="a", target_id="b", type="owns", provider="w"),
            GraphEdge(source_id="a", target_id="b", type="competes_with", provider="w"),
        ])])
        assert len(merged.edges) == 2


class TestNeighbors:
    def test_traverses_both_directions_with_edge_context(self):
        bundle = _bundle(
            nodes=[
                GraphNode(id="company:NVDA", type="company", label="NVIDIA"),
                GraphNode(id="person:jensen", type="person", label="Jensen Huang"),
                GraphNode(id="product:cuda", type="product", label="CUDA"),
            ],
            edges=[
                GraphEdge(source_id="person:jensen", target_id="company:NVDA", type="ceo_of", provider="wikidata"),
                GraphEdge(source_id="company:NVDA", target_id="product:cuda", type="produces", provider="wikidata"),
            ],
        )
        found = neighbors(bundle, "company:NVDA")
        assert {item["node"].id for item in found} == {"person:jensen", "product:cuda"}
        directions = {item["node"].id: item["direction"] for item in found}
        assert directions["person:jensen"] == "in"
        assert directions["product:cuda"] == "out"

    def test_dangling_edges_are_skipped(self):
        bundle = _bundle(
            nodes=[GraphNode(id="company:NVDA", type="company", label="NVIDIA")],
            edges=[GraphEdge(source_id="company:NVDA", target_id="person:ghost", type="ceo_of", provider="w")],
        )
        assert neighbors(bundle, "company:NVDA") == []


class TestTimeline:
    def test_newest_first_and_undated_dropped(self):
        bundle = _bundle(events=[
            TimelineEvent(id="1", date="2026-01-15", kind="filing", title="10-K filed"),
            TimelineEvent(id="2", date="2026-07-01", kind="filing", title="10-Q filed"),
            TimelineEvent(id="3", date="", kind="filing", title="undated"),
        ])
        events = timeline(bundle)
        assert [e.id for e in events] == ["2", "1"]

    def test_duplicate_events_collapse(self):
        event = TimelineEvent(id="same", date="2026-01-01", kind="filing", title="10-K")
        merged = merge_bundles([_bundle(events=[event]), _bundle(events=[event])])
        assert len(merged.events) == 1


class TestDeterminism:
    def test_merge_is_order_independent_for_nodes_and_edges(self):
        a = _bundle(
            [GraphNode(id="company:X", type="company", label="X")],
            [GraphEdge(source_id="company:X", target_id="industry:tech", type="belongs_to", provider="wikidata")],
            [ResearchFinding(id="f1", label="Revenue", text="up")],
        )
        b = _bundle(
            [GraphNode(id="industry:tech", type="industry", label="Technology")],
            [GraphEdge(source_id="company:X", target_id="industry:tech", type="belongs_to", provider="sec")],
        )
        forward = merge_bundles([a, b])
        backward = merge_bundles([b, a])
        assert [n.id for n in forward.nodes] == [n.id for n in backward.nodes]
        assert [e.provider for e in forward.edges] == [e.provider for e in backward.edges]
