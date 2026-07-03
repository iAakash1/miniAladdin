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

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

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
            }


llm_metrics = LLMMetrics()
