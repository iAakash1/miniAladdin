"""Deterministic reconciliation of comparable evidence.

Reconciliation never votes and never averages. It groups only measurements
whose field, unit, currency and period basis are comparable, preserves every
reported value, and states whether independent sources agree. A conflict is a
first-class output for the research case, not a nuisance to smooth away.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

from src.agents.schemas import (
    EvidenceRecord,
    Period,
    ReconciledDimension,
    ReconciliationReport,
    ReconciliationStatus,
)
from src.agents.validation_agent import independent_sources


def _comparable_key(record: EvidenceRecord) -> tuple[str, str, str, str, str, str]:
    period = record.period or Period()
    return (
        record.field,
        record.unit or "",
        record.currency or "",
        period.basis or "",
        period.start or "",
        period.end or "",
    )


def _stable_value(value: Any) -> str:
    """Comparable representation that also handles dict/list provider values."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        return repr(value)


def reconcile(
    evidence: Iterable[EvidenceRecord],
    *,
    claims: int = 0,
    agents_ok: Iterable[str] = (),
    agents_degraded: Iterable[str] = (),
    missing_inputs: Iterable[str] = (),
) -> ReconciliationReport:
    records = list(evidence)
    grouped: dict[tuple[str, str, str, str, str, str], list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        grouped[_comparable_key(record)].append(record)

    dimensions: list[ReconciledDimension] = []
    counts = {status.value.lower(): 0 for status in ReconciliationStatus}

    for raw_key, rows in sorted(grouped.items()):
        field, unit, currency, basis, start, end = raw_key
        providers = sorted({row.provider for row in rows if row.provider})
        source_count = independent_sources(providers)
        present = [row for row in rows if row.value is not None and row.quality != "unavailable"]
        stale = [row for row in present if row.stale or row.quality == "stale"]
        distinct = {_stable_value(row.value) for row in present}

        if not present:
            status = ReconciliationStatus.UNAVAILABLE
            reason = "no source returned a usable value"
        elif len(stale) == len(present):
            status = ReconciliationStatus.STALE
            reason = "all available values are stale"
        elif len(distinct) > 1:
            status = ReconciliationStatus.CONFLICTED
            reason = "comparable sources report different values"
        elif source_count < 2:
            status = ReconciliationStatus.SINGLE_SOURCE
            reason = "fewer than two independent sources support this value"
        else:
            status = ReconciliationStatus.AGREED
            reason = "two or more independent sources report the same value"

        counts[status.value.lower()] += 1
        key = "|".join(raw_key)
        dimensions.append(ReconciledDimension(
            key=key,
            field=field,
            unit=unit or None,
            currency=currency or None,
            period=Period(basis=basis or "instant", start=start or None, end=end or None),
            status=status,
            evidence_ids=[row.evidence_id for row in rows],
            providers=providers,
            independent_sources=source_count,
            values=[row.value for row in rows],
            reason=reason,
        ))

    providers = sorted({record.provider for record in records if record.provider})
    return ReconciliationReport(
        claims=claims,
        evidence=len(records),
        providers=len(providers),
        independent_sources=independent_sources(providers),
        agents_ok=list(agents_ok),
        agents_degraded=list(agents_degraded),
        missing_inputs=sorted(set(missing_inputs)),
        dimensions=dimensions,
        **counts,
    )
