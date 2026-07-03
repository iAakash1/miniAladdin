"""
OmniSignal LLM Service — Groq `openai/gpt-oss-120b` explanation layer.

Design contract (docs/AUDIT.md §3):

* Python is the single source of truth. Verdict, confidence and risk level are
  computed deterministically *before* this service is called and passed in as
  facts. The model's job is exclusively to explain them; after validation, the
  deterministic fields are overwritten with the Python values regardless of
  what the model returned.
* The model never fetches data, never calculates indicators, never invents
  numbers. The system prompt forbids it and the payload is the only context.
* Output must be strict JSON parseable by ``json.loads`` — validated against a
  Pydantic schema, retried once with a corrective message on validation
  failure, then replaced by a deterministic fallback. A slow or failing LLM
  can never take down ``/api/research/{ticker}``.
* Deterministic sampling: ``temperature=0.2, top_p=1,
  reasoning_effort="medium", max_completion_tokens=4096, stream=False``.
* Identical requests are served from a 5-minute in-process cache keyed on
  (ticker, UTC date, verdict, model).

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
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_TRANSIENT_RETRIES = 2      # network / 429 / 5xx, with exponential backoff
BACKOFF_BASE_SECONDS = 0.5
VALIDATION_RETRIES = 1         # one corrective re-ask on malformed output


# ── Response schema ───────────────────────────────────────────────────────────

class LLMAnalysis(BaseModel):
    """Strict schema for the model's JSON output."""

    recommendation: Literal["BUY", "SELL", "HOLD"]
    confidence: int = Field(..., ge=0, le=100)
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    summary: str = Field(..., min_length=1, max_length=2000)
    bullish_factors: list[str] = Field(default_factory=list, max_length=10)
    bearish_factors: list[str] = Field(default_factory=list, max_length=10)
    reasoning: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    investment_horizon: str = ""
    market_outlook: str = Field("", max_length=1000)


SYSTEM_PROMPT = """You are OmniSignal AI, an expert financial research assistant.

You do NOT browse the internet. You ONLY analyze the structured information provided in the user message. Never fabricate information. Never guess missing values — if a value is null or absent, say the data is insufficient for that point instead of inventing it. Never calculate indicators yourself; every number you may reference is already computed and given to you.

The provided `decision` block (recommendation, confidence, risk) was produced by a deterministic quantitative engine. Do not contradict it — your job is to explain WHY the engine reached it, citing only the supplied numbers.

Return valid JSON only. No markdown, no code fences, no tables, no text outside the JSON object. The JSON must parse with a strict parser.

Schema (all keys required):
{
  "recommendation": "BUY" | "SELL" | "HOLD",           // echo decision.recommendation
  "confidence": <integer 0-100>,                        // echo decision.confidence
  "risk": "LOW" | "MEDIUM" | "HIGH",                   // echo decision.risk
  "summary": "<3-5 plain-English sentences explaining why the verdict is what it is, citing specific supplied numbers>",
  "bullish_factors": ["<short factual statements from the supplied data>"],
  "bearish_factors": ["<short factual statements from the supplied data>"],
  "reasoning": ["<step-by-step chain from data to verdict, one step per item>"],
  "limitations": ["<what the supplied data cannot tell us, incl. any null fields>"],
  "investment_horizon": "<short-term | medium-term | long-term, with one clause of justification>",
  "market_outlook": "<1-2 sentences on the macro regime using only the supplied macro block>"
}

Style: professional research-desk register. No hype, no advice language ("you should buy"), no disclaimers (the API attaches one). Cite numbers as given (e.g. "RSI-14 at 39.1")."""


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
    """Test hook: drop the cached client and cache entries."""
    global _client
    _client = None
    _cache.clear()


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


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    """Deterministic explanation assembled from the engine's own rationale."""
    decision = payload.get("decision", {})
    rationale = decision.get("rationale") or "Signals were synthesized by the quantitative engine."
    summary = (
        f"{decision.get('recommendation', 'HOLD')} at {decision.get('confidence', 50)}% confidence. "
        f"{rationale} (AI narrative unavailable: {reason} — showing the engine's own rationale.)"
    )
    return {
        "recommendation": decision.get("recommendation", "HOLD"),
        "confidence": decision.get("confidence", 50),
        "risk": decision.get("risk", "MEDIUM"),
        "summary": summary,
        "bullish_factors": [],
        "bearish_factors": [],
        "reasoning": [part.strip() for part in rationale.split(";") if part.strip()],
        "limitations": ["AI-generated narrative unavailable for this response."],
        "investment_horizon": "",
        "market_outlook": "",
        "generated": False,
        "model": None,
        "cached": False,
    }


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


def _call_with_retries(messages: list[dict[str, str]]) -> str:
    last: Exception = RuntimeError("no attempt made")
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            return _chat_once(messages)
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
    Generate (or retrieve from cache) a validated explanation for an
    already-computed decision.

    ``payload`` must contain a ``decision`` block with the deterministic
    ``recommendation`` / ``confidence`` / ``risk`` / ``verdict`` / ``rationale``
    plus whatever computed facts the model should explain (technicals, macro,
    sentiment). Never raises; always returns a serializable dict with a
    ``generated`` flag.
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
        return {**cached, "cached": True}

    decision = payload.get("decision", {})
    user_message = json.dumps(payload, ensure_ascii=False, default=str)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    started = time.time()
    analysis: Optional[LLMAnalysis] = None

    for validation_attempt in range(VALIDATION_RETRIES + 1):
        try:
            content = _call_with_retries(messages)
        except Exception as exc:  # noqa: BLE001 — terminal failure → fallback
            logger.warning(
                "LLM call failed for %s after retries: %s: %s",
                payload.get("ticker"), type(exc).__name__, exc,
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
                messages.append({"role": "assistant", "content": content[:2000]})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON matching the schema. "
                        "Respond again with ONLY the JSON object — no other text."
                    ),
                })

    if analysis is None:
        return _fallback(payload, "invalid model output")

    # Deterministic override: the engine's numbers win, always.
    result = analysis.model_dump()
    for field, engine_value in (
        ("recommendation", decision.get("recommendation")),
        ("confidence", decision.get("confidence")),
        ("risk", decision.get("risk")),
    ):
        if engine_value is not None and result.get(field) != engine_value:
            logger.info(
                "LLM %s (%r) disagreed with engine (%r) for %s — engine value enforced",
                field, result.get(field), engine_value, payload.get("ticker"),
            )
            result[field] = engine_value

    result.update({
        "generated": True,
        "model": _model_name(),
        "cached": False,
    })
    logger.info(
        "LLM explanation for %s in %.2fs (model=%s)",
        payload.get("ticker"), time.time() - started, _model_name(),
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
        "decision": {
            "recommendation": recommendation,
            "confidence": confidence,
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
