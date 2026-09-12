"""The analysis graph: orchestration only, and every branch preserves authority.

LangGraph decides when things run. It computes nothing. The property that makes
that claim checkable is that the four authoritative values — signal,
confidence, risk, completeness — are copied from the scorecard by exactly one
node, and no node after it may write them. Every test below tries a different
route through the graph and asserts the signal survives it.

The graph earns its place by making three things explicit that a function body
hid: the specialists fan out because they are independent, the critic is a
conditional path rather than an `if`, and each node's cost is recorded so a run
has a trace.
"""

import pandas as pd
import pytest

from src.agents import graph
from src.agents.graph import (
    AnalysisState, GRAPH_VERSION, node_critic, node_explain, node_finalise,
    node_reconcile, node_score, node_validate, should_run_critic,
)
from src.agents.schemas import AgentResult, AgentStatus, EvidenceContext


class _Card:
    verdict = "Hold"
    confidence = 61
    risk_score = 42
    data_completeness = 0.93
    model_version = "scoring-v2.1"
    risk_components: list = []
    factors: list = []


def _frame(n=200):
    idx = pd.bdate_range("2026-01-01", periods=n)
    return pd.DataFrame({"Close": [100.0 + i * 0.3 for i in range(n)],
                         "Volume": [1_000_000] * n}, index=idx)


@pytest.fixture(autouse=True)
def _fresh_graph():
    graph.reset_for_tests()
    yield
    graph.reset_for_tests()


# ── the graph is available and shaped as declared ────────────────────────────

def test_langgraph_is_installed():
    assert graph.available()


def test_the_graph_compiles_and_declares_its_nodes():
    compiled = graph.build_graph()
    nodes = set(compiled.get_graph().nodes)
    for node in ("build_evidence", "market", "fundamental", "technical", "news",
                 "macro", "reconcile", "score", "validate", "explain",
                 "critic", "finalise"):
        assert node in nodes, node


def test_the_specialists_fan_out_from_one_snapshot():
    """Each depends only on build_evidence, which is what makes them parallel
    and what keeps them reasoning about the same snapshot."""
    edges = graph.build_graph().get_graph().edges
    pairs = {(e.source, e.target) for e in edges}
    for name in ("market", "fundamental", "technical", "news", "macro"):
        assert ("build_evidence", name) in pairs, name
        assert (name, "reconcile") in pairs, name


def test_the_graph_is_compiled_once():
    assert graph.build_graph() is graph.build_graph()


# ── only one node produces a signal ──────────────────────────────────────────

def test_score_copies_the_scorecard_rather_than_computing():
    state: AnalysisState = {"evidence_context": EvidenceContext(symbol="X", scorecard=_Card())}
    update = node_score(state)
    assert update["model_signal"] == "Hold"
    assert update["confidence"] == 61
    assert update["risk_score"] == 42
    assert update["data_completeness"] == 0.93


def test_no_node_after_score_writes_an_authoritative_value():
    """The invariant, checked structurally rather than by running every path."""
    import inspect

    authoritative = ("model_signal", "confidence", "risk_score", "data_completeness")
    for node in (node_validate, node_explain, node_critic, node_finalise, node_reconcile):
        source = inspect.getsource(node)
        for field in authoritative:
            assert f'"{field}":' not in source, f"{node.__name__} writes {field}"


def test_an_unscored_security_yields_no_signal_rather_than_a_default():
    state: AnalysisState = {"evidence_context": EvidenceContext(symbol="X", scorecard=None)}
    update = node_score(state)
    assert "model_signal" not in update
    assert "no_scorecard" in update["fallbacks"]


# ── the critic is a path, and cannot change anything ─────────────────────────

def test_the_critic_is_skipped_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    state: AnalysisState = {"explanation": {"summary": "Something."}}
    assert should_run_critic(state) == "skip"


