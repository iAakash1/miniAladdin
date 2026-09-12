"""Fetch once, run the agents over it, validate, attach the decision.

The shared evidence context is the point. If each agent fetched what it
needed, the same data would be paid for several times and — worse — two
agents could reason about different snapshots of the same security. A
contradiction produced that way is indistinguishable from a real one, which
would make the validation layer's findings untrustworthy in exactly the cases
it exists for.

Order matters and is fixed:

    evidence -> agents -> validation -> deterministic decision -> narrative

The decision is attached after validation and is never derived from it. No
agent, no validator and no model writes `model_signal`; it is copied from the
scorecard the scoring engine produced.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from src.agents.fundamental_agent import FundamentalAgent
from src.agents.macro_risk_agent import MacroRiskAgent
from src.agents.market_agent import MarketAgent
from src.agents.news_agent import NewsAgent
from src.agents.schemas import (
    AgentResult, AgentStatus, EvidenceContext, PipelineResult, ValidationStatus,
)
from src.agents.technical_agent import TechnicalAgent
from src.agents.validation_agent import ValidationAgent

logger = logging.getLogger("omnisignal.agents")

#: Deterministic order, so two runs over the same evidence produce claim ids
#: in the same sequence and are diffable.
EVIDENCE_AGENTS = (MarketAgent, FundamentalAgent, TechnicalAgent, NewsAgent, MacroRiskAgent)


def build_context(symbol: str, *, company_name: str = "") -> EvidenceContext:
    """Gather everything the agents will need, once.

    Every fetch is individually optional. A vendor that does not answer costs
    the reader the claims that depended on it, recorded in `failures`, rather
    than costing them the analysis.
    """
    from src import providers
    from src.services import fundamentals_data

    symbol = symbol.upper().strip()
    context = EvidenceContext(symbol=symbol, company_name=company_name or symbol)

    def attempt(label: str, fn, default=None):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — a fetch fault is recorded, not raised
            logger.info("agent context: %s unavailable (%s)", label, type(exc).__name__)
            context.failures.append(label)
            return default

    series = attempt("price_series", lambda: providers.market_data.get_series(symbol, "1y"))
    if series is not None and series.ok and series.data.bars:
        from api.index import _series_to_dataframe

        context.series_result = series
        context.price_frame = attempt("price_frame", lambda: _series_to_dataframe(series.data))
    else:
        context.failures.append("price_series")

    benchmark = attempt("benchmark", lambda: providers.market_data.get_series("SPY", "1y"))
    if benchmark is not None and benchmark.ok and benchmark.data.bars:
        from api.index import _series_to_dataframe

        context.benchmark_frame = attempt("benchmark_frame", lambda: _series_to_dataframe(benchmark.data))

    fundamentals = attempt("fundamentals", lambda: providers.fundamentals.get_fundamentals(symbol))
    if fundamentals is not None and fundamentals.ok:
        context.fundamentals = fundamentals.data
        try:
            setattr(context.fundamentals, "_provider", fundamentals.source)
        except Exception:  # noqa: BLE001 — provenance is a nicety, not a requirement
            pass

    targets = attempt("analyst_targets", lambda: providers.fundamentals.get_analyst_targets(symbol))
    if targets is not None and targets.ok:
        context.analyst_targets = targets.data

    news = attempt("news", lambda: providers.news.get_news(symbol, context.company_name, 12))
    if news is not None and news.ok and news.data:
        context.headlines = list(news.data)

    context.quality_inputs = attempt(
        "quality_inputs", lambda: fundamentals_data.get_quality_inputs(symbol), {}
    ) or {}

    from api.index import _fetch_macro_safe

    macro = attempt("macro", _fetch_macro_safe, (None, {}))
    if macro is not None:
        context.macro_multiplier, context.macro_stats = macro[0], macro[1] or {}

    return context


def scoring_inputs(context: EvidenceContext) -> Optional[dict]:
    """Every argument `score_ticker` is called with, derived from the context.

    Extracted because there is a second caller — the What-If simulator — and
    two hand-written copies of this argument list would drift. The failure
    that drift produces is quiet and bad: the simulator's "current" column
    would stop matching the scorecard on the page beside it, and a reader
    comparing them would trust the wrong one. Sharing the builder makes the
    baseline identical by construction rather than by a test that has to
    notice.

    Returns None when there is no price frame, which is the one input with no
    sensible default.
    """
    if context.price_frame is None:
        return None
    try:
        price = float(context.price_frame["Close"].iloc[-1])
    except Exception:  # noqa: BLE001
        return None

    multiplier = context.macro_multiplier
    scores = [
        getattr(h, "sentiment_score", None) for h in context.headlines
        if getattr(h, "sentiment_score", None) is not None
    ]
    quality = context.quality_inputs or {}
    return dict(
        srm=multiplier if isinstance(multiplier, (int, float)) else 1.0,
        price=price,
        pe_ratio=getattr(context.fundamentals, "pe_ratio", None),
        forward_pe=getattr(context.fundamentals, "forward_pe", None),
        analyst_target=getattr(context.analyst_targets, "target_mean", None),
        analyst_count=getattr(context.analyst_targets, "analyst_count", None),
        beta=getattr(context.fundamentals, "beta", None),
        sentiment_avg=(sum(scores) / len(scores)) if scores else None,
        headline_count=float(len(context.headlines)),
        spy_frame=context.benchmark_frame,
        gross_profit_over_assets=quality.get("gross_profit_over_assets"),
        net_issuance_yoy=quality.get("net_issuance_yoy"),
        asset_growth_yoy=quality.get("asset_growth_yoy"),
    )


def attach_scorecard(context: EvidenceContext) -> EvidenceContext:
    """Score the security from the shared context.

    The scorecard is computed here so that every agent and the decision read
    the same frame, the same fundamentals and the same regime. Scoring from a
    second fetch would let the explanation describe one snapshot and the
    verdict come from another.
    """
    from src.scoring.engine import score_ticker

    kwargs = scoring_inputs(context)
    if kwargs is None:
        return context

    try:
        context.scorecard = score_ticker(context.price_frame, **kwargs)
    except Exception:  # noqa: BLE001 — an unscored security is still describable
        logger.exception("scoring failed for %s inside the agent pipeline", context.symbol)
    return context


def run_agents(context: EvidenceContext) -> list[AgentResult]:
    """Every agent, in order, over the one shared context.

    Sequential rather than concurrent: the agents do no I/O — the fetching
    already happened — so threads would add contention and nondeterministic
    id ordering in exchange for nothing.
    """
    return [agent_cls().run(context) for agent_cls in EVIDENCE_AGENTS]


def analyse(
    symbol: str,
    *,
    company_name: str = "",
    context: Optional[EvidenceContext] = None,
    narrative_text: Optional[str] = None,
) -> PipelineResult:
    """One complete run. Never raises."""
    started = time.perf_counter()
    ctx = context or attach_scorecard(build_context(symbol, company_name=company_name))

    agents = run_agents(ctx)
    evidence = [e for a in agents for e in a.evidence]
    claims = [c for a in agents for c in a.claims]

    card = ctx.scorecard
    report = ValidationAgent().validate(
        claims, evidence,
        model_signal=getattr(card, "verdict", None),
        risk_score=getattr(card, "risk_score", None),
        narrative_text=narrative_text,
    )

    result = PipelineResult(
        symbol=ctx.symbol,
        agents=agents,
        evidence=evidence,
        claims=claims,
        validation=report,
        scoring_version=getattr(card, "model_version", None),
        # Copied from the scorecard. Nothing in this module computes them.
        model_signal=getattr(card, "verdict", None),
        confidence=getattr(card, "confidence", None),
        risk_score=getattr(card, "risk_score", None),
        data_completeness=getattr(card, "data_completeness", None),
    )
    logger.info(
        "agents %s: %d claims, validation=%s, %.0fms",
        ctx.symbol, len(claims), report.status.value,
        (time.perf_counter() - started) * 1000,
    )
    return result


def unavailable_agents(agents: list[AgentResult]) -> list[str]:
    return [a.agent for a in agents if a.status in (AgentStatus.UNAVAILABLE, AgentStatus.ERROR)]
