"""Graph traversal service — routing and shape (hermetic)."""

from __future__ import annotations

from unittest.mock import patch

from src.providers.research_schemas import GraphEdge, GraphNode, KnowledgeBundle
from src.services import graph_service


def setup_function() -> None:
    graph_service.reset_for_tests()


class TestRouting:
    def test_company_nodes_expand_through_the_company_engine(self):
        with patch.object(graph_service.company_intelligence, "build", return_value={
            "ecosystem": [{"key": "leadership", "label": "Leadership", "members": [
                {"id": "person:x", "label": "X", "type": "person", "route": None,
                 "edges": ["ceo_of"], "confidence": 0.9, "provider": "wikidata"},
            ]}],
            "timeline": [], "findings": [],
        }) as build:
            result = graph_service.expand("company:NVDA")
        build.assert_called_once_with("NVDA")
        assert result["center"]["id"] == "company:NVDA"
        assert result["edges"][0]["node"]["label"] == "X"

    def test_non_company_nodes_expand_through_wikidata(self):
        bundle = KnowledgeBundle(
            nodes=[
                GraphNode(id="person:jensen", type="person", label="Jensen Huang"),
                GraphNode(id="company:NVDA", type="company", label="Nvidia", route="/company/NVDA"),
            ],
            edges=[GraphEdge(source_id="company:NVDA", target_id="person:jensen",
                             type="ceo_of", provider="wikidata", confidence=0.9)],
        )
        with patch.object(graph_service, "_resolve_qid", return_value="Q123"), \
             patch.object(graph_service._wikidata, "expand_entity", return_value=bundle):
            result = graph_service.expand("person:jensen", "Jensen Huang")
        assert len(result["edges"]) == 1
        assert result["edges"][0]["node"]["route"] == "/company/NVDA"
        assert result["edges"][0]["group"] == "Leadership"

    def test_unresolvable_node_returns_empty_slice_not_error(self):
        with patch.object(graph_service, "_resolve_qid", return_value=""):
            result = graph_service.expand("product:unknown-thing", "Unknown Thing")
        assert result["edges"] == []
        assert result["center"]["label"] == "Unknown Thing"

    def test_malformed_node_id_is_handled(self):
        assert graph_service.expand("")["edges"] == []
        assert graph_service.expand("no-colon")["edges"] == []

    def test_results_are_cached_per_node(self):
        with patch.object(graph_service.company_intelligence, "build",
                          return_value={"ecosystem": [], "timeline": [], "findings": []}) as build:
            graph_service.expand("company:AAPL")
            graph_service.expand("company:AAPL")
        assert build.call_count == 1


class TestQidMemory:
    def test_qids_travel_with_nodes_so_expansion_skips_label_lookup(self):
        graph_service.remember_qids([
            GraphNode(id="product:cuda", type="product", label="CUDA", metadata={"qid": "Q477690"}),
        ])
        bundle = KnowledgeBundle(nodes=[GraphNode(id="product:cuda", type="product", label="CUDA")])
        with patch.object(graph_service, "_resolve_qid") as resolve, \
             patch.object(graph_service._wikidata, "expand_entity", return_value=bundle):
            graph_service.expand("product:cuda")
        resolve.assert_not_called()
