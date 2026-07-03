"""
VendorClient — the base every vendor adapter builds on.

Provides, per vendor:
  * key management (adapter is `available` only when its env key exists;
    keyless vendors like yfinance/Yahoo RSS are always available)
  * token-bucket rate limiting (defaults per free tier, override with
    PROVIDER_<NAME>_RPM)
  * hard timeout per request
  * bounded retries with exponential backoff on transient failures
  * health statistics: totals, success %, consecutive failures, avg/max
    latency, last error — feeding the orchestrator's routing decisions
  * cooldown circuit: after N consecutive failures the vendor is skipped
    by fallback chains until the cooldown elapses
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class RateLimiter:
    """Token bucket: `rpm` requests per minute, thread-safe, non-blocking check."""

    def __init__(self, rpm: int):
        self.capacity = max(1, rpm)
        self.tokens = float(self.capacity)
        self.refill_per_sec = self.capacity / 60.0
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class VendorStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.successes = 0
        self.failures = 0
        self.rate_limited = 0
        self.consecutive_failures = 0
        self.total_latency_ms = 0.0
        self.max_latency_ms = 0.0
        self.last_error: Optional[str] = None
        self.last_success_at: Optional[float] = None

    def record(self, ok: bool, latency_ms: float, error: Optional[str] = None) -> None:
        with self._lock:
            self.total += 1
            self.total_latency_ms += latency_ms
            self.max_latency_ms = max(self.max_latency_ms, latency_ms)
            if ok:
                self.successes += 1
                self.consecutive_failures = 0
                self.last_success_at = time.time()
            else:
                self.failures += 1
                self.consecutive_failures += 1
                self.last_error = (error or "unknown")[:300]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = self.total_latency_ms / self.total if self.total else 0.0
            return {
                "requests": self.total,
                "success_pct": round(100.0 * self.successes / self.total, 1) if self.total else None,
                "failures": self.failures,
                "rate_limited": self.rate_limited,
                "consecutive_failures": self.consecutive_failures,
                "avg_latency_ms": round(avg, 1),
                "max_latency_ms": round(self.max_latency_ms, 1),
                "last_error": self.last_error,
            }


class VendorError(Exception):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class VendorClient:
    """Base adapter. Subclasses set NAME / KEY_ENV / DEFAULT_RPM and use _get_json."""

    NAME = "vendor"
    KEY_ENV: Optional[str] = None          # None → keyless vendor
    DEFAULT_RPM = 30
    TIMEOUT_SECONDS = 6.0
    MAX_RETRIES = 2
    BACKOFF_BASE = 0.4
    COOLDOWN_AFTER_FAILURES = 3
    COOLDOWN_SECONDS = 60.0

    def __init__(self, session: Optional[requests.Session] = None):
        rpm_override = os.getenv(f"PROVIDER_{self.NAME.upper()}_RPM")
        rpm = int(rpm_override) if rpm_override and rpm_override.isdigit() else self.DEFAULT_RPM
        self.rate_limiter = RateLimiter(rpm)
        self.stats = VendorStats()
        self._cooldown_until = 0.0
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", "OmniSignal/2.0 (+https://mini-aladding.vercel.app)")

    # ── Availability & health ────────────────────────────────────────────────

    @property
    def api_key(self) -> str:
        return os.getenv(self.KEY_ENV, "") if self.KEY_ENV else ""

    @property
    def available(self) -> bool:
        """Key present (or keyless). Read at call time so env changes apply."""
        if self.KEY_ENV is None:
            return True
        return bool(self.api_key and len(self.api_key) > 5)

    @property
    def healthy(self) -> bool:
        """Available and not cooling down after repeated failures."""
        return self.available and time.monotonic() >= self._cooldown_until

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "vendor": self.NAME,
            "configured": self.available,
            "cooling_down": time.monotonic() < self._cooldown_until,
            **self.stats.snapshot(),
        }

    # ── HTTP core ────────────────────────────────────────────────────────────

    def _get_json(self, url: str, params: Optional[dict[str, Any]] = None,
                  headers: Optional[dict[str, str]] = None) -> Any:
        return self._request_json("GET", url, params=params, headers=headers)

    def _post_json(self, url: str, json_body: dict[str, Any],
                   headers: Optional[dict[str, str]] = None) -> Any:
        return self._request_json("POST", url, json_body=json_body, headers=headers)

    def timed_call(self, fn):
        """
        Wrap a library call (yfinance, fredapi) with the same rate limiting,
        stats and cooldown behavior as HTTP adapters.
        """
        if not self.rate_limiter.try_acquire():
            self.stats.rate_limited += 1
            raise VendorError(f"{self.NAME}: local rate limit reached", transient=True)
        started = time.perf_counter()
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001 — normalized to VendorError
            latency = (time.perf_counter() - started) * 1000
            self.stats.record(False, latency, str(exc))
            if self.stats.consecutive_failures >= self.COOLDOWN_AFTER_FAILURES:
                self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            raise VendorError(f"{self.NAME}: {exc}", transient=True) from exc
        self.stats.record(True, (time.perf_counter() - started) * 1000)
        return value

    def _request_json(self, method: str, url: str,
                      params: Optional[dict[str, Any]] = None,
                      json_body: Optional[dict[str, Any]] = None,
                      headers: Optional[dict[str, str]] = None) -> Any:
        """
        HTTP with rate limiting, timeout, bounded retries + exponential backoff.
        Raises VendorError on terminal failure; records stats either way.
        """
        if not self.rate_limiter.try_acquire():
            self.stats.rate_limited += 1
            raise VendorError(f"{self.NAME}: local rate limit reached", transient=True)

        last_error: Optional[VendorError] = None
        for attempt in range(self.MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                response = self._session.request(
                    method, url, params=params, json=json_body,
                    headers=headers, timeout=self.TIMEOUT_SECONDS,
                )
                latency = (time.perf_counter() - started) * 1000
                if response.status_code in TRANSIENT_STATUS:
                    raise VendorError(f"HTTP {response.status_code}", transient=True)
                response.raise_for_status()
                payload = response.json()
                self.stats.record(True, latency)
                return payload
            except VendorError as exc:
                latency = (time.perf_counter() - started) * 1000
                last_error = exc
            except requests.Timeout:
                latency = (time.perf_counter() - started) * 1000
                last_error = VendorError("timeout", transient=True)
            except requests.RequestException as exc:
                latency = (time.perf_counter() - started) * 1000
                last_error = VendorError(str(exc), transient=True)
            except ValueError as exc:  # JSON decode
                latency = (time.perf_counter() - started) * 1000
                last_error = VendorError(f"invalid JSON: {exc}", transient=False)

            self.stats.record(False, latency, str(last_error))
            if last_error.transient and attempt < self.MAX_RETRIES:
                time.sleep(self.BACKOFF_BASE * (2 ** attempt))
                continue
            break

        if self.stats.consecutive_failures >= self.COOLDOWN_AFTER_FAILURES:
            self._cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            logger.warning("%s cooling down for %.0fs after %d consecutive failures",
                           self.NAME, self.COOLDOWN_SECONDS, self.stats.consecutive_failures)
        assert last_error is not None
        raise last_error
