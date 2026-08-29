"""
Local ingestion — clone in, the same immutable partitions out.

Writes through `RawStore` exactly as the HTTP path does, so downstream code
cannot tell which reader produced a partition, and the manifest records which
one did. `source_version` carries the resolved commit hash of the clone, which
is a stronger provenance claim than the HTTP path could make: `stocks@master`
names a branch that moves, while a commit hash names bytes.

## What this path adds

| Dataset | Over HTTP | Locally |
|---|---|---|
| `stocks.dividend` | **failed** — a 60-symbol batch exceeded the 1,000-row cap | 494,438 rows, one query |
| `options.option_chain` | infeasible — 116M rows | aggregated per (date, symbol) server-side |
| `earnings.*` | 7M estimate vintages behind a 1,000-row cap | one query per year |

The dividend failure is worth restating because it is the design working: the
HTTP client raised `RowLimitExceeded` rather than returning a truncated answer.
A silently short dividend table would have produced total returns that were
wrong for exactly the names that pay the most.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from src.quant.datasets.catalog import DatasetSpec
from src.quant.datasets.ingest import IngestionReport, normalise_rows
from src.quant.datasets.local_dolt import LocalDoltClient
from src.quant.datasets.store import DatasetManifest, RawStore

logger = logging.getLogger("omnisignal.quant.datasets.local_ingest")


def repository_commit(client: LocalDoltClient, repository: str) -> str:
    """The clone's resolved HEAD.

    A commit hash rather than a branch name: `master` moves, and a manifest
    that records a moving reference cannot support the claim that a dataset is
    reproducible from it.
    """
    try:
        path = client.require(repository)
        out = subprocess.run(
            [client.binary, "sql", "-q", "select hashof('HEAD') as `commit`", "-r", "csv"],
            cwd=path, capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            lines = [line for line in out.stdout.strip().splitlines() if line]
            if len(lines) >= 2:
                return f"{repository}@{lines[1].strip()}"
    except (OSError, subprocess.SubprocessError, Exception):  # noqa: BLE001
        pass
    return f"{repository}@unknown"


def _publish(
    store: RawStore,
    spec: DatasetSpec,
    partitions: list[Any],
    columns: list[str],
    *,
    source_version: str,
    extra_transformations: Optional[Sequence[str]] = None,
    extra_notes: Optional[Sequence[str]] = None,
) -> None:
    store.write_manifest(
        DatasetManifest(
            dataset_id=spec.dataset_id,
            source="dolthub_local_clone",
            repository=spec.repository,
            table=spec.table,
            source_version=source_version,
            columns=columns,
            partitions=list(partitions),
            point_in_time_status=spec.point_in_time.value,
            point_in_time_note=spec.point_in_time_note,
            survivorship_status=spec.survivorship.value,
            survivorship_note=spec.survivorship_note,
            licence=spec.licence,
            transformations=[
                "read from a local Dolt clone via `dolt sql -r csv`",
                "renamed act_symbol->symbol, ex_date/last_seen->date",
                "typed at the boundary; unparseable values -> NULL, never 0",
                *(extra_transformations or []),
            ],
            notes=[*spec.limitations, *(extra_notes or [])],
        )
    )


def ingest_whole_table_local(
    spec: DatasetSpec,
    store: RawStore,
    *,
    client: Optional[LocalDoltClient] = None,
    resume: bool = True,
    where: str = "",
) -> IngestionReport:
    """Read a table in full from the clone. No row cap applies."""
    client = client or LocalDoltClient()
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()

    if resume and store.has_partition(spec.dataset_id, "all"):
        report.partitions_skipped.append("all")
        report.elapsed_seconds = time.perf_counter() - began
        return report

    projection = ", ".join(f"`{name}`" for name in spec.columns)
    clause = f" where {where}" if where else ""
    frame = client.query(spec.repository, f"select {projection} from `{spec.table}`{clause}")
    if frame.empty:
        report.elapsed_seconds = time.perf_counter() - began
        return report

    frame = normalise_rows(spec, frame.to_dict(orient="records"))
    record = store.write_partition(spec.dataset_id, "all", frame, overwrite=not resume)
    _publish(
        store, spec, [record], list(frame.columns),
        source_version=repository_commit(client, spec.repository),
    )
    report.partitions_written.append("all")
    report.rows = record.rows
    report.elapsed_seconds = time.perf_counter() - began
    logger.info("local ingest %s: %d rows in %.1fs", spec.dataset_id, record.rows, report.elapsed_seconds)
    return report


def ingest_by_year_local(
    spec: DatasetSpec,
    store: RawStore,
    *,
    start_year: int,
    end_year: int,
    client: Optional[LocalDoltClient] = None,
    symbols: Optional[Sequence[str]] = None,
    resume: bool = True,
    date_column: Optional[str] = None,
    where: str = "",
) -> IngestionReport:
    """Read a large table one year at a time, writing a partition per year.

    Peak memory is one year, not the table. A symbol restriction is pushed into
    the query rather than filtered afterwards — on a 28.9M-row table the
    difference is the whole point.
    """
    client = client or LocalDoltClient()
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()
    date_column = date_column or spec.date_column

    existing = set()
    partitions: list[Any] = []
    if resume:
        try:
            manifest = store.manifest(spec.dataset_id)
            existing = manifest.partition_keys()
            partitions = list(manifest.partitions)
        except Exception:  # noqa: BLE001 — first run
            pass

    clauses = [where] if where else []
    if symbols:
        cleaned = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
        listed = ",".join(f"'{s}'" for s in cleaned)
        clauses.append(f"`{spec.symbol_column or 'act_symbol'}` in ({listed})")
    predicate = " and ".join(f"({c})" for c in clauses)

    for year in range(start_year, end_year + 1):
        key = str(year)
        if key in existing:
            report.partitions_skipped.append(key)
            continue

        projection = ", ".join(f"`{name}`" for name in spec.columns)
        window = (
            f"`{date_column}` >= '{year}-01-01' and `{date_column}` <= '{year}-12-31'"
        )
        full = f"{window} and {predicate}" if predicate else window
        frame = client.query(
            spec.repository, f"select {projection} from `{spec.table}` where {full}"
        )
        if frame.empty:
            continue

        frame = normalise_rows(spec, frame.to_dict(orient="records"))
        record = store.write_partition(spec.dataset_id, key, frame)
        partitions.append(record)
        report.partitions_written.append(key)
        report.rows += record.rows
        _publish(
            store, spec, partitions, list(frame.columns),
            source_version=repository_commit(client, spec.repository),
        )
        logger.info(
            "local ingest %s %s: %d rows, %d symbols",
            spec.dataset_id, key, record.rows, record.symbols or 0,
        )

    if partitions:
        _publish(
            store, spec, partitions, list(spec.columns),
            source_version=repository_commit(client, spec.repository),
        )
    report.elapsed_seconds = time.perf_counter() - began
    return report


def ingest_aggregated_local(
    spec: DatasetSpec,
    store: RawStore,
    *,
    sql_template: str,
    start_year: int,
    end_year: int,
    client: Optional[LocalDoltClient] = None,
    resume: bool = True,
    transformations: Optional[Sequence[str]] = None,
    notes: Optional[Sequence[str]] = None,
) -> IngestionReport:
    """Aggregate a very large table inside Dolt, storing only the result.

    The path that makes `option_chain` usable. 116M rows never cross the process
    boundary: the per-(date, symbol) aggregate is computed by the engine and
    only the aggregate is materialised. `sql_template` is formatted with `year`.
    """
    client = client or LocalDoltClient()
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()

    existing = set()
    partitions: list[Any] = []
    if resume:
        try:
            manifest = store.manifest(spec.dataset_id)
            existing = manifest.partition_keys()
            partitions = list(manifest.partitions)
        except Exception:  # noqa: BLE001
            pass

    for year in range(start_year, end_year + 1):
        key = str(year)
        if key in existing:
            report.partitions_skipped.append(key)
            continue

        frame = client.query(spec.repository, sql_template.format(year=year))
        if frame.empty:
            logger.info("local ingest %s %s: no rows", spec.dataset_id, key)
            continue

        if "act_symbol" in frame.columns:
            frame = frame.rename(columns={"act_symbol": "symbol"})
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        if "symbol" in frame.columns:
            frame["symbol"] = frame["symbol"].astype("string").str.upper()

        record = store.write_partition(spec.dataset_id, key, frame)
        partitions.append(record)
        report.partitions_written.append(key)
        report.rows += record.rows
        _publish(
            store, spec, partitions, list(frame.columns),
            source_version=repository_commit(client, spec.repository),
            extra_transformations=transformations, extra_notes=notes,
        )
        logger.info(
            "local ingest %s %s: %d aggregated rows (%.1fs elapsed)",
            spec.dataset_id, key, record.rows, time.perf_counter() - began,
        )

    if partitions:
        _publish(
            store, spec, partitions,
            list(partitions[0].as_dict().keys()) if partitions else list(spec.columns),
            source_version=repository_commit(client, spec.repository),
            extra_transformations=transformations, extra_notes=notes,
        )
    report.elapsed_seconds = time.perf_counter() - began
    return report
