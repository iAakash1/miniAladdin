"""
AI research analyst — investment memo generation.

Reasoning pipeline (each stage feeds the next; the model only ever sees
already-verified inputs):

    /api/research output (deterministic: scorecard, technicals, macro,
    sentiment, verdict, confidence)
        +
    Evidence table (collected → deduped → reliability-scored → ranked,
    with citation IDs — src/services/evidence.py)
        ↓
    Groq gpt-oss-120b, memo prompt v1 (JSON only, cite [E#] per claim)
        ↓
    json.loads → Pydantic → CITATION AUDIT (every cited ID must exist;
    unknown citations = validation failure)
        ↓ retry once with the valid-ID list ↓
    Deterministic attachment: final recommendation + confidence from the
    engine, Source Attribution built from the evidence table itself
        ↓
    Fallback memo assembled from scorecard + top evidence when the model
    fails — the endpoint never breaks.

Hallucination containment, by construction:
  * the model receives ONLY the research facts + evidence table;
  * narrative sections must cite evidence IDs; invented IDs fail validation;
  * recommendation/confidence/attribution are never model-generated;
  * temperature 0.2, JSON-object mode, strict parsing (shared machinery).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from src.services import llm_service
from src.services.evidence import EvidenceItem, citation_ids, collect_evidence, extract_citations
from src.services.metrics import llm_metrics

logger = logging.getLogger(__name__)

MEMO_PROMPT_VERSION = "memo-2"
MEMO_CACHE_TTL_SECONDS = 900.0  # memos are heavier; 15 min


class ScenarioAnalysis(BaseModel):
    best_case: str = Field("", max_length=1200)
    base_case: str = Field("", max_length=1200)
    worst_case: str = Field("", max_length=1200)


class MemoNarrative(BaseModel):
    """Model-generated sections (memo-2). Everything else is attached deterministically."""

    executive_summary: str = Field(..., min_length=1, max_length=2500)
    investment_thesis: str = Field("", max_length=2500)
    catalysts: list[str] = Field(default_factory=list, max_length=8)
    headwinds: list[str] = Field(default_factory=list, max_length=8)
    competitive_position: str = Field("", max_length=1500)
    industry_outlook: str = Field("", max_length=1500)
    macro_impact: str = Field("", max_length=1500)
    valuation: str = Field("", max_length=1500)
    technical_picture: str = Field("", max_length=1500)
    fundamental_picture: str = Field("", max_length=1500)
    institutional_activity: str = Field("", max_length=1200)
    analyst_consensus: str = Field("", max_length=1200)
    risk_factors: list[str] = Field(default_factory=list, max_length=8)
    counter_arguments: list[str] = Field(default_factory=list, max_length=6)
    scenario_analysis: ScenarioAnalysis = Field(default_factory=ScenarioAnalysis)


MEMO_SYSTEM_PROMPT = """You are OmniSignal's research analyst. You write institutional investment memos.

You do NOT browse the internet. You may ONLY use two inputs supplied in the user message:
1. `research` — deterministic engine output (scores, indicators, macro, verdict, confidence). These numbers are authoritative; never contradict or recompute them.
2. `evidence` — a ranked table of news/search items, each with an id (E1, E2, …), source, reliability score and date.

Citation rules (mandatory):
- Every factual claim in summary, bull_case, bear_case, news_summary, key_catalysts and key_risks that comes from evidence MUST cite its id inline like [E3].
- Cite only ids that exist in the evidence table. Never invent citations.
- Claims from `research` numbers need no citation (they are engine facts) — reference them by value, e.g. "momentum score +0.31".
- Prefer higher-reliability evidence; when relying on reliability < 0.6, note it ("per a lower-reliability source [E7]").
- If evidence is thin or conflicting for a section, say exactly that instead of filling space.

Do not output a recommendation or confidence — they are attached by the engine after validation.

For sections where the supplied evidence is insufficient (e.g. institutional_activity when no filing/ownership evidence exists, competitive_position without competitor coverage), write exactly what is missing — one honest sentence — rather than inventing content. Scenario analysis must be grounded: best/worst cases reference the specific supplied catalysts/risks, base case follows the engine verdict.

