"""Graph API — traversal, filtering, analytics. Pure and deterministic."""

from __future__ import annotations

from src.providers.research_schemas import GraphEdge, GraphNode, KnowledgeBundle
from src.services.graph_api import (
    adjacency,
    analytics,
    filter_graph,
    shared_neighbors,
    shortest_path,
    subgraph,
    within_hops,
)


def _graph() -> KnowledgeBundle:
    """NVDA—Jensen, NVDA—CUDA, MSFT—OpenAI—NVDA: a small connected world."""
    nodes = [
        GraphNode(id="company:NVDA", type="company", label="Nvidia"),
        GraphNode(id="person:jensen", type="person", label="Jensen Huang"),
        GraphNode(id="product:cuda", type="product", label="CUDA"),
        GraphNode(id="company:MSFT", type="company", label="Microsoft"),
        GraphNode(id="company:OPENAI", type="company", label="OpenAI"),
        GraphNode(id="country:us", type="country", label="United States"),
    ]
    edges = [
        GraphEdge(source_id="person:jensen", target_id="company:NVDA", type="ceo_of",
                  provider="wikidata", confidence=0.9, observed_at="2020-01-01"),
        GraphEdge(source_id="company:NVDA", target_id="product:cuda", type="produces",
                  provider="wikidata", confidence=0.9, observed_at="2020-01-01"),
        GraphEdge(source_id="company:NVDA", target_id="company:OPENAI", type="partners_with",
                  provider="sec", confidence=0.7, observed_at="2024-06-01"),
        GraphEdge(source_id="company:MSFT", target_id="company:OPENAI", type="owns",
                  provider="sec,wikidata", confidence=0.95, observed_at="2023-01-01"),
        GraphEdge(source_id="company:NVDA", target_id="country:us", type="headquartered_in",
                  provider="wikidata", confidence=0.9, observed_at="2020-01-01"),
        GraphEdge(source_id="company:MSFT", target_id="country:us", type="headquartered_in",
                  provider="wikidata", confidence=0.9, observed_at="2020-01-01"),
    ]
    return KnowledgeBundle(nodes=nodes, edges=edges)


class TestAdjacency:
    def test_traversal_is_undirected_but_edges_keep_direction(self):
        index = adjacency(_graph())
        assert "person:jensen" in [n for n, _ in index["company:NVDA"]]
        assert "company:NVDA" in [n for n, _ in index["person:jensen"]]
        edge = next(e for n, e in index["person:jensen"] if n == "company:NVDA")
        assert edge.source_id == "person:jensen"  # direction preserved

    def test_dangling_edges_are_not_traversable(self):
        bundle = KnowledgeBundle(
            nodes=[GraphNode(id="a", type="company", label="A")],
            edges=[GraphEdge(source_id="a", target_id="ghost", type="owns", provider="x")],
        )
        assert adjacency(bundle).get("a", []) == []

    def test_ordering_is_deterministic(self):
        graph = _graph()
        assert adjacency(graph) == adjacency(graph)


class TestWithinHops:
    def test_one_hop_returns_direct_neighbours_only(self):
        result = within_hops(_graph(), "company:NVDA", hops=1)
        ids = {n.id for n in result.nodes}
        assert ids == {"company:NVDA", "person:jensen", "product:cuda",
                       "company:OPENAI", "country:us"}
        assert "company:MSFT" not in ids  # two hops away

    def test_two_hops_reaches_msft_through_openai(self):
        ids = {n.id for n in within_hops(_graph(), "company:NVDA", hops=2).nodes}
        assert "company:MSFT" in ids

    def test_zero_hops_is_just_the_node(self):
        assert [n.id for n in within_hops(_graph(), "company:NVDA", hops=0).nodes] == ["company:NVDA"]

    def test_unknown_start_is_empty_not_error(self):
        assert within_hops(_graph(), "company:NOPE", hops=2).nodes == []

    def test_limit_is_respected(self):
        assert len(within_hops(_graph(), "company:NVDA", hops=3, limit=3).nodes) <= 3


