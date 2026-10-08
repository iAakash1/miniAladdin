"""The knowledge graph says when it could not look.

`company_intelligence.build` composes four independent sources and every one
of them is optional - research must never break analysis. That left no way to
tell a source that found nothing from a source that could not be reached, and
the merged result was cached for six hours either way. A thirty-second Wikidata
timeout therefore read as "this company has no ecosystem" until the evening.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.providers.research_schemas import GraphEdge, GraphNode, KnowledgeBundle
from src.providers.vendors.sec_vendor import SECVendor
from src.services import company_intelligence as ci
from src.services import graph_service
from src.services.research import engine as research_engine


def _bundle() -> KnowledgeBundle:
    return KnowledgeBundle(
        nodes=[GraphNode(id="company:AAPL", type="company", label="Apple Inc.", route="/company/AAPL"),
               GraphNode(id="person:tim-cook", type="person", label="Tim Cook")],
        edges=[GraphEdge(source_id="person:tim-cook", target_id="company:AAPL", type="ceo_of", provider="wikidata")],
    )


@pytest.fixture(autouse=True)
def _clean():
    ci.reset_for_tests()
    graph_service.reset_for_tests()
    yield
    ci.reset_for_tests()
    graph_service.reset_for_tests()


class _Sources:
    """Replace the four sources with scripted callables and count the calls."""

    def __init__(self, sec, wikidata, research):
        self.calls = {"sec": 0, "wikidata": 0, "research": 0}
        self.script = {"sec": sec, "wikidata": wikidata, "research": research}

    def _run(self, name):
        self.calls[name] += 1
        outcome = self.script[name]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def __enter__(self):
        self._patches = [
            patch.object(ci._sec, "get_knowledge", lambda symbol: self._run("sec")),
            patch.object(ci._wikidata, "get_knowledge", lambda symbol, name="": self._run("wikidata")),
            patch.object(ci, "_research", lambda symbol, name: self._run("research")),
            patch.object(ci.identity.openfigi.__class__, "available", property(lambda self: False)),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()


def test_when_every_source_is_down_the_answer_is_unavailable_not_an_empty_ecosystem():
    down = RuntimeError("timeout")
    with _Sources(down, down, down):
        result = ci.build("AAPL")
    assert result["status"] == "unavailable"
    assert set(result["sources"].values()) == {"unavailable"}
    assert result["ecosystem"] == [] and result["graph"]["nodes"] == 0


def test_an_unavailable_answer_is_not_cached_so_recovery_is_seen_at_once():
    down = RuntimeError("timeout")
    with _Sources(down, down, down) as outage:
        ci.build("AAPL")
    with _Sources(KnowledgeBundle(), _bundle(), KnowledgeBundle()) as recovered:
        result = ci.build("AAPL")
    assert result["status"] == "complete"
    assert result["graph"]["nodes"] > 0, "the outage was served again after the source recovered"
    assert recovered.calls["wikidata"] == 1 and outage.calls["wikidata"] == 1


def test_one_source_down_is_partial_and_names_which():
    with _Sources(KnowledgeBundle(), RuntimeError("timeout"), KnowledgeBundle()):
        result = ci.build("AAPL")
    assert result["status"] == "partial"
    assert result["sources"]["wikidata"] == "unavailable"
    assert result["sources"]["sec"] == "empty"


def test_sources_that_answered_nothing_are_complete_not_unavailable():
    """They were asked, and said there is nothing. That is a finding."""
    with _Sources(KnowledgeBundle(), KnowledgeBundle(), KnowledgeBundle()):
        result = ci.build("ZZZZ")
    assert result["status"] == "complete"
    assert set(result["sources"].values()) == {"empty"}


def test_a_complete_answer_is_cached_and_a_partial_one_is_held_only_briefly():
    with _Sources(KnowledgeBundle(), _bundle(), KnowledgeBundle()) as whole:
        ci.build("AAPL")
        ci.build("AAPL")
    assert whole.calls["wikidata"] == 1, "a complete answer was not cached"

    ci.reset_for_tests()
    with _Sources(KnowledgeBundle(), RuntimeError("x"), KnowledgeBundle()):
        ci.build("MSFT")
        stored = ci._cache["MSFT"][0] - __import__("time").time()
    assert 0 < stored <= ci.DEGRADED_TTL_SECONDS + 1, (
        f"a partial answer was held for {stored:.0f}s; it must not outlive the degraded window"
    )
    assert ci.DEGRADED_TTL_SECONDS < ci.CACHE_TTL_SECONDS / 100


# ── the research engine reports whether its providers could answer ───────────

class _Provider:
    def __init__(self, name, hits=None, boom=False, configured=True):
        self.name, self._hits, self._boom, self._configured = name, hits or [], boom, configured

    def is_configured(self):
        return self._configured

    def capabilities(self):
        from src.services.research.base import ProviderCapabilities
        return ProviderCapabilities(search=True)

    def search(self, query, limit=6):
        if self._boom:
            raise RuntimeError("provider down")
        return self._hits


def _hit(url):
    from src.services.research.base import ResearchHit
    return ResearchHit(url=url, title="A sufficiently long headline about the company", snippet="A long enough snippet. " * 4, provider="x")


def test_every_research_provider_failing_is_reported_unavailable_but_still_returns_a_bundle():
    with patch.object(research_engine, "providers_in_order", return_value=[_Provider("a", boom=True), _Provider("b", boom=True)]):
        bundle, outcome = research_engine.research_company_checked("AAPL", "Apple")
    assert bundle.claims == []                       # the public contract: never raises
    assert outcome.unavailable is True and outcome.attempted == 2 and sorted(outcome.failed) == ["a", "b"]


def test_a_provider_that_found_nothing_is_not_a_failure():
    with patch.object(research_engine, "providers_in_order", return_value=[_Provider("a", hits=[])]):
        _bundle_, outcome = research_engine.research_company_checked("AAPL", "Apple")
    assert outcome.unavailable is False and outcome.failed == []


def test_one_provider_failing_among_working_ones_is_not_unavailable():
    ok = _Provider("ok", hits=[_hit("https://www.reuters.com/a")])
    with patch.object(research_engine, "providers_in_order", return_value=[_Provider("bad", boom=True), ok]):
        bundle, outcome = research_engine.research_company_checked("AAPL", "Apple")
    assert outcome.unavailable is False and outcome.failed == ["bad"]
    assert bundle.claims, "the working provider's evidence was lost"


def test_nothing_configured_is_not_an_outage_nobody_was_asked():
    with patch.object(research_engine, "providers_in_order", return_value=[_Provider("a", configured=False)]):
        _bundle_, outcome = research_engine.research_company_checked("AAPL", "Apple")
    assert outcome.attempted == 0 and outcome.unavailable is False


def test_the_unchecked_entry_point_keeps_its_contract():
    with patch.object(research_engine, "providers_in_order", return_value=[_Provider("a", boom=True)]):
        assert research_engine.research_company("AAPL").claims == []
        assert research_engine.search("q") == []


# ── graph expansion ───────────────────────────────────────────────────────────

def test_a_failed_label_lookup_is_unavailable_and_is_not_remembered():
    with patch.object(graph_service, "_resolve_qid", side_effect=RuntimeError("timeout")):
        failed = graph_service.expand("product:iphone", "iPhone")
    assert failed["status"] == "unavailable" and failed["edges"] == []
    bundle = KnowledgeBundle(
        nodes=[GraphNode(id="person:x", type="person", label="X")],
        edges=[GraphEdge(source_id="product:iphone", target_id="person:x", type="owns", provider="wikidata")],
    )
    with patch.object(graph_service, "_resolve_qid", return_value="Q123"), \
         patch.object(graph_service._wikidata, "expand_entity", return_value=bundle):
        recovered = graph_service.expand("product:iphone", "iPhone")
    assert recovered["status"] == "complete" and recovered["edges"], (
        "the failed lookup was cached and the recovery was never seen"
    )


def test_no_such_entity_is_a_complete_empty_answer_and_is_cached():
    with patch.object(graph_service, "_resolve_qid", return_value="") as resolve:
        first = graph_service.expand("concept:nothing-here", "Nothing Here")
        graph_service.expand("concept:nothing-here", "Nothing Here")
    assert first["status"] == "complete" and first["edges"] == []
    assert resolve.call_count == 1


def test_a_failed_expansion_after_a_successful_lookup_is_unavailable():
    with patch.object(graph_service, "_resolve_qid", return_value="Q1"), \
         patch.object(graph_service._wikidata, "expand_entity", side_effect=RuntimeError("503")):
        result = graph_service.expand("product:azure", "Azure")
    assert result["status"] == "unavailable"


def test_the_workspace_names_the_company_it_could_not_look_up():
    ok = _bundle()

    def lookup(symbol, name=""):
        if symbol == "MSFT":
            raise RuntimeError("timeout")
        return ok

    with patch.object(graph_service._wikidata, "get_knowledge", side_effect=lookup):
        result = graph_service.workspace(["AAPL", "MSFT"], hops=1)
    assert result["status"] == "partial" and result["unavailable_symbols"] == ["MSFT"]

    graph_service.reset_for_tests()   # the partial answer is (briefly) cached by design
    with patch.object(graph_service._wikidata, "get_knowledge", side_effect=RuntimeError("down")):
        total = graph_service.workspace(["AAPL", "MSFT"], hops=1)
    assert total["status"] == "unavailable"


def test_a_company_expansion_carries_the_ecosystem_status_through():
    with patch.object(ci, "build", return_value={"ecosystem": [], "timeline": [], "findings": [],
                                                 "status": "partial", "sources": {"wikidata": "unavailable"}}):
        result = graph_service.expand("company:AAPL")
    assert result["status"] == "partial" and result["sources"] == {"wikidata": "unavailable"}