Return ONLY valid JSON parseable by a strict parser. No markdown, no code fences. Schema (all keys required; "" or [] when empty):
{
  "executive_summary": "<4-6 sentences: verdict, the drivers behind it, and what would change it — engine numbers + cited evidence>",
  "investment_thesis": "<the core argument, cited>",
  "catalysts": ["<short items, cited where evidence-based>"],
  "headwinds": ["<short items, cited where evidence-based>"],
  "competitive_position": "<from evidence about the company's market standing, cited — or what's missing>",
  "industry_outlook": "<from evidence about the sector, cited — or what's missing>",
  "macro_impact": "<from research.macro only: SRM, gate effect, regime>",
  "valuation": "<from supplied PE/forward PE/targets only>",
  "technical_picture": "<from research quant/technicals only: factor scores, regimes>",
  "fundamental_picture": "<from supplied fundamentals only>",
  "institutional_activity": "<only if evidence covers filings/ownership; otherwise state that no institutional evidence was supplied>",
  "analyst_consensus": "<from supplied analyst target + any cited analyst coverage>",
  "risk_factors": ["<short items, cited where evidence-based>"],
  "counter_arguments": ["<the strongest honest cases AGAINST the engine verdict, cited>"],
  "scenario_analysis": {
    "best_case": "<grounded in supplied catalysts>",
    "base_case": "<follows the engine verdict and scores>",
    "worst_case": "<grounded in supplied risks>"
  }
}