class TestSubgraph:
    def test_only_edges_between_included_nodes_survive(self):
        result = subgraph(_graph(), ["company:NVDA", "product:cuda"])
        assert len(result.nodes) == 2
        assert len(result.edges) == 1
        assert result.edges[0].type == "produces"

    def test_unknown_ids_are_skipped(self):
        assert len(subgraph(_graph(), ["company:NVDA", "nope"]).nodes) == 1


class TestShortestPath:
    def test_finds_the_connecting_chain_with_its_edges(self):
        path = shortest_path(_graph(), "company:MSFT", "company:NVDA")
        assert [step["node"].id for step in path] == [
            "company:MSFT", "company:OPENAI", "company:NVDA",
        ]
        # Every step past the first explains HOW it connects.
        assert all("edge" in step for step in path[1:])

    def test_same_node_is_a_single_step(self):
        assert len(shortest_path(_graph(), "company:NVDA", "company:NVDA")) == 1

    def test_unreachable_returns_empty(self):
        bundle = KnowledgeBundle(
            nodes=[GraphNode(id="a", type="company", label="A"),
                   GraphNode(id="b", type="company", label="B")],
            edges=[],
        )
        assert shortest_path(bundle, "a", "b") == []

    def test_max_hops_bounds_the_search(self):
        assert shortest_path(_graph(), "person:jensen", "company:MSFT", max_hops=1) == []

    def test_is_deterministic_across_runs(self):
        graph = _graph()
        first = [s["node"].id for s in shortest_path(graph, "product:cuda", "company:MSFT")]
        second = [s["node"].id for s in shortest_path(graph, "product:cuda", "company:MSFT")]
        assert first == second


class TestSharedNeighbors:
    def test_finds_what_two_companies_have_in_common(self):
        shared = shared_neighbors(_graph(), ["company:NVDA", "company:MSFT"])
        labels = {row["node"].id for row in shared}
        assert "country:us" in labels      # both HQ'd in the US
        assert "company:OPENAI" in labels  # both connected to OpenAI

    def test_single_node_has_nothing_to_share(self):
        assert shared_neighbors(_graph(), ["company:NVDA"]) == []

    def test_the_selected_nodes_are_never_their_own_shared_neighbours(self):
        shared = shared_neighbors(_graph(), ["company:NVDA", "company:OPENAI"])
        assert all(row["node"].id not in {"company:NVDA", "company:OPENAI"} for row in shared)


class TestFiltering:
    def test_node_type_filter_drops_orphaned_edges(self):
        result = filter_graph(_graph(), node_types={"company"})
        assert all(n.type == "company" for n in result.nodes)
        assert all(e.source_id.startswith("company:") and e.target_id.startswith("company:")
                   for e in result.edges)

    def test_confidence_floor(self):
        result = filter_graph(_graph(), min_confidence=0.9)
        assert all(e.confidence >= 0.9 for e in result.edges)

    def test_provider_filter_matches_any_contributor(self):
        result = filter_graph(_graph(), providers={"sec"})
        assert result.edges  # the msft-openai edge lists "sec,wikidata"
        assert all("sec" in e.provider for e in result.edges)

    def test_time_machine_drops_edges_observed_later(self):
        # As of 2022 the NVDA-OpenAI partnership (2024) was not yet known.
        result = filter_graph(_graph(), before="2022-01-01")
        types = {e.type for e in result.edges}
        assert "partners_with" not in types
        assert "ceo_of" in types


class TestAnalytics:
    def test_counts_and_density_are_computed_not_estimated(self):
        stats = analytics(_graph())
        assert stats["nodes"] == 6
        assert stats["edges"] == 6
        assert 0 < float(stats["density"]) <= 1
        assert stats["node_types"]["company"] == 3

    def test_most_connected_is_ranked_by_degree(self):
        top = analytics(_graph())["most_connected"]
        assert top[0]["id"] == "company:NVDA"  # highest degree
        degrees = [row["degree"] for row in top]
        assert degrees == sorted(degrees, reverse=True)

    def test_provider_coverage_splits_multi_provider_edges(self):
        coverage = analytics(_graph())["provider_coverage"]
        assert coverage["sec"] == 2 and coverage["wikidata"] == 5

    def test_empty_graph_does_not_divide_by_zero(self):
        stats = analytics(KnowledgeBundle())
        assert stats["density"] == 0.0 and stats["avg_confidence"] == 0.0
