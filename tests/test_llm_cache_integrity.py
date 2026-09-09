"""Narratives and attached engine facts must belong to the same input snapshot."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from src.services import llm_service


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-placeholder")
    llm_service.reset_client_for_tests()
    yield
    llm_service.reset_client_for_tests()


def _payload():
    return llm_service.build_payload(
        ticker="NVDA", recommendation="HOLD", confidence=70, risk="HIGH",
        verdict="Hold", rationale="Measured rationale",
        macro={"risk_multiplier": 1.2}, technicals={"current_price": 100},
        sentiment=None,
        quant={"factors": [
            {"name": "r12_1", "family": "momentum", "contribution": 0.18},
        ]},
    )


@pytest.mark.parametrize("changed", ["decision", "technicals", "macro", "factor_impacts"])
def test_same_verdict_new_evidence_cannot_reuse_old_narrative(monkeypatch, changed):
    calls = []

    def explain(messages):
        evidence = json.loads(messages[-1]["content"])
        calls.append(evidence)
        return json.dumps({"executive_summary": f"Explanation for evidence snapshot {len(calls)}."}), 0

    monkeypatch.setattr(llm_service, "_call_with_retries", explain)
    initial = _payload()
    first = llm_service.explain_recommendation(initial)
    current = deepcopy(initial)
    if changed == "decision":
        current["decision"].update(confidence=33, risk="LOW")
    elif changed == "technicals":
        current["technicals"]["current_price"] = 90
    elif changed == "macro":
        current["macro"] = {"risk_multiplier": None, "status": "UNAVAILABLE"}
    else:
        current["factor_impacts"]["momentum"]["contribution"] = -0.09

    second = llm_service.explain_recommendation(current)

    assert len(calls) == 2, "the verdict alone cannot identify the evidence explained"
    assert second["cached"] is False
    assert second["executive_summary"] != first["executive_summary"]
    assert second["confidence"] == current["decision"]["confidence"]
    assert second["risk"] == current["decision"]["risk"]
    assert second["factor_impacts"] == current["factor_impacts"]


def test_equivalent_payload_key_order_still_reuses_cache(monkeypatch):
    calls = []

    def explain(messages):
        calls.append(messages)
        return json.dumps({"executive_summary": "The supplied engine verdict is HOLD."}), 0

    monkeypatch.setattr(llm_service, "_call_with_retries", explain)
    original = _payload()
    reordered = dict(reversed(list(original.items())))
    reordered["decision"] = dict(reversed(list(original["decision"].items())))
    first = llm_service.explain_recommendation(original)
    second = llm_service.explain_recommendation(reordered)

    assert len(calls) == 1
    assert first["cached"] is False and second["cached"] is True
    assert second["executive_summary"] == first["executive_summary"]
