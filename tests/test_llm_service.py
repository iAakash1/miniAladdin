"""
Tests for the Groq LLM explanation service.

The Groq client is always mocked — these tests never touch the network.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.services import llm_service


VALID_MODEL_JSON = {
    "recommendation": "BUY",
    "confidence": 84,
    "risk": "MEDIUM",
    "summary": "The engine favors upside given RSI-14 at 28.4 and a Sharpe of 1.6.",
    "bullish_factors": ["RSI-14 at 28.4 signals oversold conditions"],
    "bearish_factors": ["SRM at 1.2 marks an elevated macro regime"],
    "reasoning": ["Oversold RSI adds +2", "Sharpe above 1.5 adds +2"],
    "limitations": ["MACD unavailable for this run"],
    "investment_horizon": "medium-term, driven by the 21-day momentum window",
    "market_outlook": "Elevated but not critical regime at SRM 1.2.",
}


def make_payload(**overrides):
    payload = {
        "ticker": "NVDA",
        "decision": {
            "recommendation": "HOLD",
            "confidence": 70,
            "risk": "HIGH",
            "verdict": "Hold",
            "rationale": "Neutral sentiment (avg score 0.05); Macro environment is ELEVATED (SRM=1.2)",
        },
        "macro": {"risk_multiplier": 1.2},
        "technicals": {"rsi_14": 28.4, "sharpe_ratio": 1.6},
        "sentiment": None,
    }
    payload.update(overrides)
    return payload


def fake_client_returning(*contents: str) -> MagicMock:
    """A stub Groq client whose successive calls return the given strings."""
    client = MagicMock()
    responses = []
    for content in contents:
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = content
        responses.append(completion)
    client.chat.completions.create.side_effect = responses
    return client


@pytest.fixture(autouse=True)
def clean_service(monkeypatch):
    """Reset client/cache and configure a fake key for each test."""
    llm_service.reset_client_for_tests()
    llm_service._missing_key_logged = False
    monkeypatch.setenv("GROQ_API_KEY", "test_key_placeholder")
    yield
    llm_service.reset_client_for_tests()


def install_client(monkeypatch, client) -> None:
    monkeypatch.setattr(llm_service, "_get_client", lambda: client)


class TestSuccessPath:
    def test_valid_response_is_parsed_and_flagged_generated(self, monkeypatch):
        client = fake_client_returning(json.dumps({**VALID_MODEL_JSON,
                                                   "recommendation": "HOLD",
                                                   "confidence": 70,
                                                   "risk": "HIGH"}))
        install_client(monkeypatch, client)

        result = llm_service.explain_recommendation(make_payload())

        assert result["generated"] is True
        assert result["cached"] is False
        assert result["summary"].startswith("The engine favors")
        assert client.chat.completions.create.call_count == 1

    def test_deterministic_fields_are_enforced_over_model_output(self, monkeypatch):
        # Model disagrees with the engine on all three deterministic fields.
        client = fake_client_returning(json.dumps(VALID_MODEL_JSON))
        install_client(monkeypatch, client)

        result = llm_service.explain_recommendation(make_payload())

        assert result["recommendation"] == "HOLD"  # engine value, not BUY
        assert result["confidence"] == 70          # engine value, not 84
        assert result["risk"] == "HIGH"            # engine value, not MEDIUM

    def test_deterministic_request_parameters(self, monkeypatch):
        client = fake_client_returning(json.dumps(VALID_MODEL_JSON))
        install_client(monkeypatch, client)

        llm_service.explain_recommendation(make_payload())

        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.2
        assert kwargs["top_p"] == 1
        assert kwargs["reasoning_effort"] == "medium"
        assert kwargs["max_completion_tokens"] == 4096
        assert kwargs["stream"] is False
        assert kwargs["response_format"] == {"type": "json_object"}


class TestFailurePaths:
    def test_invalid_json_retries_once_then_falls_back(self, monkeypatch):
        client = fake_client_returning("not json at all", "still {not json")
        install_client(monkeypatch, client)

        result = llm_service.explain_recommendation(make_payload())

        assert client.chat.completions.create.call_count == 2  # initial + 1 corrective
        assert result["generated"] is False
        assert result["recommendation"] == "HOLD"
        assert "rationale" not in result  # fallback shape matches schema keys
        assert "Neutral sentiment" in result["summary"]

    def test_invalid_then_valid_json_succeeds_on_retry(self, monkeypatch):
        client = fake_client_returning(
            "garbage",
            json.dumps({**VALID_MODEL_JSON, "recommendation": "HOLD",
                        "confidence": 70, "risk": "HIGH"}),
        )
        install_client(monkeypatch, client)

        result = llm_service.explain_recommendation(make_payload())

        assert result["generated"] is True
        assert client.chat.completions.create.call_count == 2

    def test_provider_error_falls_back_without_raising(self, monkeypatch):
        client = MagicMock()
        client.chat.completions.create.side_effect = ValueError("boom")
        install_client(monkeypatch, client)

        result = llm_service.explain_recommendation(make_payload())

        assert result["generated"] is False
        assert result["confidence"] == 70

    def test_transient_errors_retry_with_backoff(self, monkeypatch):
        class RateLimitError(Exception):
            status_code = 429

        good = json.dumps({**VALID_MODEL_JSON, "recommendation": "HOLD",
                           "confidence": 70, "risk": "HIGH"})
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.content = good

        client = MagicMock()
        client.chat.completions.create.side_effect = [RateLimitError(), completion]
        install_client(monkeypatch, client)
        monkeypatch.setattr(llm_service.time, "sleep", lambda s: None)  # no real waiting

        result = llm_service.explain_recommendation(make_payload())

        assert result["generated"] is True
        assert client.chat.completions.create.call_count == 2

    def test_unconfigured_service_serves_fallback_without_client(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        client = MagicMock()
        install_client(monkeypatch, client)

        result = llm_service.explain_recommendation(make_payload())

        assert result["generated"] is False
        client.chat.completions.create.assert_not_called()


class TestCache:
    def test_second_identical_request_is_served_from_cache(self, monkeypatch):
        client = fake_client_returning(json.dumps({**VALID_MODEL_JSON,
                                                   "recommendation": "HOLD",
                                                   "confidence": 70, "risk": "HIGH"}))
        install_client(monkeypatch, client)

        first = llm_service.explain_recommendation(make_payload())
        second = llm_service.explain_recommendation(make_payload())

        assert client.chat.completions.create.call_count == 1
        assert first["cached"] is False
        assert second["cached"] is True
        assert second["summary"] == first["summary"]

    def test_fallbacks_are_not_cached(self, monkeypatch):
        client = MagicMock()
        client.chat.completions.create.side_effect = ValueError("down")
        install_client(monkeypatch, client)

        llm_service.explain_recommendation(make_payload())
        llm_service.explain_recommendation(make_payload())

        # Both attempts hit the (failing) provider — failures never poison the cache.
        assert client.chat.completions.create.call_count == 2


class TestPayloadBuilder:
    def test_build_payload_carries_decision_and_truncates_headlines(self):
        sentiment = {
            "average_score": 0.2,
            "dominant_label": "Bullish",
            "headline_count": 12,
            "headlines": [{"title": f"h{i}", "score": 0.1, "label": "Neutral",
                           "source": "x", "url": "", "published_at": ""} for i in range(12)],
        }
        payload = llm_service.build_payload(
            ticker="NVDA", recommendation="BUY", confidence=80, risk="LOW",
            verdict="Buy", rationale="r", macro={"risk_multiplier": 1.0},
            technicals={"rsi_14": 50}, sentiment=sentiment,
        )
        assert payload["decision"]["recommendation"] == "BUY"
        assert len(payload["sentiment"]["headlines"]) == 8  # capped
        assert payload["sentiment"]["headline_count"] == 12
