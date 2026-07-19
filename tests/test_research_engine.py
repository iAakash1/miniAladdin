"""Provider-agnostic research engine: ordering, fallback, ranking, dedup."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.services.research import engine
from src.services.research.authority import authority_of, confidence_for, is_community
from src.services.research.base import ProviderCapabilities, ResearchHit, ResearchProvider


def setup_function() -> None:
    engine.reset_for_tests()


class _Fake(ResearchProvider):
    def __init__(self, name: str, hits: list[ResearchHit], configured: bool = True, boom: bool = False):
        self.name = name
        self._hits = hits
        self._configured = configured
        self._boom = boom
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        self.calls += 1
        if self._boom:
            raise RuntimeError("provider down")
        return self._hits


def _hit(url: str, title: str = "t", provider: str = "p", snippet: str = "") -> ResearchHit:
    return ResearchHit(url=url, title=title, snippet=snippet, provider=provider)


class TestAuthority:
    def test_tier_ordering_is_strict(self):
        assert authority_of("https://sec.gov/filing") > authority_of("https://federalreserve.gov/x")
        assert authority_of("https://federalreserve.gov/x") > authority_of("https://investor.apple.com/q")
        assert authority_of("https://investor.apple.com/q") > authority_of("https://reuters.com/a")
        assert authority_of("https://reuters.com/a") > authority_of("https://morningstar.com/a")
        assert authority_of("https://morningstar.com/a") > authority_of("https://unknown-site.io/a")
        assert authority_of("https://unknown-site.io/a") > authority_of("https://reddit.com/r/x")

    def test_community_never_outranks_authoritative(self):
        assert is_community("https://reddit.com/r/stocks")
        assert not is_community("https://sec.gov/x")
        assert confidence_for("https://reddit.com/r/x") < confidence_for("https://reuters.com/a")

    def test_web_confidence_never_rivals_the_deterministic_record(self):
        # SEC XBRL is 1.0 and Wikidata 0.9 — no web source may reach those.
        for url in ["https://sec.gov/x", "https://reuters.com/a", "https://investor.apple.com/q"]:
            assert confidence_for(url) <= 0.75

    def test_subdomains_inherit_their_parent_tier(self):
        assert authority_of("https://www.reuters.com/x") == authority_of("https://reuters.com/x")
        assert authority_of("https://old.reddit.com/r/x") == authority_of("https://reddit.com/r/x")


class TestOrdering:
    def test_default_order_is_used_when_env_is_unset(self, monkeypatch):
        monkeypatch.delenv("RESEARCH_PROVIDER_ORDER", raising=False)
        assert engine.configured_order() == engine.DEFAULT_ORDER

    def test_env_overrides_order_without_code_change(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PROVIDER_ORDER", "exa, brave")
        assert engine.configured_order() == ["exa", "brave"]

    def test_unknown_provider_names_are_ignored(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PROVIDER_ORDER", "nonsense, exa")
        assert engine.configured_order() == ["exa"]

    def test_entirely_invalid_order_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PROVIDER_ORDER", "nope, nada")
        assert engine.configured_order() == engine.DEFAULT_ORDER


class TestFallback:
    def test_unconfigured_provider_is_skipped_and_next_one_answers(self):
        down = _Fake("down", [], configured=False)
        up = _Fake("up", [_hit("https://reuters.com/a")])
        with patch.object(engine, "providers_in_order", return_value=[down, up]):
            hits = engine.search("q")
        assert down.calls == 0 and up.calls == 1
        assert len(hits) == 1

    def test_failing_provider_never_breaks_the_chain(self):
        boom = _Fake("boom", [], boom=True)
        up = _Fake("up", [_hit("https://reuters.com/a")])
        with patch.object(engine, "providers_in_order", return_value=[boom, up]):
            hits = engine.search("q")
        assert len(hits) == 1  # the crash is absorbed

    def test_every_provider_failing_returns_empty_not_error(self):
        boom = _Fake("boom", [], boom=True)
        with patch.object(engine, "providers_in_order", return_value=[boom]):
            assert engine.search("q") == []
            assert engine.research_company("NVDA").claims == []

    def test_chain_stops_once_enough_evidence_is_gathered(self):
        many = _Fake("many", [_hit(f"https://site{i}.com/a") for i in range(engine.TARGET_HITS)])
        extra = _Fake("extra", [_hit("https://late.com/a")])
        with patch.object(engine, "providers_in_order", return_value=[many, extra]):
            engine.search("q")
        assert extra.calls == 0  # not consulted — no duplicate work


class TestMergeAndRank:
    def test_results_are_ranked_by_source_authority_not_provider_order(self):
        low = _Fake("low", [_hit("https://reddit.com/r/x", "community")])
        high = _Fake("high", [_hit("https://sec.gov/f", "filing")])
        with patch.object(engine, "providers_in_order", return_value=[low, high]):
            hits = engine.search("q")
        assert hits[0].title == "filing"  # authority wins over chain position

    def test_same_url_from_two_providers_appears_once(self):
        a = _Fake("a", [_hit("https://reuters.com/story", snippet="short")])
        b = _Fake("b", [_hit("https://reuters.com/story?utm_source=x", snippet="a much longer extract")])
        with patch.object(engine, "providers_in_order", return_value=[a, b]):
            hits = engine.search("q")
        assert len(hits) == 1
        assert "longer" in hits[0].snippet  # richer extract kept

    def test_non_http_urls_are_dropped(self):
        junk = _Fake("junk", [_hit("javascript:alert(1)"), _hit("https://ok.com/a")])
        with patch.object(engine, "providers_in_order", return_value=[junk]):
            assert len(engine.search("q")) == 1


class TestNormalization:
    def test_claims_carry_source_derived_confidence_and_evidence(self):
        provider = _Fake("x", [_hit(
            "https://reuters.com/a", "Title",
            snippet="Nvidia reported record data center revenue for the quarter, beating estimates.",
        )])
        with patch.object(engine, "providers_in_order", return_value=[provider]):
            bundle = engine.research_company("NVDA")
        assert bundle.claims
        claim = bundle.claims[0]
        assert claim.confidence == confidence_for("https://reuters.com/a")
        assert claim.evidence[0].source.url == "https://reuters.com/a"

    def test_provider_identity_does_not_leak_into_claim_confidence(self):
        # Same URL through two different providers → identical confidence.
        one = _Fake("one", [_hit("https://reuters.com/a", "T", snippet="x" * 60)])
        two = _Fake("two", [_hit("https://reuters.com/a", "T", snippet="x" * 60)])
        with patch.object(engine, "providers_in_order", return_value=[one]):
            first = engine.research_company("NVDA")
        engine.reset_for_tests()
        with patch.object(engine, "providers_in_order", return_value=[two]):
            second = engine.research_company("NVDA")
        assert [c.confidence for c in first.claims] == [c.confidence for c in second.claims]


class TestHealth:
    def test_health_reports_every_provider_without_exposing_keys(self):
        rows = engine.health()
        assert {r["name"] for r in rows} == set(engine.DEFAULT_ORDER)
        serialized = str(rows).lower()
        assert "api_key" not in serialized and "token" not in serialized
