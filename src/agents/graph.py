"""The analysis run, as an explicit graph.

LangGraph is the orchestration layer and nothing more. It decides *when* each
component runs, in what order, in parallel or not, and what happens when one
fails. It computes no financial value: every number in the result comes from
the same deterministic services that produced it before this module existed.

**Why a graph rather than a function.** The previous orchestrator ran five
agents in a list comprehension and validated whatever came back. That worked,
and it made three things awkward that a research product needs:

  - the five specialists are independent and should fan out, but a sequential
    list cannot say so, and adding threads by hand reintroduces exactly the
    kind of unmanaged concurrency that leaked workers into the test suite
  - the critic is a conditional path — it runs only when configured and only
    when there is a narrative to review — and an `if` buried mid-function is
    not a path anyone can see
  - a run needs a trace: which node ran, how long it took, what it degraded
    to. Timing scattered through a function body is not a trace

The graph makes all three explicit, which is the whole reason it is here. It is
not here so the project can say it uses LangGraph.

**Agents do not vote.** There is no node that combines specialist opinions into
a verdict, and there could not be: the specialists emit evidence and claims,
never recommendations. `score` is the only node that produces a signal, it is
the existing scoring engine, and every node after it treats the result as
given.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Annotated, Any, Optional, TypedDict

logger = logging.getLogger("omnisignal.agents.graph")

#: Bumped when the node set or their contract changes, so a stored trace can be
#: read under the shape it was produced with.
GRAPH_VERSION = "graph-v1"


def _merge(left: dict, right: dict) -> dict:
    """Reducer for the fields parallel nodes write into.

    Each specialist writes under its own key, so the merge is a union and can
    never be order-dependent. Without a reducer LangGraph rejects concurrent
    writes to one channel — correctly, because a last-writer-wins merge across
    a fan-out is a race dressed as a result.
    """
    return {**left, **right}


def _extend(left: list, right: list) -> list:
    return [*left, *right]


class AnalysisState(TypedDict, total=False):
    """Everything one run carries. No secrets: this is traceable and logged."""

    run_id: str
    ticker: str
    experience_mode: Optional[str]
    requested_at: str

    evidence_context: Any

    #: Written concurrently by the five specialists, keyed by agent name.
    agent_results: Annotated[dict[str, Any], _merge]

    reconciliation: Optional[dict[str, Any]]
    validation: Optional[Any]
    scorecard: Optional[Any]

    # Authoritative, copied from the scorecard. No node computes these.
    model_signal: Optional[str]
    confidence: Optional[int]
    risk_score: Optional[int]
    data_completeness: Optional[float]

    explanation: Optional[dict[str, Any]]
    narrative_source: str
    critic: Optional[dict[str, Any]]

    warnings: Annotated[list[str], _extend]
    errors: Annotated[list[str], _extend]
    fallbacks: Annotated[list[str], _extend]
    #: node name -> milliseconds. The trace the Observatory renders.
    timings: Annotated[dict[str, float], _merge]

    scoring_version: Optional[str]
    agent_schema_version: str
    validation_version: str
    prompt_version: Optional[str]
    graph_version: str


def _timed(name: str, fn, state: AnalysisState) -> dict[str, Any]:
    """Run one node, record its cost, and never let it end the run.

    Error isolation is per node on purpose: an unavailable news provider should
    cost a reader the news section, not the analysis. The failure is recorded
    in `errors` and the graph carries on to the next node.
    """
    started = time.perf_counter()
    try:
        update = fn(state)
    except Exception as exc:  # noqa: BLE001 — a node fault is data, not a crash
        logger.exception("graph node %s failed", name)
        update = {
            "errors": [f"{name}: {type(exc).__name__}"],
            "warnings": [f"the {name} stage did not complete"],
        }
    update.setdefault("timings", {})
    update["timings"] = {**update["timings"], name: round((time.perf_counter() - started) * 1000, 2)}
    return update


# ── nodes ────────────────────────────────────────────────────────────────────

def node_build_evidence(state: AnalysisState) -> dict[str, Any]:
    """One coherent snapshot, fetched once, shared by every specialist."""
    from src.agents.orchestrator import attach_scorecard, build_context

    context = attach_scorecard(build_context(state["ticker"]))
    warnings = [f"{label} unavailable" for label in context.failures]
    return {"evidence_context": context, "warnings": warnings}


def _specialist(agent_cls):
    """One specialist node. Writes under its own key so the fan-out merges."""

    def run(state: AnalysisState) -> dict[str, Any]:
        context = state.get("evidence_context")
        if context is None:
            return {"warnings": [f"{agent_cls.name}: no evidence context"]}
        result = agent_cls().run(context)
        return {"agent_results": {result.agent: result}}

    run.__name__ = f"node_{agent_cls.name}"
    return run


def node_reconcile(state: AnalysisState) -> dict[str, Any]:
    """Pool the claims and count what the specialists disagreed about.

    Reconciliation here is about *independence*, not averaging. Two vendors
    that resell one upstream are one source, and counting them twice inflates
    apparent corroboration exactly where a reader would lean on it.
    """
    from src.agents.validation_agent import independent_sources

    results = list(state.get("agent_results", {}).values())
    evidence = [e for r in results for e in r.evidence]
    claims = [c for r in results for c in r.claims]
    providers = [e.provider for e in evidence if e.provider]

    return {
        "reconciliation": {
            "claims": len(claims),
            "evidence": len(evidence),
            "providers": len(set(providers)),
            "independent_sources": independent_sources(providers),
            "agents_ok": [r.agent for r in results if r.status.value == "ok"],
            "agents_degraded": [r.agent for r in results if r.status.value != "ok"],
            "missing_inputs": sorted({m for r in results for m in r.missing}),
        },
    }


def node_validate(state: AnalysisState) -> dict[str, Any]:
    """Check every claim against the evidence it cites."""
    from src.agents.validation_agent import ValidationAgent

    results = list(state.get("agent_results", {}).values())
    evidence = [e for r in results for e in r.evidence]
    claims = [c for r in results for c in r.claims]
    card = state.get("scorecard") or getattr(state.get("evidence_context"), "scorecard", None)

    report = ValidationAgent().validate(
        claims, evidence,
        model_signal=getattr(card, "verdict", None),
        risk_score=getattr(card, "risk_score", None),
    )
    return {"validation": report}


def node_score(state: AnalysisState) -> dict[str, Any]:
    """The only node that produces a signal, and it does not compute one.

    The scorecard was built from the shared context in `build_evidence`, by the
    production scoring engine. This node reads it. Nothing between here and the
    reader is allowed to change these four values.
    """
    context = state.get("evidence_context")
    card = getattr(context, "scorecard", None)
    if card is None:
        return {
            "warnings": ["no scorecard: the security could not be scored"],
            "fallbacks": ["no_scorecard"],
        }
    return {
        "scorecard": card,
        "model_signal": card.verdict,
        "confidence": card.confidence,
        "risk_score": card.risk_score,
        "data_completeness": card.data_completeness,
        "scoring_version": getattr(card, "model_version", None),
    }


def node_explain(state: AnalysisState) -> dict[str, Any]:
    """Language only, and only after the decision exists.

    A deterministic summary is always produced. It is the fallback when no
    model is configured or every attempt fails, and it is built from the same
    authoritative numbers, so a reader with no LLM available still gets a
    useful answer rather than an empty panel.
    """
    from src.agents.explanation import deterministic_summary

    card = state.get("scorecard")
    summary = deterministic_summary(
        signal=state.get("model_signal"),
        confidence=state.get("confidence"),
        risk_score=state.get("risk_score"),
        data_completeness=state.get("data_completeness"),
        factors=getattr(card, "factors", None),
        validation=state.get("validation"),
    )
    return {"explanation": summary, "narrative_source": "deterministic"}


def node_critic(state: AnalysisState) -> dict[str, Any]:
    """Optional second opinion on the prose. Cannot touch a number."""
    from src.agents import critic_agent

    explanation = state.get("explanation") or {}
    narrative = explanation.get("summary") or ""
    results = list(state.get("agent_results", {}).values())
    evidence = [e for r in results for e in r.evidence]

    report = critic_agent.review(
        narrative=narrative,
        evidence=evidence,
        model_signal=state.get("model_signal"),
        confidence=state.get("confidence"),
        risk_score=state.get("risk_score"),
    )
    update: dict[str, Any] = {"critic": report.model_dump()}
    if not report.available:
        update["fallbacks"] = ["critic_unavailable"]
    return update


def should_run_critic(state: AnalysisState) -> str:
    """The conditional path, stated as an edge rather than hidden in an `if`."""
    from src.agents import critic_agent

    explanation = state.get("explanation") or {}
    if not explanation.get("summary"):
        return "skip"
    return "critic" if critic_agent.available() else "skip"


def node_finalise(state: AnalysisState) -> dict[str, Any]:
    """Last gate: withhold a narrative the validator refused.

    Also records that the critic was skipped. The conditional edge means
    `node_critic` never runs on that path, so without this the trace would show
    no critic entry at all — indistinguishable from a critic that ran and found
    nothing, which is a different fact.
    """
    update: dict[str, Any] = {}
    if state.get("critic") is None:
        from src.agents import critic_agent

        update["critic"] = {
            "available": False,
            "skipped": True,
            "reason": (
                "no critic model is configured"
                if not critic_agent.available()
                else "there was no narrative to review"
            ),
        }
        update["fallbacks"] = ["critic_skipped"]

    report = state.get("validation")
    if report is not None and not report.narrative_admissible:
        # The refused text is *moved*, not flagged in place.
        #
        # Flagging it left the paragraph sitting under `summary` beside
        # `withheld: true`, so the guarantee held only as long as every
        # consumer remembered to check a boolean before rendering the field
        # they were reaching for anyway. One that forgot would ship a
        # narrative the validator refused, and nothing would fail.
        #
        # Under `withheld_summary` it is still auditable — an operator
        # reviewing what was rejected needs to see it — but a surface can only
        # display it by asking for it under a name that says what it is.
        refused = dict(state.get("explanation") or {})
        summary = refused.pop("summary", None)
        update["explanation"] = {
            **refused,
            "summary": None,
            "withheld": True,
            "withheld_summary": summary,
            "withheld_reason": report.rejected_reason,
        }
        update["narrative_source"] = "deterministic"
        update["fallbacks"] = [*update.get("fallbacks", []), "narrative_withheld"]
    return update


# ── graph ────────────────────────────────────────────────────────────────────

_compiled = None


def build_graph():
    """Compile once. The topology is fixed, so rebuilding it per request is
    pure overhead."""
    global _compiled
    if _compiled is not None:
        return _compiled

    from langgraph.graph import END, START, StateGraph

    from src.agents.fundamental_agent import FundamentalAgent
    from src.agents.macro_risk_agent import MacroRiskAgent
    from src.agents.market_agent import MarketAgent
    from src.agents.news_agent import NewsAgent
    from src.agents.technical_agent import TechnicalAgent

    graph = StateGraph(AnalysisState)

    graph.add_node("build_evidence", lambda s: _timed("build_evidence", node_build_evidence, s))

    specialists = {
        "market": MarketAgent, "fundamental": FundamentalAgent,
        "technical": TechnicalAgent, "news": NewsAgent, "macro": MacroRiskAgent,
    }
    for name, cls in specialists.items():
        runner = _specialist(cls)
        graph.add_node(name, lambda s, fn=runner, n=name: _timed(n, fn, s))

    graph.add_node("score", lambda s: _timed("score", node_score, s))
    graph.add_node("reconcile", lambda s: _timed("reconcile", node_reconcile, s))
    graph.add_node("validate", lambda s: _timed("validate", node_validate, s))
    graph.add_node("explain", lambda s: _timed("explain", node_explain, s))
    graph.add_node("critic", lambda s: _timed("critic", node_critic, s))
    graph.add_node("finalise", lambda s: _timed("finalise", node_finalise, s))

    graph.add_edge(START, "build_evidence")
    # The fan-out: five specialists over one snapshot, concurrently, because
    # they share every input and none reads another's output.
    for name in specialists:
        graph.add_edge("build_evidence", name)
        graph.add_edge(name, "reconcile")

    graph.add_edge("reconcile", "score")
    graph.add_edge("score", "validate")
    graph.add_edge("validate", "explain")
    graph.add_conditional_edges(
        "explain", should_run_critic, {"critic": "critic", "skip": "finalise"},
    )
    graph.add_edge("critic", "finalise")
    graph.add_edge("finalise", END)

    _compiled = graph.compile()
    return _compiled


def available() -> bool:
    try:
        import langgraph  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def run(ticker: str, *, experience_mode: Optional[str] = None) -> dict[str, Any]:
    """Execute one analysis run and return its final state.

    Degrades rather than collapses: without LangGraph installed this falls back
    to the sequential orchestrator and records `langgraph_unavailable`, so a
    deployment that cannot carry the dependency still produces an analysis.
    """
    from datetime import datetime, timezone

    from src.agents.schemas import AGENT_SCHEMA_VERSION

    run_id = f"OS-{uuid.uuid4().hex[:8].upper()}"
    initial: AnalysisState = {
        "run_id": run_id,
        "ticker": ticker.upper().strip(),
        "experience_mode": experience_mode,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "agent_results": {},
        "warnings": [], "errors": [], "fallbacks": [], "timings": {},
        "narrative_source": "none",
        "agent_schema_version": AGENT_SCHEMA_VERSION,
        "validation_version": "validation-v1",
        "graph_version": GRAPH_VERSION,
    }

    if not available():
        from src.agents.orchestrator import analyse

        result = analyse(ticker)
        initial.update({
            "model_signal": result.model_signal,
            "confidence": result.confidence,
            "risk_score": result.risk_score,
            "data_completeness": result.data_completeness,
            "validation": result.validation,
            "agent_results": {a.agent: a for a in result.agents},
            "fallbacks": ["langgraph_unavailable"],
        })
        return initial

    return build_graph().invoke(initial)


def reset_for_tests() -> None:
    global _compiled
    _compiled = None
