"""Verified company identity through Logo.dev.

The visual layer deliberately exposes only factual brand identity. Generic
stock photography is not evidence about a company and is excluded from the
runtime, capability registry, and client payloads.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from src.providers.vendors.visual_vendors import LogoDevVendor
from src.services.cache_policy import put_ttl

logger = logging.getLogger(__name__)

IDENTITY_TTL_SECONDS = 604_800.0


class _Cache:
    def __init__(self, max_entries: int = 256) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            expires, value = entry
            if time.monotonic() > expires:
                self._data.pop(key, None)
                return None
            return value

    def put(self, key: str, value: Any, ttl: float) -> None:
        now = time.monotonic()
        with self._lock:
            put_ttl(
                self._data, key, now + ttl, value,
                max_entries=self._max_entries, now=now,
            )

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._data)}


_identity_cache = _Cache()
_logo = LogoDevVendor()

# Consumed by the capability matrix. It is identity-only by design.
IMAGE_VENDORS = [_logo]


def reset_for_tests() -> None:
    _identity_cache._data.clear()


def resolve_domain(symbol: str, name: str = "") -> str:
    """Recover a company domain when no profile vendor supplied one."""
    if not name.strip() or not _logo.secret:
        return ""
    cache_key = f"domain|{symbol.upper()}|{name.strip().lower()}"
    cached = _identity_cache.get(cache_key)
    if cached is not None:
        return cached

    domain = ""
    try:
        results = _logo.search_brand(name.strip()) or []
        for row in results:
            if isinstance(row, dict) and row.get("domain"):
                domain = str(row["domain"]).lower()
                break
    except Exception:  # noqa: BLE001 — identity enrichment is never fatal
        logger.debug("brand search failed for %s", symbol)
        return ""

    _identity_cache.put(cache_key, domain, IDENTITY_TTL_SECONDS)
    return domain


def identity(symbol: str, domain: str = "", name: str = "") -> Optional[dict[str, Any]]:
    """Return a Logo.dev brand mark, or ``None`` when unconfigured."""
    if not domain and name:
        domain = resolve_domain(symbol, name)

    key = f"{symbol.upper()}|{domain}"
    cached = _identity_cache.get(key)
    if cached is not None:
        return cached
    mark = _logo.get_brand(symbol, domain)
    payload = mark.model_dump() if mark else None
    _identity_cache.put(key, payload, IDENTITY_TTL_SECONDS)
    return payload


def diagnostics() -> dict[str, Any]:
    """Configuration state without exposing either Logo.dev key."""
    return {
        "policy": "verified_identity_only",
        "logo_dev": {
            "configured": _logo.available,
            "secret_configured": bool(_logo.secret),
            "health_state": _logo.health_snapshot()["health_state"],
        },
        "cache": {"identity": _identity_cache.stats()},
    }