Style: research desk. Specific numbers over adjectives. No advice language, no disclaimers."""


# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def reset_for_tests() -> None:
    _cache.clear()


def _cache_key(ticker: str, verdict: str) -> str:
    raw = "|".join([
        ticker,
        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        verdict,
        llm_service._model_name(),
        MEMO_PROMPT_VERSION,
    ])
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Deterministic pieces ──────────────────────────────────────────────────────

def _source_attribution(evidence: list[EvidenceItem], cited: set[str]) -> list[dict[str, Any]]:
    """Built from the evidence table, never from model output."""
    return [
        {
            "id": item.id,
            "title": item.title,
            "source": item.source,
            "url": item.url,
            "published_at": item.published_at,
            "reliability": item.reliability,
            "cited": item.id in cited,
        }
        for item in evidence
    ]


def _fallback_memo(research: dict[str, Any], evidence: list[EvidenceItem], reason: str) -> dict[str, Any]:
    quant = research.get("quant") or {}
    top_titles = "; ".join(f"{item.title} [{item.id}]" for item in evidence[:3])
    verdict = research.get("verdict", "Hold")
    narrative = {
        "executive_summary": (
            f"{verdict} at {research.get('confidence', 50)}% confidence. "
            f"{research.get('rationale', '')} "
            f"(Analyst memo unavailable: {reason} — deterministic summary shown.)"
        ).strip(),
        "investment_thesis": "",
        "catalysts": [],
        "headwinds": [item.title for item in evidence[:3]] or [],
        "competitive_position": "",
        "industry_outlook": "",
        "macro_impact": research.get("rationale", ""),
        "valuation": "",
        "technical_picture": (
            f"Composite {quant.get('raw_score')} (momentum {quant.get('momentum_score')}, "
            f"macro gate {quant.get('macro_gate')})" if quant else ""
        ),
        "fundamental_picture": "",
        "institutional_activity": "",
        "analyst_consensus": "",
        "risk_factors": [],
        "counter_arguments": [],
        "scenario_analysis": {
            "best_case": "",
            "base_case": f"Engine verdict: {verdict}.",
            "worst_case": "",
        },
        "news_summary_fallback": f"Top evidence: {top_titles}" if top_titles else "No evidence collected.",
    }
    return _attach(narrative, research, evidence, cited=set(), generated=False)


def _attach(
    narrative: dict[str, Any],
    research: dict[str, Any],
    evidence: list[EvidenceItem],
    cited: set[str],
    generated: bool,
) -> dict[str, Any]:
    return {
        **narrative,
        "final_recommendation": research.get("verdict", "Hold"),
        "confidence": research.get("confidence", 50),
        "risk_level": research.get("risk_level", "MEDIUM"),
        "source_attribution": _source_attribution(evidence, cited),
        "evidence_count": len(evidence),
        "generated": generated,
        "model": llm_service._model_name() if generated else None,
        "prompt_version": MEMO_PROMPT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": research.get("ticker"),
        "disclaimer": research.get("disclaimer", "Research and education only — not investment advice."),
    }


def _validate_citations(narrative: MemoNarrative, valid_ids: set[str]) -> set[str]:
    """Return cited ids; raise ValueError when the model invented one."""
    scenario = narrative.scenario_analysis
    blob = " ".join([
        narrative.executive_summary, narrative.investment_thesis,
        narrative.competitive_position, narrative.industry_outlook,
        narrative.macro_impact, narrative.valuation,
        narrative.technical_picture, narrative.fundamental_picture,
        narrative.institutional_activity, narrative.analyst_consensus,
        scenario.best_case, scenario.base_case, scenario.worst_case,
        " ".join(narrative.catalysts), " ".join(narrative.headwinds),
        " ".join(narrative.risk_factors), " ".join(narrative.counter_arguments),
    ])
    cited = extract_citations(blob)
    unknown = cited - valid_ids
    if unknown:
        raise ValueError(f"unknown citations: {sorted(unknown)}")
    return cited


# ── Public API ────────────────────────────────────────────────────────────────

def generate_memo(research: dict[str, Any]) -> dict[str, Any]:
    """
    Produce the investment memo for an already-computed research payload.
    Never raises. `research` is the /api/research response dict.
    """
    ticker = str(research.get("ticker", "")).upper()
    company = (research.get("technicals") or {}).get("company_name") or ""

    key = _cache_key(ticker, str(research.get("verdict", "")))
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return {**entry[1], "cached": True}

    evidence = collect_evidence(ticker, company)
    valid_ids = citation_ids(evidence)

    if not llm_service.is_configured():
        return _fallback_memo(research, evidence, "LLM not configured")

    # Trim the research payload to the facts worth prompting with.
    research_facts = {
        k: research.get(k)
        for k in ("ticker", "verdict", "confidence", "confidence_breakdown",
                  "risk_level", "rationale", "quant", "macro", "technicals")
    }
    payload = {
        "research": research_facts,
        "evidence": [item.model_dump() for item in evidence],
    }

    messages = [
        {"role": "system", "content": MEMO_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]

    started = time.time()
    narrative: Optional[MemoNarrative] = None
    cited: set[str] = set()
    transient_retries = 0
    validation_retries = 0

    for attempt in range(2):  # initial + one corrective retry
        try:
            content, retries = llm_service._call_with_retries(messages)
            transient_retries += retries
        except Exception as exc:  # noqa: BLE001 — terminal → fallback
            logger.warning("memo LLM call failed for %s: %s: %s", ticker, type(exc).__name__, exc)
            llm_metrics.record_call(
                latency_ms=(time.time() - started) * 1000, generated=False,
                transient_retries=transient_retries, validation_retries=validation_retries,
                model=llm_service._model_name(), prompt_version=MEMO_PROMPT_VERSION,
            )
            return _fallback_memo(research, evidence, "provider unavailable")

        try:
            candidate = MemoNarrative.model_validate(json.loads(content))
            cited = _validate_citations(candidate, valid_ids)
            narrative = candidate
            break
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning("memo validation failed for %s (attempt %d): %s", ticker, attempt + 1, exc)
            if attempt == 0:
                validation_retries += 1
                messages.append({"role": "assistant", "content": content[:2000]})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your reply failed validation: "
                        f"{exc}. Valid citation ids are exactly: {sorted(valid_ids)}. "
                        "Respond again with ONLY the JSON object matching the schema."
                    ),
                })

    llm_metrics.record_call(
        latency_ms=(time.time() - started) * 1000, generated=narrative is not None,
        transient_retries=transient_retries, validation_retries=validation_retries,
        model=llm_service._model_name(), prompt_version=MEMO_PROMPT_VERSION,
    )

    if narrative is None:
        return _fallback_memo(research, evidence, "invalid model output")

    memo = _attach(narrative.model_dump(), research, evidence, cited, generated=True)
    memo["cached"] = False
    with _cache_lock:
        _cache[key] = (time.time() + MEMO_CACHE_TTL_SECONDS, memo)
    logger.info(
        "memo %s: %d evidence items, %d cited, %.0fms",
        ticker, len(evidence), len(cited), (time.time() - started) * 1000,
    )
    return memo
