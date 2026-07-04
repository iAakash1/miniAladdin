"""Tests for the evidence pipeline and the citation-audited memo service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services import evidence as ev
from src.services import llm_service, memo_service
from src.providers.schemas import NewsHeadline, ProviderResult, SearchResult


NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def headline(title, url="https://reuters.com/x", published="2026-07-04T09:00:00Z", summary=""):
    return NewsHeadline(title=title, source="Reuters", url=url, published_at=published, summary=summary)


class TestReliability:
    def test_tiering(self):
        assert ev.reliability_of("https://www.reuters.com/a") == 1.0
        assert ev.reliability_of("https://www.cnbc.com/a") == 0.85
        assert ev.reliability_of("https://seekingalpha.com/a") == 0.65
        assert ev.reliability_of("https://randomblog.io/a") == ev.DEFAULT_RELIABILITY
        assert ev.reliability_of("https://reddit.com/r/stocks") == ev.UGC_RELIABILITY

    def test_recency_decay_half_life(self):
        fresh = ev.recency_of("2026-07-04T12:00:00Z", now=NOW)
        two_days = ev.recency_of("2026-07-02T12:00:00Z", now=NOW)
        assert fresh == pytest.approx(1.0, abs=0.01)
        assert two_days == pytest.approx(0.5, abs=0.02)
        assert ev.recency_of("", now=NOW) == 0.5  # unknown date is neutral


class TestCollectEvidence:
    def test_dedupes_ranks_and_assigns_ids(self):
        news = [
            headline("NVDA surges on record earnings"),
            headline("NVDA surges on record earnings!!", url="https://fool.com/dup"),  # dup title
            headline("Old story", url="https://randomblog.io/old", published="2026-06-20T00:00:00Z"),
        ]
        search = [SearchResult(title="NVDA outlook deep dive", url="https://wsj.com/dive",
                               snippet="NVDA analysis", published_at="2026-07-04T08:00:00Z")]
        with patch.object(ev.providers.news, "get_news",
                          return_value=ProviderResult(data=news, source="newsapi", confidence=0.85)), \
             patch.object(ev.providers.search, "search",
                          return_value=ProviderResult(data=search, source="tavily", confidence=0.85)):
            items = ev.collect_evidence("NVDA", "NVIDIA", now=NOW)

        titles = [item.title for item in items]
        assert "NVDA surges on record earnings!!" not in titles  # deduped
        assert [item.id for item in items] == [f"E{i}" for i in range(1, len(items) + 1)]
        # Reliable + fresh + relevant outranks stale unknown-domain item
        assert items[0].rank_score >= items[-1].rank_score
        assert items[-1].title == "Old story"

    def test_provider_failures_yield_empty_list(self):
        with patch.object(ev.providers.news, "get_news", side_effect=RuntimeError("down")), \
             patch.object(ev.providers.search, "search", side_effect=RuntimeError("down")):
            assert ev.collect_evidence("NVDA") == []


RESEARCH = {
    "ticker": "NVDA",
    "verdict": "Buy",
    "confidence": 78,
    "confidence_breakdown": [],
    "risk_level": "MEDIUM",
    "rationale": "Composite score +0.22",
    "quant": {"raw_score": 0.22, "momentum_score": 0.4, "macro_gate": 0.9},
    "macro": {"risk_multiplier": 1.1},
    "technicals": {"company_name": "NVIDIA Corporation", "rsi_14": 55.0},
    "disclaimer": "Research only.",
}

VALID_MEMO = {
    "executive_summary": "Engine favors upside with composite +0.22; earnings beat supports it [E1].",
    "investment_thesis": "Momentum 0.4 with strong demand [E1].",
    "catalysts": ["Next earnings [E1]"],
    "headwinds": ["Valuation stretched per coverage [E2]"],
    "competitive_position": "No competitor coverage was supplied in evidence.",
    "industry_outlook": "Sector coverage constructive [E2].",
    "macro_impact": "SRM 1.1, mildly elevated; gate 0.9 trims bullish score.",
    "valuation": "No PE supplied for this run.",
    "technical_picture": "Momentum score 0.4.",
    "fundamental_picture": "RSI 55 neutral.",
    "institutional_activity": "No institutional evidence was supplied.",
    "analyst_consensus": "No analyst target supplied.",
    "risk_factors": ["Macro gate at 0.9"],
    "counter_arguments": ["Momentum could fade without follow-through [E2]"],
    "scenario_analysis": {
        "best_case": "Earnings strength continues [E1].",
        "base_case": "Buy verdict holds at composite +0.22.",
        "worst_case": "Valuation concerns dominate [E2].",
    },
}

TWO_ITEMS = [
    ev.EvidenceItem(id="E1", title="Earnings beat", url="https://reuters.com/a",
                    source="Reuters", reliability=1.0),
    ev.EvidenceItem(id="E2", title="Valuation worry", url="https://wsj.com/b",
                    source="WSJ", reliability=1.0),
]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    memo_service.reset_for_tests()
    llm_service.reset_client_for_tests()
    monkeypatch.setenv("GROQ_API_KEY", "test_key_placeholder")
    yield
    memo_service.reset_for_tests()
    llm_service.reset_client_for_tests()


def stub_llm(monkeypatch, *replies: str):
    calls = {"n": 0}

    def fake(messages):
        reply = replies[min(calls["n"], len(replies) - 1)]
        calls["n"] += 1
        return reply, 0

    monkeypatch.setattr(llm_service, "_call_with_retries", fake)
    return calls


class TestMemoService:
    def test_valid_memo_attaches_deterministic_fields(self, monkeypatch):
        monkeypatch.setattr(memo_service, "collect_evidence", lambda *a, **k: list(TWO_ITEMS))
        stub_llm(monkeypatch, json.dumps(VALID_MEMO))

        memo = memo_service.generate_memo(RESEARCH)

        assert memo["generated"] is True
        assert memo["final_recommendation"] == "Buy"      # engine, not model
        assert memo["confidence"] == 78                    # engine, not model
        attribution = {row["id"]: row for row in memo["source_attribution"]}
        assert attribution["E1"]["cited"] is True
        assert attribution["E2"]["cited"] is True
        assert memo["prompt_version"] == memo_service.MEMO_PROMPT_VERSION

    def test_invented_citation_fails_then_retry_succeeds(self, monkeypatch):
        monkeypatch.setattr(memo_service, "collect_evidence", lambda *a, **k: list(TWO_ITEMS))
        bad = {**VALID_MEMO, "executive_summary": "Great quarter [E9]."}  # E9 doesn't exist
        calls = stub_llm(monkeypatch, json.dumps(bad), json.dumps(VALID_MEMO))

        memo = memo_service.generate_memo(RESEARCH)

        assert calls["n"] == 2  # corrective retry happened
        assert memo["generated"] is True

    def test_persistent_invalid_output_falls_back(self, monkeypatch):
        monkeypatch.setattr(memo_service, "collect_evidence", lambda *a, **k: list(TWO_ITEMS))
        stub_llm(monkeypatch, "not json", "still not json")

        memo = memo_service.generate_memo(RESEARCH)

        assert memo["generated"] is False
        assert memo["final_recommendation"] == "Buy"
        assert "unavailable" in memo["executive_summary"]
        assert memo["scenario_analysis"]["base_case"].startswith("Engine verdict")
        assert len(memo["source_attribution"]) == 2  # attribution survives fallback

    def test_unconfigured_llm_serves_fallback(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setattr(memo_service, "collect_evidence", lambda *a, **k: list(TWO_ITEMS))

        memo = memo_service.generate_memo(RESEARCH)

        assert memo["generated"] is False
        assert memo["evidence_count"] == 2

    def test_memo_cache_hit(self, monkeypatch):
        monkeypatch.setattr(memo_service, "collect_evidence", lambda *a, **k: list(TWO_ITEMS))
        stub_llm(monkeypatch, json.dumps(VALID_MEMO))

        first = memo_service.generate_memo(RESEARCH)
        second = memo_service.generate_memo(RESEARCH)

        assert first["cached"] is False
        assert second["cached"] is True
