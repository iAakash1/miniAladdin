"""Canonical, honest health for the research operating system.

This is deliberately distinct from ``/api/health``. The old route is a fast
liveness probe: if the process can answer, it says ``ok``. This module answers
the harder question a researcher asks: which layers are ready, degraded,
blocked, unavailable, or not configured, and what fact caused that state?

No secret values are returned and no unavailable dependency is converted into
a healthy boolean.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class HealthState(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ComponentHealth(BaseModel):
    component: str
    status: HealthState
    critical: bool = False
    reason: str
    version: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class SystemHealth(BaseModel):
    status: HealthState
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    components: list[ComponentHealth]
    summary: dict[str, int]
    process_memory: dict[str, Any] = Field(default_factory=dict)
    provider_concurrency: dict[str, int] = Field(default_factory=dict)


def overall_state(components: Iterable[ComponentHealth]) -> HealthState:
    """Worst relevant state, with critical research blocks kept visible."""
    rows = list(components)
    if any(row.critical and row.status is HealthState.UNAVAILABLE for row in rows):
        return HealthState.UNAVAILABLE
    if any(row.critical and row.status is HealthState.BLOCKED for row in rows):
        return HealthState.BLOCKED
    if any(row.status is not HealthState.READY for row in rows):
        return HealthState.DEGRADED
    return HealthState.READY


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _provider_component(name: str, rows: list[dict[str, Any]], *, critical: bool) -> ComponentHealth:
    configured = [row for row in rows if row.get("configured")]
    if not configured:
        return ComponentHealth(
            component=f"providers.{name}", status=HealthState.NOT_CONFIGURED,
            critical=critical, reason="no provider in this capability is configured",
            detail={"configured": 0, "known": len(rows)},
        )
    failing = [
        row for row in configured
        if row.get("cooling_down") or row.get("consecutive_failures", 0) > 0
    ]
    status = HealthState.DEGRADED if failing else HealthState.READY
    reason = (
        f"{len(failing)} configured provider(s) report failures or cooldown"
        if failing else "configured with no observed runtime failure"
    )
    return ComponentHealth(
        component=f"providers.{name}", status=status, critical=critical,
        reason=reason,
        detail={
            "configured": len(configured), "known": len(rows),
            "degraded": [row.get("vendor") for row in failing],
            "reachability": "observed requests only",
        },
    )


def build_health(
    *,
    build_commit: str,
    persistence_configured: bool,
    persistence_reachable: bool,
    auth_configured: bool,
    provider_health: dict[str, Any],
    quant_status: dict[str, Any],
    inference_configured: bool,
    inference_health: dict[str, Any],
    langgraph_available: bool,
    project_root: Path = PROJECT_ROOT,
    process_memory: dict[str, Any] | None = None,
    provider_concurrency: dict[str, int] | None = None,
) -> SystemHealth:
    """Assemble the report from explicit inputs so classification is testable."""
    components: list[ComponentHealth] = [
        ComponentHealth(
            component="api", status=HealthState.READY, critical=True,
            reason="the API process answered this check", version=build_commit,
        ),
        ComponentHealth(
            component="persistence",
            status=(HealthState.READY if persistence_reachable else
                    HealthState.DEGRADED if persistence_configured else HealthState.NOT_CONFIGURED),
            reason=("client initialised; no network probe performed" if persistence_reachable else
                    "configured but not yet initialised; no network probe performed" if persistence_configured else
                    "Supabase persistence is not configured"),
        ),
        ComponentHealth(
            component="authentication",
            status=HealthState.READY if auth_configured else HealthState.NOT_CONFIGURED,
            reason="Clerk is configured" if auth_configured else "Clerk is not configured",
        ),
        ComponentHealth(
            component="agent_graph",
            status=HealthState.READY if langgraph_available else HealthState.UNAVAILABLE,
            critical=True,
            reason=("LangGraph runtime is importable" if langgraph_available else
                    "LangGraph is unavailable; analysis runs are refused"),
        ),
    ]

    domains = provider_health.get("providers", {})
    components.extend([
        _provider_component("market", domains.get("market_data", []), critical=True),
        _provider_component("fundamentals", domains.get("fundamentals", []), critical=False),
        _provider_component("news", domains.get("news", []), critical=False),
        _provider_component("macro", domains.get("macro", []), critical=False),
        _provider_component("filings", domains.get("filings", []), critical=False),
    ])

    deployment = str(quant_status.get("deployment_status", "UNKNOWN"))
    registry_available = bool(quant_status.get("registry_available"))
    if not registry_available:
        registry_state = HealthState.UNAVAILABLE
    elif deployment == "PRODUCTION":
        registry_state = HealthState.READY
    else:
        registry_state = HealthState.BLOCKED
    components.append(ComponentHealth(
        component="research_registry", status=registry_state, critical=True,
        reason=str(quant_status.get("message") or f"model registry reports {deployment}"),
        detail={
            "deployment_status": deployment,
            "production": quant_status.get("production"),
            "candidates": quant_status.get("candidates"),
            "total_entries": quant_status.get("total_entries"),
            "serving_predictions": bool(quant_status.get("serving_predictions")),
        },
    ))

    validation = _read_json(project_root / "data/manifests/pit_validation_v4.json")
    rich = _read_json(project_root / "data/manifests/rich_pit_v2_manifest.json")
    if validation is None or rich is None:
        data_state, data_reason = HealthState.UNAVAILABLE, "one or more PIT manifests are unreadable"
    elif validation.get("status") == "PASS":
        data_state, data_reason = HealthState.READY, "all admitted PIT validation checks pass"
    else:
        data_state, data_reason = HealthState.DEGRADED, (
            f"PIT validation is {validation.get('status', 'UNKNOWN')}; blocked and partial checks remain explicit"
        )
    components.append(ComponentHealth(
        component="data_registry", status=data_state, critical=True, reason=data_reason,
        version=rich.get("dataset_id") if rich else None,
        detail={
            "validation_status": validation.get("status") if validation else None,
            "feature_count": rich.get("feature_count") if rich else None,
            "content_hash": rich.get("content_hash") if rich else None,
            "holdout_touched": (rich.get("holdout") or {}).get("touched") if rich else None,
        },
    ))

    components.append(ComponentHealth(
        component="final_holdout", status=HealthState.BLOCKED, critical=True,
        reason="sealed and not ready: EXP-011 revenue mapping requires a formal replication decision",
        detail={"touched": False, "next_experiment_started": False},
    ))

    remote_status = str(inference_health.get("status", "unavailable")).lower()
    if not inference_configured:
        inference_state = HealthState.NOT_CONFIGURED
    elif remote_status == "ok":
        inference_state = HealthState.READY
    elif remote_status == "waking":
        inference_state = HealthState.DEGRADED
    else:
        inference_state = HealthState.UNAVAILABLE
    components.append(ComponentHealth(
        component="quant_inference", status=inference_state,
        reason=str(inference_health.get("detail") or inference_health.get("error") or remote_status),
        detail={"configured": inference_configured, "promotion_status": inference_health.get("promotion_status")},
    ))

    summary = {state.value: 0 for state in HealthState}
    for component in components:
        summary[component.status.value] += 1
    return SystemHealth(
        status=overall_state(components), components=components, summary=summary,
        process_memory=process_memory or {},
        provider_concurrency=provider_concurrency or {},
    )


def snapshot(*, build_commit: str) -> SystemHealth:
    """Read current local/runtime state. Network checks stay bounded upstream."""
    from src import providers
    from src.agents import graph
    from src.providers.parallel import concurrency_snapshot
    from src.services import clerk_auth, database, inference_client, memory_diagnostics, quant_service

    configured = database.is_configured()
    return build_health(
        build_commit=build_commit,
        persistence_configured=configured,
        persistence_reachable=database.client_is_initialized() if configured else False,
        auth_configured=clerk_auth.is_configured(),
        provider_health=providers.providers_health(),
        quant_status=quant_service.production_status(),
        inference_configured=inference_client.configured(),
        inference_health=inference_client.observed_health(),
        langgraph_available=graph.available(),
        process_memory=memory_diagnostics.snapshot().as_dict(),
        provider_concurrency=concurrency_snapshot(),
    )
