"""One record per provider: what it is, what it can answer, what it has done.

`/api/providers/health` reports vendor snapshots nested by provider family and
`/api/providers/capabilities` reports who implements what; the providers page
used to join the two in the browser, with the vendors' display names kept in a
hand-written table there. This builds the joined view once, on the server,
from the three sources of truth:

  * the catalogue (`catalog.py`): who the vendor is and what its terms say
  * the capability registry, by introspection: what it can answer
  * every live adapter instance (`base.live_vendors`): what it has done

**Merging instances.** Several services hold their own instance of the same
vendor, each counting its own traffic. Counters are summed, timestamps take the
latest, recent calls are interleaved by time, and the state is the most severe
of the instances' — a vendor that one service saw fail is not reported healthy
because another service has not called it.

**What never leaves.** Credential values (only the variable's *name* and
whether it is set), URLs (stripped from error text even though credentials are
already redacted where errors are built), symbols and parameters (the recent
calls carry operation names only, so one reader cannot see what another is
researching).

**Counters are per process.** They start at zero when the server starts and are
not persisted; `process_started_at` says when that was, and the page says so.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import os
import pkgutil
import re
import time
from typing import Any, Iterable, Optional, Sequence

from src.providers import capabilities as capability_registry
from src.providers import catalog
from src.providers.base import (
    RECENT_EVENTS,
    VendorClient,
    disabled_vendors,
    health_window_seconds,
    live_vendors,
    redact,
)

PROCESS_STARTED_AT = time.time()

#: One never-called instance per catalogued adapter that no service has
#: created yet, made once and reused, so reading the view does not create
#: adapters on every request and the placeholders are never counted as
#: running instances.
_PLACEHOLDERS: dict[str, VendorClient] = {}

#: When instances disagree, the merged state is the highest-ranked one. Failure
#: outranks success, and evidence of answering outranks staleness and idleness.
STATE_RANK = {
    "DISABLED": 99, "NOT_CONFIGURED": 98, "DEV_ONLY": 97,
    "AUTH_FAILURE": 9, "COOLDOWN": 8, "UNAVAILABLE": 7, "TIMEOUT": 6,
    "RATE_LIMITED": 5, "NOT_ENTITLED": 4, "DEGRADED": 3,
    "HEALTHY": 2, "STALE": 1, "IDLE": 0,
}

_URL = re.compile(r"(?i)(\bfor url:?\s*)?https?://\S+")


@functools.lru_cache(maxsize=1)
def adapter_classes() -> dict[str, type]:
    """Every adapter class in `src.providers.vendors`, by NAME."""
    import src.providers.vendors as package

    found: dict[str, type] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, VendorClient) and cls is not VendorClient and cls.__module__ == module.__name__:
                found[cls.NAME] = cls
    return found


def safe_error(raw: Optional[str]) -> Optional[str]:
    """An error message fit to show: credentials redacted, URLs removed, short."""
    if not raw:
        return None
    text = _URL.sub("", redact(str(raw)))
    text = re.sub(r"\s{2,}", " ", text).strip(" :,-·")
    return text[:160] or None


def _advisories(name: str, info: Optional[catalog.ProviderInfo], available: bool) -> list[dict[str, str]]:
    """What an operator should act on. Configuration first, then licenses."""
    out: list[dict[str, str]] = []
    if name == "sec" and not os.getenv("SEC_USER_AGENT", "").strip():
        out.append({
            "kind": "configuration",
            "text": "SEC_USER_AGENT is not set, so EDGAR receives the generic project identifier. "
                    "SEC's access policy asks for a User-Agent naming a contact address.",
        })
    if info is None:
        out.append({
            "kind": "catalog",
            "text": "This adapter has no catalog entry, so its source and terms are not described.",
        })
    elif info.licence_review and available:
        out.append({"kind": "license", "text": info.notes or "Terms restrict this use; confirm the plan."})
    return out


def _merge(name: str, vendors: list[VendorClient]) -> dict[str, Any]:
    snaps = [v.health_snapshot(include_recent=True) for v in vendors]
    first = vendors[0]
    requests = sum(s["requests"] for s in snaps)
    failures = sum(s["failures"] for s in snaps)
    total_latency = sum((s.get("avg_latency_ms") or 0.0) * s["requests"] for s in snaps)
    state = max((s["health_state"] for s in snaps), key=lambda st: STATE_RANK.get(st, 5))
    latest_failure = max(snaps, key=lambda s: s.get("last_failure_at") or 0.0)
    recent = sorted(
        (event for s in snaps for event in s.get("recent", [])),
        key=lambda e: e["at"], reverse=True,
    )[:RECENT_EVENTS]
    successes = requests - failures
    return {
        "state": state,
        "requests": requests,
        "failures": failures,
        "success_pct": round(100.0 * successes / requests, 1) if requests else None,
        "avg_latency_ms": round(total_latency / requests, 1) if requests else None,
        "max_latency_ms": max((s.get("max_latency_ms") or 0.0) for s in snaps) if requests else None,
        "held_back_locally": sum(s.get("rate_limited") or 0 for s in snaps),
        "last_success_at": max((s.get("last_success_at") or 0.0) for s in snaps) or None,
        "last_failure_at": latest_failure.get("last_failure_at"),
        "last_attempt_at": max((s.get("last_attempt_at") or 0.0) for s in snaps) or None,
        "last_failure_class": latest_failure.get("last_failure_class"),
        "last_error": safe_error(latest_failure.get("last_error")),
        "cooling_down": any(s.get("cooling_down") for s in snaps),
        "cooldown_remaining_seconds": max(s.get("cooldown_remaining_seconds") or 0.0 for s in snaps),
        "restricted_operations": sorted({op for s in snaps for op in s.get("restricted_operations") or []}),
        "window": {
            "ok": sum(s["window"]["ok"] for s in snaps),
            "failed": sum(s["window"]["failed"] for s in snaps),
            "declined": sum(s["window"].get("declined", 0) for s in snaps),
        },
        "credential_state": first.credential_state,
        "recent": recent,
    }


def build(groups: dict[str, Sequence[Any]], extra: Iterable[Any] = ()) -> dict[str, Any]:
    """The providers view. `groups` maps a provider family to its vendors.

    Every live instance whose name is catalogued or appears in a group is
    included; an instance created by a test or a script under another name is
    not, so the view describes the product, not whatever else is in memory.
    """
    group_of: dict[str, set[str]] = {}
    for group, vendors in groups.items():
        for vendor in vendors:
            group_of.setdefault(getattr(vendor, "NAME", "unknown"), set()).add(group)

    by_name: dict[str, list[VendorClient]] = {}
    seen: set[int] = set()
    placeholder_ids = {id(v) for v in _PLACEHOLDERS.values()}
    for vendor in [*live_vendors(), *(v for vs in groups.values() for v in vs), *extra]:
        name = getattr(vendor, "NAME", None)
        if not name or id(vendor) in seen or id(vendor) in placeholder_ids:
            continue
        if not isinstance(vendor, VendorClient):
            continue
        if name not in catalog.CATALOG and name not in group_of:
            continue
        seen.add(id(vendor))
        by_name.setdefault(name, []).append(vendor)

    # A catalogued adapter with no instance yet (its service has not been
    # loaded in this process) is still a registered provider. It is described
    # from a fresh, never-called instance and reported with zero instances, so
    # it reads as idle or unconfigured rather than vanishing from the list.
    unloaded: set[str] = set()
    for name, cls in adapter_classes().items():
        if name in catalog.CATALOG and name not in by_name:
            if name not in _PLACEHOLDERS:
                _PLACEHOLDERS[name] = cls()
            by_name[name] = [_PLACEHOLDERS[name]]
            unloaded.add(name)

    window = health_window_seconds()
    providers: list[dict[str, Any]] = []
    for name, vendors in by_name.items():
        info = catalog.info(name)
        first = vendors[0]
        merged = _merge(name, vendors)
        recent = merged.pop("recent")
        credential_state = merged.pop("credential_state")
        caps = sorted({c for v in vendors for c in capability_registry.supported(v)})
        providers.append({
            "id": name,
            "display_name": info.display_name if info else name,
            "domain": info.domain if info else None,
            "source_kind": info.source_kind if info else None,
            "endpoint": info.endpoint if info else None,
            "catalogued": info is not None,
            "groups": sorted(group_of.get(name, set())),
            "capabilities": caps,
            "instances": 0 if name in unloaded else len(vendors),
            "configuration": {
                "credential_env": first.KEY_ENV,
                "keyless": first.KEY_ENV is None,
                "configured": first.configured,
                "disabled": first.disabled,
                "credential_state": credential_state,
                # Whether each optional setting is present. Never its value.
                "optional_env": [
                    {"name": env, "set": bool(os.getenv(env, "").strip())}
                    for env in (info.optional_env if info else ())
                ],
            },
            "policy": {
                "requests_per_minute": first.rate_limiter.capacity,
                "timeout_seconds": first.TIMEOUT_SECONDS,
                "max_retries": first.MAX_RETRIES,
                "cooldown_after_failures": first.COOLDOWN_AFTER_FAILURES,
                "cooldown_seconds": first.COOLDOWN_SECONDS,
            },
            "health": merged,
            "recent": recent,
            "terms": (
                {k: v for k, v in info.describe().items()
                 if k in ("terms_status", "terms_url", "notes", "attribution", "terms_checked_on")}
                if info else None
            ),
            "advisories": _advisories(name, info, first.available),
        })
    providers.sort(key=lambda p: p["display_name"].lower())

    eligible_by_name = {
        p["id"]: p for p in providers
        if p["configuration"]["configured"] and not p["configuration"]["disabled"]
        and p["health"]["state"] not in ("AUTH_FAILURE", "COOLDOWN")
    }
    capabilities = []
    for cap in capability_registry.describe():
        implemented = [p["id"] for p in providers if cap["name"] in p["capabilities"]]
        if not implemented:
            continue
        capabilities.append({
            "key": cap["name"],
            "label": cap["label"],
            "description": cap["description"],
            "reconciliation": cap["reconciliation"],
            "fanout_limit": cap["fanout_limit"],
            "implemented_by": implemented,
            # Could be asked right now: configured, not switched off, and not
            # benched for a rejected credential or repeated failures.
            "eligible": [n for n in implemented if n in eligible_by_name],
        })

    commit = os.getenv("GIT_COMMIT", "").strip()
    return {
        "generated_at": time.time(),
        "process_started_at": PROCESS_STARTED_AT,
        "health_window_seconds": window,
        # Adapters ship with the backend, so the build is their version.
        "adapter_version": commit[:12] or None,
        "disabled": sorted(disabled_vendors()),
        "providers": providers,
        "capabilities": capabilities,
    }
