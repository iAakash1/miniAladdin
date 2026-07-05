"""
OmniSignal LLM Service — Groq `openai/gpt-oss-120b` explanation layer.

Architecture contract (docs/AUDIT.md §3):

    Market data → indicators → macro → Python decision engine
        → deterministic recommendation / confidence / breakdown / risk / rationale
        → THIS SERVICE (explanation only)
        → validated JSON narrative → frontend

The model NEVER generates recommendation, confidence, its breakdown, risk,
rationale, or any indicator/macro value. Those are computed upstream, passed
in as facts, and attached to the result verbatim. The model contributes only
the narrative fields of the v4 schema below — a full research-report layer:
executive summary, investment thesis, bull/bear case, verdict rationale,
per-family impact commentary (momentum, quality, value, PEAD, macro, news),
a synthesis of the biggest positive/negative contributors, catalysts, risks,
things to watch and a closing conclusion.

Family-level "impact" subtotals (momentum/quality/value/PEAD/news) are NOT
computed by the model — ``_group_factor_impacts`` sums the engine's own
per-factor ``contribution`` values (already computed by ``src/scoring/
engine.py``) into presentation buckets before the request is ever sent. This
regrouping is display-only: it does not touch the engine's real scoring
families or weights. The model receives the subtotals as facts and explains
them; it never adds them up itself. There is deliberately no "what changed
since last analysis" field here — that history lives client-side only
(``dashboard/src/lib/history.ts``, browser localStorage), so the backend has
no prior snapshot to narrate; the frontend's own diff view owns that story.

Reliability: singleton client · 8s timeout · exponential backoff on 429/5xx ·
strict ``json.loads`` + Pydantic validation · one corrective retry · then a
deterministic fallback. ``/api/research`` can never fail because of this layer.
Results cache for 5 minutes per (ticker, UTC day, verdict, model).
Observability: per-call latency/retries/outcome recorded in
``src/services/metrics.py`` (internal only).

Environment:
    GROQ_API_KEY   — enables the service (absent → fallback mode, logged once)
    LLM_MODEL      — default "openai/gpt-oss-120b"
    LLM_TIMEOUT    — seconds per API call, default 8
    LLM_CACHE_TTL  — seconds, default 300
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from src.services.metrics import llm_metrics

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
PROMPT_VERSION = "4"
MAX_TRANSIENT_RETRIES = 2      # network / 429 / 5xx, with exponential backoff
BACKOFF_BASE_SECONDS = 0.5
VALIDATION_RETRIES = 1         # one corrective re-ask on malformed output


# ── Response schema (v4 — full research report; deterministic values are inputs) ─

class LLMAnalysis(BaseModel):
    """Strict schema for the model's JSON output. Explanation fields only."""

    executive_summary: str = Field(..., min_length=1, max_length=2000)
    investment_thesis: str = Field("", max_length=1500)
    verdict_rationale: str = Field("", max_length=1000)
    bull_case: str = Field("", max_length=1000)
    bear_case: str = Field("", max_length=1000)
    technical_reasoning: str = Field("", max_length=1500)
    momentum_impact: str = Field("", max_length=800)
    quality_impact: str = Field("", max_length=800)
    value_impact: str = Field("", max_length=800)
    pead_impact: str = Field("", max_length=800)
    macro_reasoning: str = Field("", max_length=1500)
    news_reasoning: str = Field("", max_length=1500)
    risk_reasoning: str = Field("", max_length=1500)
    confidence_reason: str = Field("", max_length=1000)
    top_positive_narrative: str = Field("", max_length=600)
    top_negative_narrative: str = Field("", max_length=600)
    key_catalysts: list[str] = Field(default_factory=list, max_length=10)
    key_risks: list[str] = Field(default_factory=list, max_length=10)
    things_to_watch: list[str] = Field(default_factory=list, max_length=10)
    investment_horizon: str = Field("", max_length=300)
    market_outlook: str = Field("", max_length=1000)
    conclusion: str = Field("", max_length=800)


# ── Factor-impact grouping (presentation layer — see module docstring) ───────

