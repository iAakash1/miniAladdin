"""The depth endpoint re-explains a held evidence snapshot and nothing else."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.services import narrative_pipeline as pipeline
from src.services.clerk_auth import require_clerk_user


def _payload():
    return {
        "ticker": "NVDA",
        "decision": {
            "recommendation": "HOLD", "confidence": 70, "risk": "HIGH", "verdict": "Hold",
            "rationale": "Macro conditions offset momentum.",
            "confidence_breakdown": [{"component": "Base confidence", "points": 50}],
        },
        "macro": {"risk_multiplier": 1.2},
        "technicals": {"rsi_14": 28.4, "current_price": 193.2},
    }


def _narrative() -> str:
    return json.dumps({
        "executive_summary": {"text": "Confidence is 70% and the engine remains at Hold.", "evidence_ids": ["decision.confidence"]},
        "verdict_rationale": {"text": "The deterministic verdict is Hold.", "evidence_ids": ["decision.recommendation"]},
    })


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    monkeypatch.setenv("LLM_PIPELINE_MODE", "fast")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    pipeline.reset_for_tests()
    calls: list[str] = []

    def fake(provider, messages, *, final, model=None):
        calls.append(provider)
        return pipeline.ProviderResponse(content=_narrative(), provider=provider, model="deepseek-flash")

    monkeypatch.setattr(pipeline, "_call_stage", fake)
    api_module.app.dependency_overrides[require_clerk_user] = lambda: "user_test"
    try:
        yield TestClient(api_module.app), calls
    finally:
        api_module.app.dependency_overrides.pop(require_clerk_user, None)
        pipeline.reset_for_tests()


def test_a_held_snapshot_is_re_explained_at_the_requested_depth(client):
    http, calls = client
    first = pipeline.generate(_payload())
    res = http.post("/api/research/nvda/narrative", json={"snapshot_id": first["snapshot_id"], "depth": "advanced"})
    assert res.status_code == 200
    body = res.json()
    assert body["depth"] == "advanced" and body["ai"]["depth"] == "advanced"
    # The engine's decision is attached verbatim, never produced by the rewrite.
    assert body["ai"]["recommendation"] == "HOLD" and body["ai"]["confidence"] == 70
    assert calls == ["deepseek", "deepseek"]


def test_an_expired_snapshot_is_410_not_a_new_research_run(client):
    http, calls = client
    res = http.post("/api/research/NVDA/narrative", json={"snapshot_id": "a" * 32, "depth": "beginner"})
    assert res.status_code == 410
    assert calls == []


def test_an_unknown_depth_is_rejected(client):
    http, _ = client
    res = http.post("/api/research/NVDA/narrative", json={"snapshot_id": "a" * 32, "depth": "expert"})
    assert res.status_code == 422


def test_the_endpoint_requires_a_signed_in_user():
    res = TestClient(api_module.app).post(
        "/api/research/NVDA/narrative", json={"snapshot_id": "a" * 32, "depth": "beginner"},
    )
    assert res.status_code in (401, 403, 503)
