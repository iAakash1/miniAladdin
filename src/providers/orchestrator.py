"""
FallbackChain — the routing brain of every provider.

Given an ordered list of (vendor, fetch_fn) pairs it:
  1. serves fresh cache when present (after single-flight dedupe),
  2. walks healthy vendors in order until one answers,
  3. optionally cross-validates numeric answers against a second vendor
     and scores confidence from their agreement,
  4. serves a *stale* cached value as the institutional last resort,
  5. reports every vendor consulted in the result envelope.

The frontend never learns which vendor answered — it sees one schema.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Generic, Optional, TypeVar

from src.providers.base import VendorClient, VendorError
from src.providers.cache import CacheBackend
from src.providers.dedupe import SingleFlight
from src.providers.schemas import ProviderResult, SourceReading

logger = logging.getLogger(__name__)

T = TypeVar("T")

FetchFn = Callable[[], T]
NumericExtractor = Callable[[T], Optional[float]]

# Confidence policy (documented in schemas.ProviderResult)
CONF_MULTI_AGREE = 1.0
CONF_PRIMARY = 0.85
CONF_FALLBACK = 0.70
CONF_DISAGREE = 0.50
CONF_STALE = 0.30
AGREE_TOLERANCE = 0.005   # 0.5 % → full agreement
DISAGREE_TOLERANCE = 0.02  # > 2 % → material disagreement


class ChainLink(Generic[T]):
    def __init__(self, vendor: VendorClient, fetch: FetchFn):
        self.vendor = vendor
        self.fetch = fetch


class FallbackChain(Generic[T]):
    def __init__(
        self,
        name: str,
        cache: CacheBackend,
        single_flight: SingleFlight,
        ttl_seconds: float,
    ):
        self.name = name
        self.cache = cache
        self.single_flight = single_flight
        self.ttl = ttl_seconds

    # ── public ───────────────────────────────────────────────────────────────

    def execute(
        self,
        cache_key: str,
        links: list[ChainLink[T]],
        cross_validate: Optional[NumericExtractor[T]] = None,
    ) -> ProviderResult[T]:
        """Resolve through cache → vendors → stale cache. Never raises."""
        cached = self.cache.get(cache_key)
        if cached is not None:
            result, is_stale = cached
            if not is_stale:
                return result.model_copy(update={"cached": True})

        def _fetch() -> ProviderResult[T]:
            return self._resolve(cache_key, links, cross_validate)

        try:
            return self.single_flight.do(cache_key, _fetch)
        except Exception:  # noqa: BLE001 — absolute backstop, _resolve shouldn't raise
            logger.exception("%s: unexpected orchestrator failure for %s", self.name, cache_key)
            return self._stale_or_empty(cache_key, "internal error")

    # ── internals ────────────────────────────────────────────────────────────

    def _resolve(
        self,
        cache_key: str,
        links: list[ChainLink[T]],
        cross_validate: Optional[NumericExtractor[T]],
    ) -> ProviderResult[T]:
        consulted: list[str] = []
        readings: list[SourceReading] = []
        primary_result: Optional[T] = None
        primary_vendor = ""
        used_fallback = False

        eligible = [l for l in links if l.vendor.healthy]
        skipped = [l.vendor.NAME for l in links if not l.vendor.healthy]
        if skipped:
            logger.debug("%s: skipping unhealthy/unconfigured vendors: %s", self.name, skipped)
        # If literally everything is cooling down, retry the configured ones anyway.
        if not eligible:
            eligible = [l for l in links if l.vendor.available]

        for index, link in enumerate(eligible):
            consulted.append(link.vendor.NAME)
            started = time.perf_counter()
            try:
                value = link.fetch()
            except VendorError as exc:
                logger.info("%s: %s failed (%s), falling through", self.name, link.vendor.NAME, exc)
                continue
            except Exception:  # noqa: BLE001 — adapter bug; log loudly, keep chain alive
                logger.exception("%s: %s adapter raised unexpectedly", self.name, link.vendor.NAME)
                continue
            if value is None:
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            primary_result = value
            primary_vendor = link.vendor.NAME
            used_fallback = index > 0
            if cross_validate is not None:
                metric = cross_validate(value)
                if metric is not None:
                    readings.append(SourceReading(vendor=primary_vendor, value=metric, latency_ms=latency_ms))
            break

        if primary_result is None:
            return self._stale_or_empty(cache_key, "all vendors failed")

        confidence = CONF_FALLBACK if used_fallback else CONF_PRIMARY
        disagreement = False

        # Cross-validation: ask the next healthy vendor for a second opinion.
        if cross_validate is not None and readings:
            second = self._second_opinion(
                [l for l in eligible if l.vendor.NAME != primary_vendor],
                cross_validate,
                consulted,
                readings,
            )
            if second is not None:
                base = readings[0].value
                if base:
                    delta = abs(second - base) / abs(base)
                    if delta <= AGREE_TOLERANCE:
                        confidence = CONF_MULTI_AGREE
                    elif delta > DISAGREE_TOLERANCE:
                        confidence = CONF_DISAGREE
                        disagreement = True
                        logger.warning(
                            "%s: source disagreement on %s — %s=%.4f vs %.4f (Δ %.2f%%)",
                            self.name, cache_key, primary_vendor, base, second, delta * 100,
                        )
                    # 0.5–2 %: keep the single-source confidence

        result: ProviderResult[T] = ProviderResult(
            data=primary_result,
            source=primary_vendor,
            sources_consulted=consulted,
            readings=readings,
            confidence=confidence,
            disagreement=disagreement,
        )
        self.cache.set(cache_key, result, self.ttl)
        return result

    def _second_opinion(
        self,
        remaining: list[ChainLink[T]],
        extractor: NumericExtractor[T],
        consulted: list[str],
        readings: list[SourceReading],
    ) -> Optional[float]:
        for link in remaining[:1]:  # exactly one validation call — quota-aware
            consulted.append(link.vendor.NAME)
            started = time.perf_counter()
            try:
                value = link.fetch()
            except Exception:  # noqa: BLE001 — validation is best-effort
                return None
            if value is None:
                return None
            metric = extractor(value)
            if metric is not None:
                readings.append(SourceReading(
                    vendor=link.vendor.NAME, value=metric,
                    latency_ms=(time.perf_counter() - started) * 1000,
                ))
            return metric
        return None

    def _stale_or_empty(self, cache_key: str, reason: str) -> ProviderResult[T]:
        cached = self.cache.get(cache_key)
        if cached is not None:
            stale_result, _ = cached
            logger.warning("%s: serving STALE cache for %s (%s)", self.name, cache_key, reason)
            return stale_result.model_copy(update={
                "cached": True, "stale": True, "confidence": CONF_STALE,
            })
        return ProviderResult(data=None, error=reason, confidence=0.0)
