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
the narrative fields of the v3 schema below.

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
PROMPT_VERSION = "3"
MAX_TRANSIENT_RETRIES = 2      # network / 429 / 5xx, with exponential backoff
BACKOFF_BASE_SECONDS = 0.5
VALIDATION_RETRIES = 1         # one corrective re-ask on malformed output


# ── Response schema (v3 — narrative only; deterministic values are inputs) ───

class LLMAnalysis(BaseModel):
    """Strict schema for the model's JSON output. Explanation fields only."""

    executive_summary: str = Field(..., min_length=1, max_length=2000)
    bull_case: str = Field("", max_length=1000)
    bear_case: str = Field("", max_length=1000)
    technical_reasoning: str = Field("", max_length=1500)
    macro_reasoning: str = Field("", max_length=1500)
    news_reasoning: str = Field("", max_length=1500)
    risk_reasoning: str = Field("", max_length=1500)
    confidence_reason: str = Field("", max_length=1000)
    key_catalysts: list[str] = Field(default_factory=list, max_length=10)
    key_risks: list[str] = Field(default_factory=list, max_length=10)
    things_to_watch: list[str] = Field(default_factory=list, max_length=10)
    investment_horizon: str = Field("", max_length=300)
    market_outlook: str = Field("", max_length=1000)


SYSTEM_PROMPT = """You are OmniSignal AI, an expert financial research assistant.

You do NOT browse the internet. You ONLY analyze the structured information provided in the user message. Never fabricate information. Never guess missing values — if a value is null or absent, note that the data is insufficient for that point instead of inventing it. Never calculate anything: every number you may reference (indicators, macro series, scores, confidence, its breakdown, risk level, recommendation) is already computed by a deterministic engine and given to you as fact.

Your only job is to EXPLAIN the engine's decision in professional plain English, citing the supplied numbers exactly as given (e.g. "RSI-14 at 39.1"). Do not contradict the decision block. Do not restate a recommendation of your own.

Return valid JSON only. No markdown, no code fences, no tables, no text outside the JSON object. It must parse with a strict parser.

Schema (all keys required; use "" or [] when a section has no data):
{
  "executive_summary": "<3-5 sentences: what the verdict is and the main reasons why, citing supplied numbers>",
  "bull_case": "<the strongest case FOR the position, built only from supplied factors that point that way — even for a HOLD or SELL verdict, state what a bull would point to>",
  "bear_case": "<the strongest case AGAINST the position, built only from supplied factors that point that way — even for a BUY verdict, state what a bear would point to>",
  "technical_reasoning": "<how the supplied technical indicators support or oppose the verdict>",
  "macro_reasoning": "<what the supplied macro block (SRM, yield spread, inflation, Fed rate) contributed, including any dampening>",
  "news_reasoning": "<what the supplied sentiment block contributed; if headline_count is 0, say sentiment was unavailable>",
  "risk_reasoning": "<why the supplied risk level is what it is, from volatility/drawdown/beta/SRM given>",
  "confidence_reason": "<explain the supplied confidence using the supplied confidence_breakdown items — do not invent arithmetic>",
  "key_catalysts": ["<short factual bullish drivers from the supplied data>"],
  "key_risks": ["<short factual risk factors from the supplied data>"],
  "things_to_watch": ["<short forward-looking items worth monitoring next — upcoming levels, thresholds or regime shifts implied by the supplied data; do not just repeat key_risks>"],
  "investment_horizon": "<short-term | medium-term | long-term, one clause of justification>",
  "market_outlook": "<1-2 sentences on the macro regime using only the supplied macro block>"
}

bull_case and bear_case must both be present regardless of verdict — a HOLD still has a case on each side, drawn only from the supplied numbers. things_to_watch is forward-looking (what could change the picture), not a restatement of key_risks (what is true now).

Style: research-desk register. No hype, no advice language, no disclaimers (the API attaches one)."""


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

def _attach_deterministic(result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Engine values are attached verbatim — the model never supplies them."""
    result["recommendation"] = decision.get("recommendation", "HOLD")
    result["confidence"] = decision.get("confidence", 50)
    result["risk"] = decision.get("risk", "MEDIUM")
    return result


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
    result = {
        "executive_summary": (
            f"{decision.get('recommendation', 'HOLD')} at {decision.get('confidence', 50)}% confidence. "
            f"{rationale} (AI narrative unavailable: {reason} — showing the engine's own rationale.)"
        ),
        "bull_case": "",
        "bear_case": "",
        "technical_reasoning": "",
        "macro_reasoning": "",
        "news_reasoning": "",
        "risk_reasoning": rationale,
        "confidence_reason": confidence_reason,
        "key_catalysts": [],
        "key_risks": [part.strip() for part in rationale.split(";") if part.strip()][:5],
        "things_to_watch": [],
        "investment_horizon": "",
        "market_outlook": "",
        "generated": False,
        "model": None,
        "cached": False,
    }
    return _attach_deterministic(result, decision)


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

    result = _attach_deterministic(analysis.model_dump(), decision)
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
    return {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "quant": quant,  # v2 scorecard summary: family scores, weights, regimes
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