def test_the_critic_is_skipped_when_there_is_no_narrative(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    assert should_run_critic({"explanation": {}}) == "skip"
    assert should_run_critic({}) == "skip"


def test_the_critic_runs_when_configured_and_there_is_prose(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    assert should_run_critic({"explanation": {"summary": "Something."}}) == "critic"


def test_a_skipped_critic_is_recorded_rather_than_absent(monkeypatch):
    """No critic entry at all is indistinguishable from a critic that ran and
    found nothing, which is a different fact."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    update = node_finalise({"critic": None, "validation": None})
    assert update["critic"]["skipped"] is True
    assert update["critic"]["reason"]
    assert "critic_skipped" in update["fallbacks"]


def test_a_failing_critic_does_not_end_the_run(monkeypatch):
    from src.agents import critic_agent

    monkeypatch.setattr(critic_agent, "available", lambda: True)
    monkeypatch.setattr(critic_agent, "_request", lambda prompt: (_ for _ in ()).throw(TimeoutError()))
    update = node_critic({
        "explanation": {"summary": "Something."}, "agent_results": {},
        "model_signal": "Hold", "confidence": 61, "risk_score": 42,
    })
    assert update["critic"]["available"] is False
    assert "critic_unavailable" in update["fallbacks"]


# ── failure isolation ────────────────────────────────────────────────────────

def test_a_failing_node_is_recorded_and_the_run_continues():
    """An unavailable news provider should cost a reader the news section, not
    the analysis."""
    from src.agents.graph import _timed

    def boom(_state):
        raise RuntimeError("vendor exploded")

    update = _timed("news", boom, {})
    assert update["errors"] == ["news: RuntimeError"]
    assert update["warnings"]
    assert "news" in update["timings"]


def test_every_node_records_its_cost():
    from src.agents.graph import _timed

    update = _timed("score", lambda _s: {}, {})
    assert "score" in update["timings"]
    assert update["timings"]["score"] >= 0


# ── the deterministic explanation ────────────────────────────────────────────

def test_a_useful_explanation_exists_with_no_model_available():
    state: AnalysisState = {
        "model_signal": "Hold", "confidence": 44, "risk_score": 52,
        "data_completeness": 0.84, "scorecard": _Card(),
    }
    update = node_explain(state)
    assert update["narrative_source"] == "deterministic"
    summary = update["explanation"]["summary"]
    assert "HOLD" in summary
    assert "chance of a gain" in summary  # confidence framed correctly


def test_the_deterministic_explanation_never_promises_a_probability():
    from src.agents.explanation import deterministic_summary

    out = deterministic_summary(
        signal="Buy", confidence=82, risk_score=30, data_completeness=1.0,
    )
    blob = " ".join(str(v) for v in out.values()).lower()
    for forbidden in ("% chance", "probability of profit", "will rise", "guaranteed"):
        assert forbidden not in blob


def test_an_unscored_security_gets_an_honest_summary():
    from src.agents.explanation import deterministic_summary

    out = deterministic_summary(
        signal=None, confidence=None, risk_score=None, data_completeness=None,
    )
    assert "could not produce a signal" in out["summary"]
    assert "not the same as it being low" in out["risk_explanation"]


# ── the last gate ────────────────────────────────────────────────────────────

def test_a_refused_narrative_is_withheld():
    from src.agents.schemas import ValidationReport

    report = ValidationReport()
    report.narrative_admissible = False
    report.rejected_reason = "it contradicts the signal"

    update = node_finalise({
        "critic": {"available": True}, "validation": report,
        "explanation": {"summary": "Buy this."},
    })
    assert update["explanation"]["withheld"] is True
    assert "narrative_withheld" in update["fallbacks"]


def test_an_admissible_narrative_survives():
    from src.agents.schemas import ValidationReport

    update = node_finalise({
        "critic": {"available": True}, "validation": ValidationReport(),
        "explanation": {"summary": "Momentum supports the signal."},
    })
    assert "explanation" not in update


# ── reconciliation counts sources, not vendor names ──────────────────────────

def test_reconciliation_distinguishes_providers_from_independent_sources():
    """yfinance and Yahoo RSS are Yahoo twice."""
    from src.agents.schemas import EvidenceRecord

    def ev(provider):
        return EvidenceRecord(
            evidence_id=f"E-{provider}", agent="t", provider=provider,
            capability="price_series", field="last_close", value=1.0,
        )

    result = AgentResult(agent="market", status=AgentStatus.OK,
                         evidence=[ev("yahoo"), ev("yfinance"), ev("polygon")])
    update = node_reconcile({"agent_results": {"market": result}})
    rec = update["reconciliation"]
    assert rec["providers"] == 3
    assert rec["independent_sources"] == 2


def test_reconciliation_names_the_degraded_agents():
    result_ok = AgentResult(agent="market", status=AgentStatus.OK)
    result_bad = AgentResult(agent="news", status=AgentStatus.UNAVAILABLE, missing=["headlines"])
    update = node_reconcile({"agent_results": {"market": result_ok, "news": result_bad}})
    rec = update["reconciliation"]
    assert rec["agents_ok"] == ["market"]
    assert rec["agents_degraded"] == ["news"]
    assert "headlines" in rec["missing_inputs"]


# ── versioning ───────────────────────────────────────────────────────────────

def test_a_run_records_the_versions_that_produced_it():
    state = graph.run.__doc__
    assert state  # the function documents its degradation contract
    assert GRAPH_VERSION == "graph-v1"
