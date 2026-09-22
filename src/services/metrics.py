"""
Internal LLM observability. Aggregates are held in-process and logged —
deliberately not exposed on any endpoint (audit phase 7: "store internally,
do not expose unless requested").
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional


class LLMMetrics:
    """Thread-safe counters for the LLM explanation layer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self.calls = 0
            self.generated = 0
            self.fallbacks = 0
            self.cache_hits = 0
            self.transient_retries = 0
            self.validation_retries = 0
            self.total_latency_ms = 0.0
            self.max_latency_ms = 0.0
            self.last_model: Optional[str] = None
            self.last_prompt_version: Optional[str] = None
            self.last_generated_at: Optional[str] = None
            self.stage_calls: dict[str, int] = {}
            self.stage_failures: dict[str, int] = {}
            self.stage_cache_hits: dict[str, int] = {}
            self.singleflight_waits = 0
            self.input_tokens = 0
            self.output_tokens = 0
            self.cache_hit_tokens = 0
            self.cache_miss_tokens = 0
            self.stage_latency_ms: dict[str, float] = {}

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def record_stage_cache_hit(self, provider: str, stage: str) -> None:
        """Record reuse without exposing prompts, payloads or credentials."""
        key = f"{provider}.{stage}"
        with self._lock:
            self.stage_cache_hits[key] = self.stage_cache_hits.get(key, 0) + 1

    def record_singleflight_wait(self) -> None:
        with self._lock:
            self.singleflight_waits += 1

    def record_validation_retry(self) -> None:
        """Count a schema correction without retaining model output."""
        with self._lock:
            self.validation_retries += 1

    def record_stage(
        self,
        *,
        provider: str,
        model: str,
        stage: str,
        latency_ms: float,
        success: bool,
        retries: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0,
    ) -> None:
        """Aggregate cost/reliability telemetry for a provider-neutral stage."""
        key = f"{provider}.{stage}"
        with self._lock:
            self.stage_calls[key] = self.stage_calls.get(key, 0) + 1
            if not success:
                self.stage_failures[key] = self.stage_failures.get(key, 0) + 1
            self.stage_latency_ms[key] = self.stage_latency_ms.get(key, 0.0) + latency_ms
            self.transient_retries += retries
            self.input_tokens += max(0, input_tokens)
            self.output_tokens += max(0, output_tokens)
            self.cache_hit_tokens += max(0, cache_hit_tokens)
            self.cache_miss_tokens += max(0, cache_miss_tokens)
            self.last_model = model
            self.last_generated_at = datetime.now(timezone.utc).isoformat()

    def record_call(
        self,
        *,
        latency_ms: float,
        generated: bool,
        transient_retries: int,
        validation_retries: int,
        model: str,
        prompt_version: str,
    ) -> None:
        with self._lock:
            self.calls += 1
            if generated:
                self.generated += 1
            else:
                self.fallbacks += 1
            self.transient_retries += transient_retries
            self.validation_retries += validation_retries
            self.total_latency_ms += latency_ms
            self.max_latency_ms = max(self.max_latency_ms, latency_ms)
            self.last_model = model
            self.last_prompt_version = prompt_version
            self.last_generated_at = datetime.now(timezone.utc).isoformat()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = self.total_latency_ms / self.calls if self.calls else 0.0
            return {
                "calls": self.calls,
                "generated": self.generated,
                "fallbacks": self.fallbacks,
                "cache_hits": self.cache_hits,
                "transient_retries": self.transient_retries,
                "validation_retries": self.validation_retries,
                "avg_latency_ms": round(avg, 1),
                "max_latency_ms": round(self.max_latency_ms, 1),
                "last_model": self.last_model,
                "last_prompt_version": self.last_prompt_version,
                "last_generated_at": self.last_generated_at,
                "stage_calls": dict(self.stage_calls),
                "stage_failures": dict(self.stage_failures),
                "stage_cache_hits": dict(self.stage_cache_hits),
                "singleflight_waits": self.singleflight_waits,
                "tokens": {
                    "input": self.input_tokens,
                    "output": self.output_tokens,
                    "cache_hit_input": self.cache_hit_tokens,
                    "cache_miss_input": self.cache_miss_tokens,
                },
                "stage_avg_latency_ms": {
                    key: round(total / self.stage_calls[key], 1)
                    for key, total in self.stage_latency_ms.items()
                    if self.stage_calls.get(key)
                },
            }


llm_metrics = LLMMetrics()