# Maps the engine's own FactorRow.family (src/scoring/engine.py) to a
# narrative "impact" bucket. "pead" is pulled out of "fundamental" into its
# own bucket because it is explicitly called out in the report; the rest of
# "fundamental" (target_upside, earnings_yield, pe_gap) becomes "value";
# "reversal" (the short-horizon contrarian signal) reads to an end user as a
# momentum-family concept, so it is folded into "momentum" here — this does
# NOT change how the engine weights or scores it, only how it is grouped for
# the narrative.
_FAMILY_TO_IMPACT = {
    "momentum": "momentum",
    "reversal": "momentum",
    "quality": "quality",
    "fundamental": "value",
    "news": "news",
}
IMPACT_LABELS = {
    "momentum": "Momentum",
    "quality": "Quality",
    "value": "Value",
    "pead": "Post-earnings drift",
    "news": "News",
}


def _group_factor_impacts(factors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Sum the engine's own per-factor ``contribution`` values into the five
    narrative buckets (momentum, quality, value, pead, news). Pure and
    order-stable; used both to build the LLM payload and could be reused by
    any other consumer that wants the same grouping. Never invents a number —
    every contribution here was already computed by the scoring engine.
    """
    buckets: dict[str, dict[str, Any]] = {
        key: {"contribution": 0.0, "factors": []}
        for key in ("momentum", "quality", "value", "pead", "news")
    }
    for factor in factors:
        name = factor.get("name")
        family = factor.get("family")
        contribution = factor.get("contribution")
        if contribution is None:
            continue
        bucket_key = "pead" if name == "pead" else _FAMILY_TO_IMPACT.get(family)
        if bucket_key is None:
            continue
        bucket = buckets[bucket_key]
        bucket["contribution"] = round(bucket["contribution"] + contribution, 4)
        bucket["factors"].append({"name": name, "contribution": contribution})
    for bucket in buckets.values():
        bucket["factors"].sort(key=lambda f: abs(f["contribution"]), reverse=True)
    return buckets


SYSTEM_PROMPT = """You are OmniSignal Research, writing the narrative layer of an institutional equity research report.

FACTS AND BOUNDARIES
You do not browse the internet and have no knowledge beyond the JSON supplied in the user message. Every number that matters — recommendation, confidence, its breakdown, risk level, risk breakdown, factor contributions, factor-family impact subtotals (momentum, quality, value, PEAD, news), macro readings, technical indicators, sentiment — is already computed by a deterministic engine and handed to you as fact. You never calculate, estimate, re-derive, or adjust any of these numbers. You never invent a number, ticker fact, catalyst, or event that is not present in the supplied JSON. If a field is null, empty, or absent, say plainly that the data was unavailable for that point — never fill the gap with a plausible-sounding guess. You never contradict the supplied decision block, and you never issue a recommendation of your own — the recommendation is the engine's, stated once, and your job is only to explain why it follows from the supplied facts.

OUTPUT
Return one valid JSON object and nothing else — no markdown, no code fences, no commentary before or after. It must parse with a strict parser on the first try.

Schema (every key required; use "" or [] for a section with no supporting data rather than omitting the key):
{
  "executive_summary": "<3-5 sentences: the verdict, the confidence and risk levels, and the two or three supplied numbers that matter most>",
  "investment_thesis": "<the core argument in 3-4 sentences: why this verdict follows from the supplied factor and macro data, as a research analyst would frame it>",
  "verdict_rationale": "<1-2 tight sentences answering directly: why is this a Buy / Hold / Sell, citing the specific supplied scores or factors that tipped it>",
  "bull_case": "<the strongest case FOR the position, built only from supplied factors that point that way — even a HOLD or SELL has a bull case, drawn only from the supplied numbers>",
  "bear_case": "<the strongest case AGAINST the position, built only from supplied factors that point that way — even a BUY has a bear case, drawn only from the supplied numbers>",
  "technical_reasoning": "<how the supplied technical indicators support or oppose the verdict, citing values (e.g. "RSI-14 at 28.4")>",
  "momentum_impact": "<what the supplied momentum_impact subtotal and its listed factors contributed — cite the subtotal number>",
  "quality_impact": "<what the supplied quality_impact subtotal and its listed factors (profitability, issuance, asset growth) contributed — cite the subtotal number>",
  "value_impact": "<what the supplied value_impact subtotal and its listed factors (earnings yield, forward PE gap, analyst target) contributed — cite the subtotal number>",
  "pead_impact": "<what the supplied pead_impact subtotal (post-earnings-announcement drift) contributed — cite the number; if the factor is absent say drift data was unavailable>",
  "macro_reasoning": "<what the supplied macro block (SRM, yield spread, inflation, Fed rate, macro gate) contributed, including any dampening of the raw signal>",
  "news_reasoning": "<what the supplied sentiment block contributed; if headline_count is 0, say sentiment was unavailable>",
  "risk_reasoning": "<why the supplied risk level is what it is, from the supplied risk components/volatility/drawdown/beta/SRM>",
  "confidence_reason": "<explain the supplied confidence using the supplied confidence_breakdown items only — do not invent arithmetic>",
  "top_positive_narrative": "<1-2 sentences synthesizing the supplied top positive contributors — what they are and why they push the score up>",
  "top_negative_narrative": "<1-2 sentences synthesizing the supplied top negative contributors — what they are and why they push the score down>",
  "key_catalysts": ["<short factual bullish drivers from the supplied data>"],
  "key_risks": ["<short factual risk factors from the supplied data>"],
  "things_to_watch": ["<short forward-looking items worth monitoring next — thresholds, upcoming levels or regime shifts implied by the supplied data; do not just repeat key_risks>"],
  "investment_horizon": "<short-term | medium-term | long-term, one clause of justification>",
  "market_outlook": "<1-2 sentences on the macro regime using only the supplied macro block>",
  "conclusion": "<2-3 sentences closing the report: restate the verdict, the single strongest supporting fact, and the single most important thing that would change it>"
}

STYLE
Write like a sell-side research desk: institutional, concise, plain declarative sentences. No hype ("massive", "explosive", "to the moon"), no advice language ("you should buy"), no disclaimers (the API attaches its own), no filler openers ("In conclusion", "It's worth noting that"), no hedge-everything qualifiers. Do not use em dashes, "--", "///" or other decorative separators to join ideas — use a period and a new sentence, or a comma, the way a published research note would. Never use generic AI phrasing ("as an AI", "based on the data provided, it appears that") — state the fact and move on. Every sentence should earn its place by citing or interpreting a specific supplied number; do not pad."""


# ── Client management ─────────────────────────────────────────────────────────

_client = None
_client_lock = threading.Lock()
_missing_key_logged = False


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("LLM_TIMEOUT", "8"))
    except ValueError:
        return 8.0


def _model_name() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


def is_configured() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def _get_client():
    """Reuse a single Groq client (thread-safe lazy init)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from groq import Groq  # imported lazily so tests can run without the SDK

                _client = Groq(
                    api_key=os.getenv("GROQ_API_KEY"),
                    timeout=_timeout_seconds(),
                    max_retries=0,  # retries are handled here, with backoff
                )
    return _client


def reset_client_for_tests() -> None:
    """Test hook: drop the cached client, cache entries and metrics."""
    global _client
    _client = None
    _cache.clear()
    llm_metrics.reset()


# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cache_ttl() -> float:
    try:
        return float(os.getenv("LLM_CACHE_TTL", "300"))
    except ValueError:
        return 300.0


def _cache_key(payload: dict[str, Any]) -> str:
    decision = payload.get("decision", {})
    raw = "|".join(
        [
            str(payload.get("ticker", "")),
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            str(decision.get("verdict", "")),
            _model_name(),
            PROMPT_VERSION,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry[0] > time.time():
            return entry[1]
        if entry:
            del _cache[key]
    return None


def _cache_put(key: str, value: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + _cache_ttl(), value)


# ── Result assembly ───────────────────────────────────────────────────────────

def _attach_deterministic(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Engine values are attached verbatim — the model never supplies them."""
    decision = payload.get("decision", {})
    result["recommendation"] = decision.get("recommendation", "HOLD")
    result["confidence"] = decision.get("confidence", 50)
    result["risk"] = decision.get("risk", "MEDIUM")
    # Factor-impact subtotals are the engine's own numbers (see module
    # docstring) — the frontend renders them alongside the model's narrative.
    result["factor_impacts"] = payload.get("factor_impacts", {})
    return result


def _impact_line(bucket: Optional[dict[str, Any]]) -> str:
    """
    A bare, honest one-liner for a factor-impact bucket using only the
    engine's own subtotal — no narrative flourish, since the fallback path
    has no model to write one. Empty when the bucket has no factors, so the
    UI's conditional rendering hides it like every other blank field.
    """
    if not bucket or not bucket.get("factors"):
        return ""
    return f"Net contribution {bucket['contribution']:+.3f} from the engine's own factor weights."


def _fallback(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    """Deterministic explanation assembled from the engine's own outputs."""
    decision = payload.get("decision", {})
    rationale = decision.get("rationale") or "Signals were synthesized by the quantitative engine."
    breakdown = decision.get("confidence_breakdown") or []
    confidence_reason = (
        " + ".join(f"{item.get('component')} ({item.get('points')}%)" for item in breakdown)
        if breakdown
        else "Confidence reflects agreement between the technical, sentiment and macro factors."
    )
    impacts = payload.get("factor_impacts") or {}
    result = {
        "executive_summary": (
            f"{decision.get('recommendation', 'HOLD')} at {decision.get('confidence', 50)}% confidence. "
            f"{rationale} (AI narrative unavailable: {reason} — showing the engine's own rationale.)"
        ),
        "investment_thesis": "",
        "verdict_rationale": "",
        "bull_case": "",
        "bear_case": "",
        "technical_reasoning": "",
        "momentum_impact": _impact_line(impacts.get("momentum")),
        "quality_impact": _impact_line(impacts.get("quality")),
        "value_impact": _impact_line(impacts.get("value")),
        "pead_impact": _impact_line(impacts.get("pead")),
        "macro_reasoning": "",
        "news_reasoning": "",
        "risk_reasoning": rationale,
        "confidence_reason": confidence_reason,
        "top_positive_narrative": "",
        "top_negative_narrative": "",
        "key_catalysts": [],
        "key_risks": [part.strip() for part in rationale.split(";") if part.strip()][:5],
        "things_to_watch": [],
        "investment_horizon": "",
        "market_outlook": "",
        "conclusion": "",
        "generated": False,
        "model": None,
        "cached": False,
    }
    return _attach_deterministic(result, payload)


# ── Core call ─────────────────────────────────────────────────────────────────

def _chat_once(messages: list[dict[str, str]]) -> str:
    """One completion call with deterministic parameters. Raises on failure."""
    client = _get_client()
    completion = client.chat.completions.create(
        model=_model_name(),
        messages=messages,
        temperature=0.2,
        top_p=1,
        reasoning_effort="medium",
        max_completion_tokens=4096,
        stream=False,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("empty completion content")
    return content


def _is_transient(exc: Exception) -> bool:
    """Rate limits, timeouts and 5xx are retryable; everything else is not."""
    name = type(exc).__name__
    if name in {"RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError"}:
        return True
    status = getattr(exc, "status_code", None)
    return status in (429, 500, 502, 503, 504)


def _call_with_retries(messages: list[dict[str, str]]) -> tuple[str, int]:
    """Returns (content, transient_retry_count). Raises on terminal failure."""
    last: Exception = RuntimeError("no attempt made")
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            return _chat_once(messages), attempt
        except Exception as exc:  # noqa: BLE001 — categorized below
            last = exc
            if _is_transient(exc) and attempt < MAX_TRANSIENT_RETRIES:
                delay = BACKOFF_BASE_SECONDS * (2**attempt)
                logger.warning(
                    "LLM transient failure (%s), retry %d/%d in %.1fs",
                    type(exc).__name__, attempt + 1, MAX_TRANSIENT_RETRIES, delay,
                )
                time.sleep(delay)
                continue
            raise
    raise last


def _parse_and_validate(content: str) -> LLMAnalysis:
    """Strict json.loads → Pydantic. No preprocessing, by design."""
    return LLMAnalysis.model_validate(json.loads(content))


# ── Public API ────────────────────────────────────────────────────────────────

def explain_recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Generate (or retrieve from cache) a validated narrative explanation for an
    already-computed decision. Never raises; always returns a serializable
    dict with a ``generated`` flag and the engine's deterministic values
    attached verbatim.
    """
    global _missing_key_logged

    if not is_configured():
        if not _missing_key_logged:
            logger.warning("GROQ_API_KEY not set — LLM explanations disabled, serving fallbacks")
            _missing_key_logged = True
        return _fallback(payload, "not configured")

    key = _cache_key(payload)
    cached = _cache_get(key)
    if cached is not None:
        llm_metrics.record_cache_hit()
        return {**cached, "cached": True}

    decision = payload.get("decision", {})
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]

    started = time.time()
    analysis: Optional[LLMAnalysis] = None
    transient_retries = 0
    validation_retries_used = 0

    for validation_attempt in range(VALIDATION_RETRIES + 1):
        try:
            content, attempt_retries = _call_with_retries(messages)
            transient_retries += attempt_retries
        except Exception as exc:  # noqa: BLE001 — terminal failure → fallback
            logger.warning(
                "LLM call failed for %s after retries: %s: %s",
                payload.get("ticker"), type(exc).__name__, exc,
            )
            llm_metrics.record_call(
                latency_ms=(time.time() - started) * 1000,
                generated=False,
                transient_retries=transient_retries,
                validation_retries=validation_retries_used,
                model=_model_name(),
                prompt_version=PROMPT_VERSION,
            )
            return _fallback(payload, "provider unavailable")

        try:
            analysis = _parse_and_validate(content)
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "LLM returned invalid JSON for %s (attempt %d): %s",
                payload.get("ticker"), validation_attempt + 1, exc,
            )
            if validation_attempt < VALIDATION_RETRIES:
                validation_retries_used += 1
                messages.append({"role": "assistant", "content": content[:2000]})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON matching the schema. "
                        "Respond again with ONLY the JSON object — no other text."
                    ),
                })

    latency_ms = (time.time() - started) * 1000
    llm_metrics.record_call(
        latency_ms=latency_ms,
        generated=analysis is not None,
        transient_retries=transient_retries,
        validation_retries=validation_retries_used,
        model=_model_name(),
        prompt_version=PROMPT_VERSION,
    )

    if analysis is None:
        return _fallback(payload, "invalid model output")

    result = _attach_deterministic(analysis.model_dump(), payload)
    result.update({
        "generated": True,
        "model": _model_name(),
        "cached": False,
    })
    logger.info(
        "LLM explanation for %s in %.0fms (model=%s prompt=v%s retries=%d/%d)",
        payload.get("ticker"), latency_ms, _model_name(), PROMPT_VERSION,
        transient_retries, validation_retries_used,
    )
    _cache_put(key, result)
    return result


def build_payload(
    ticker: str,
    recommendation: str,
    confidence: int,
    risk: str,
    verdict: str,
    rationale: str,
    macro: dict[str, Any],
    technicals: dict[str, Any],
    sentiment: Optional[dict[str, Any]],
    confidence_breakdown: Optional[list[dict[str, Any]]] = None,
    quant: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the structured facts the model is allowed to reference."""
    headlines = []
    if sentiment and sentiment.get("headlines"):
        headlines = [
            {"title": h.get("title"), "score": h.get("score"), "label": h.get("label")}
            for h in sentiment["headlines"][:8]
        ]
    factor_impacts = _group_factor_impacts((quant or {}).get("factors") or [])
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "quant": quant,  # v2 scorecard summary: family scores, weights, regimes
        # Presentation-layer subtotals (see module docstring) — deterministic,
        # summed from the engine's own per-factor contributions above.
        "factor_impacts": factor_impacts,
        "decision": {
            "recommendation": recommendation,
            "confidence": confidence,
            "confidence_breakdown": confidence_breakdown or [],
            "risk": risk,
            "verdict": verdict,
            "rationale": rationale,
        },
        "macro": macro,
        "technicals": technicals,
        "sentiment": {
            "average_score": sentiment.get("average_score") if sentiment else None,
            "dominant_label": sentiment.get("dominant_label") if sentiment else None,
            "headline_count": sentiment.get("headline_count", 0) if sentiment else 0,
            "headlines": headlines,
        },
    }
