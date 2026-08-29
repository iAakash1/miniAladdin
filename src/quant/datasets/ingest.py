"""
Ingestion — catalog specs in, immutable partitioned Parquet out.

## The three properties that make a backfill usable

**Resumable.** A 15-year backfill is thousands of network round trips and will
be interrupted. Partitions are written whole and skipped when present, so a
resumed run costs only the work that did not land. Nothing is ever
half-written: `RawStore.write_partition` stages and renames.

**Bounded.** Fan-out is capped and every worker shares one client, so the
source sees a steady, polite request rate rather than a burst. The measured
single-request cost is ~1.0 s for a date restricted to a 50-symbol universe,
so 12 workers is ~12 dates/s and a 15-year backfill is minutes rather than
the ~1.6 h the CSV export path was measured at.

**Honest about gaps.** A date that returns no rows is recorded as a
non-trading date, not retried forever and not silently dropped. The trading
calendar is therefore *discovered from the data* — which is the only calendar
that can be right, because a hardcoded holiday table is wrong the first time
an exchange closes unexpectedly.

A date that *errored* is a different thing entirely and is never confused with
one that returned nothing. Errored dates are retried once at the end of the
year's pass; any that still fail are written into the partition's manifest
under `failed_dates`, and `MAX_FAILED_DATE_FRACTION` caps how many a partition
may carry before the write is refused outright. Without that cap a rate-limited
run produces a year of prices with a scatter of missing sessions that looks
exactly like a complete year — and every return spanning a hole is wrong by the
size of the gap.

## Why the trading calendar is discovered rather than queried

`select date from ohlcv group by date` times out: the deployed engine will not
aggregate 39 million rows inside the request deadline. Single-date equality
predicates are the only shape it answers quickly (see `dolthub.py`). So the
ingestion enumerates candidate weekdays locally and lets the source say which
of them traded. Roughly 4% of requests land on holidays and return empty; that
is the measured cost of not inventing a calendar.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import timedelta
from typing import Any, Callable, Optional, Sequence

import pandas as pd

from src.quant.datasets.catalog import DatasetSpec, IngestionMode
from src.quant.datasets.dolthub import DEFAULT_BRANCH, DoltHubClient
from src.quant.datasets.store import DatasetManifest, RawStore

logger = logging.getLogger("omnisignal.quant.datasets.ingest")

#: Concurrent single-date requests. Measured: one date restricted to a
#: 50-symbol universe answers in ~1.0 s, and the source is a shared public
#: service. 12 keeps a 15-year backfill to minutes without behaving like a
#: scraper.
DEFAULT_WORKERS = 12

#: Maximum symbols in one ``IN`` list. Measured against the live endpoint:
#: IN(600) answers in ~1.05 s, IN(1000) closes the connection — the composed
#: URL is ~7 KB and something in the path refuses it. 500 leaves headroom, and
#: a universe larger than that simply costs proportionally more requests per
#: date rather than failing.
SYMBOL_CHUNK = 500

#: The largest fraction of a year's sessions that may be missing due to errors
#: before the partition is refused. 2% is roughly five sessions in a year: few
#: enough that a return computed across one is a rounding issue, and any more
#: means the ingestion was degraded and the data should be refetched rather
#: than reasoned about.
MAX_FAILED_DATE_FRACTION = 0.02

#: Partition granularity. A year of a 50-name universe is ~12,500 rows and
#: ~150 KB compressed — small enough that a corrupt partition is cheap to
#: refetch, large enough that a 15-year dataset is 16 files rather than 4,000.
PARTITION_BY_YEAR = "year"


@dataclass
class IngestionReport:
    """What an ingestion actually did. Reported, never estimated."""

    dataset_id: str
    partitions_written: list[str] = field(default_factory=list)
    partitions_skipped: list[str] = field(default_factory=list)
    rows: int = 0
    dates_requested: int = 0
    dates_with_data: int = 0
    dates_empty: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    client_stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "partitions_written": list(self.partitions_written),
            "partitions_skipped": list(self.partitions_skipped),
            "rows": self.rows,
            "dates_requested": self.dates_requested,
            "dates_with_data": self.dates_with_data,
            "dates_empty": self.dates_empty,
            "failures": list(self.failures),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "rows_per_second": (
                round(self.rows / self.elapsed_seconds, 1) if self.elapsed_seconds else None
            ),
            "client_stats": dict(self.client_stats),
        }


ProgressFn = Callable[[str, int, int], None]


def ingest_date_partitioned(
    spec: DatasetSpec,
    store: RawStore,
    *,
    start: Date,
    end: Date,
    symbols: Optional[Sequence[str]] = None,
    client: Optional[DoltHubClient] = None,
    workers: int = DEFAULT_WORKERS,
    branch: str = DEFAULT_BRANCH,
    on_progress: Optional[ProgressFn] = None,
    resume: bool = True,
    dates: Optional[Sequence[Date]] = None,
) -> IngestionReport:
    """Fetch a date-keyed table one date at a time, writing yearly partitions.

    `symbols=None` means the whole market and forces the paginated path, which
    is ~12 requests per date instead of one. That is the right trade only for
    universe discovery; every research ingestion passes a symbol list.
    """
    client = client or DoltHubClient()
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()

    years = sorted({year for year in range(start.year, end.year + 1)})
    existing = _existing_partitions(store, spec.dataset_id) if resume else set()

    partitions: list[Any] = []
    partition_gaps: dict[str, list[str]] = {}
    for year in years:
        key = str(year)
        window_start = max(start, Date(year, 1, 1))
        window_end = min(end, Date(year, 12, 31))
        if key in existing:
            report.partitions_skipped.append(key)
            record = _existing_record(store, spec.dataset_id, key)
            if record is not None:
                partitions.append(record)
                report.rows += record.rows
            continue

        frame, counters = _fetch_year(
            spec, client, window_start, window_end, symbols, workers, branch,
            report, on_progress, dates,
        )
        report.dates_requested += counters["requested"]
        report.dates_with_data += counters["with_data"]
        report.dates_empty += counters["empty"]

        # Second pass over dates that ERRORED. An empty date is a holiday; an
        # errored date is a hole, and the two must never be conflated.
        failed_dates = [item["date"] for item in counters.get("failed", [])]
        if failed_dates:
            logger.info(
                "ingest %s %s: retrying %d errored date(s)",
                spec.dataset_id, key, len(failed_dates),
            )
            retry_frame, retry_counters = _fetch_year(
                spec, client, window_start, window_end, symbols,
                max(1, workers // 3), branch, report, on_progress,
                [Date.fromisoformat(day) for day in failed_dates],
            )
            if not retry_frame.empty:
                frame = pd.concat([frame, retry_frame], ignore_index=True)
            failed_dates = [item["date"] for item in retry_counters.get("failed", [])]

        if failed_dates:
            attempted = max(1, counters["requested"])
            share = len(failed_dates) / attempted
            if share > MAX_FAILED_DATE_FRACTION:
                report.failures.append(
                    {
                        "partition": key,
                        "error": (
                            f"{len(failed_dates)}/{attempted} dates ({share:.1%}) still failing "
                            f"after retry — above the {MAX_FAILED_DATE_FRACTION:.0%} ceiling. "
                            "Partition NOT written; rerun to resume."
                        ),
                    }
                )
                logger.error(
                    "ingest %s %s: REFUSING to write — %d/%d dates unresolved (%.1f%%)",
                    spec.dataset_id, key, len(failed_dates), attempted, share * 100,
                )
                continue
            logger.warning(
                "ingest %s %s: %d date(s) unresolved, recorded in the manifest",
                spec.dataset_id, key, len(failed_dates),
            )

        if frame.empty:
            logger.info("ingest %s %s: no rows", spec.dataset_id, key)
            continue

        record = store.write_partition(
            spec.dataset_id,
            key,
            frame,
            date_column="date",
            symbol_column="symbol",
        )
        if failed_dates:
            partition_gaps[key] = sorted(failed_dates)
        partitions.append(record)
        report.partitions_written.append(key)
        report.rows += record.rows
        _publish_manifest(store, spec, partitions, list(frame.columns), gaps=partition_gaps)
        logger.info(
            "ingest %s %s: %d rows, %d symbols",
            spec.dataset_id, key, record.rows, record.symbols or 0,
        )

    _publish_manifest(store, spec, partitions, list(spec.columns), gaps=partition_gaps)
    report.elapsed_seconds = time.perf_counter() - began
    report.client_stats = client.stats.as_dict()
    return report


def _fetch_year(
    spec: DatasetSpec,
    client: DoltHubClient,
    start: Date,
    end: Date,
    symbols: Optional[Sequence[str]],
    workers: int,
    branch: str,
    report: IngestionReport,
    on_progress: Optional[ProgressFn],
    dates: Optional[Sequence[Date]] = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fan out over the candidate trading dates in one year."""
    candidates = (
        [day for day in dates if start <= day <= end]
        if dates is not None
        else _candidate_sessions(start, end)
    )
    counters: dict[str, Any] = {
        "requested": len(candidates), "with_data": 0, "empty": 0, "failed": [],
    }
    collected: list[dict[str, Any]] = []

    def fetch(trade_date: Date) -> tuple[Date, list[dict[str, Any]]]:
        iso = trade_date.isoformat()
        if symbols is None:
            rows = client.rows_for_date_paginated(
                spec.repository, spec.table, iso,
                columns=list(spec.columns), date_column=spec.date_column, branch=branch,
            )
        else:
            # Chunked because the endpoint refuses an IN-list past roughly 700
            # names (SYMBOL_CHUNK). Chunks are concatenated, never sampled: a
            # universe larger than one request costs more requests, not fewer
            # symbols.
            rows = []
            for offset in range(0, len(symbols), SYMBOL_CHUNK):
                rows.extend(
                    client.rows_for_date(
                        spec.repository, spec.table, iso,
                        symbols=symbols[offset:offset + SYMBOL_CHUNK],
                        columns=list(spec.columns),
                        symbol_column=spec.symbol_column or "act_symbol",
                        date_column=spec.date_column, branch=branch,
                    )
                )
        return trade_date, rows

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, day): day for day in candidates}
        done = 0
        for future in as_completed(futures):
            day = futures[future]
            done += 1
            try:
                _, rows = future.result()
            except Exception as error:  # noqa: BLE001 — recorded, retried, never dropped
                entry = {"date": day.isoformat(), "error": str(error)[:300]}
                counters["failed"].append(entry)
                report.failures.append({"dataset": spec.dataset_id, **entry})
                logger.warning("ingest %s %s failed: %s", spec.dataset_id, day, error)
                continue
            if rows:
                counters["with_data"] += 1
                collected.extend(rows)
            else:
                counters["empty"] += 1
            if on_progress is not None and done % 25 == 0:
                on_progress(f"{spec.dataset_id}:{start.year}", done, len(candidates))

    if not collected:
        return pd.DataFrame(), counters
    return normalise_rows(spec, collected), counters


def ingest_by_symbol(
    spec: DatasetSpec,
    store: RawStore,
    symbols: Sequence[str],
    *,
    client: Optional[DoltHubClient] = None,
    branch: str = DEFAULT_BRANCH,
    workers: int = DEFAULT_WORKERS,
    batch: int = 60,
    resume: bool = True,
) -> IngestionReport:
    """Fetch a symbol-keyed table for a bounded universe.

    `stocks.dividend` is 494,438 rows — too many to page whole, and its primary
    key is `(act_symbol, ex_date)`, so a symbol predicate is an index seek
    rather than a scan. Batches are small (60) because each symbol contributes
    its entire dividend history: AAPL alone has 92 rows going back to 1987, so
    a large batch risks silently hitting the 1,000-row cap. `execute` raises on
    truncation, so hitting it fails loudly — but the batch size is chosen so it
    does not happen at all.
    """
    client = client or DoltHubClient()
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()

    if resume and store.has_partition(spec.dataset_id, "all"):
        report.partitions_skipped.append("all")
        record = _existing_record(store, spec.dataset_id, "all")
        if record is not None:
            report.rows = record.rows
        report.elapsed_seconds = time.perf_counter() - began
        report.client_stats = client.stats.as_dict()
        return report

    cleaned = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    batches = [cleaned[i:i + batch] for i in range(0, len(cleaned), batch)]
    collected: list[dict[str, Any]] = []

    def fetch(group: list[str]) -> list[dict[str, Any]]:
        projection = ", ".join(f"`{name}`" for name in spec.columns)
        column = spec.symbol_column or "act_symbol"
        listed = ",".join(f"'{name}'" for name in group)
        query = f"select {projection} from `{spec.table}` where `{column}` in ({listed})"
        return client.execute(spec.repository, query, branch=branch).rows

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, group): group for group in batches}
        for future in as_completed(futures):
            group = futures[future]
            try:
                collected.extend(future.result())
            except Exception as error:  # noqa: BLE001 — one batch never fails the run
                report.failures.append(
                    {"symbols": ",".join(group[:5]) + "...", "error": str(error)[:300]}
                )
                logger.warning("ingest %s batch failed: %s", spec.dataset_id, error)

    if collected:
        frame = normalise_rows(spec, collected)
        record = store.write_partition(
            spec.dataset_id, "all", frame, date_column="date", symbol_column="symbol"
        )
        report.partitions_written.append("all")
        report.rows = record.rows
        _publish_manifest(store, spec, [record], list(frame.columns))

    report.elapsed_seconds = time.perf_counter() - began
    report.client_stats = client.stats.as_dict()
    return report


def ingest_whole_table(
    spec: DatasetSpec,
    store: RawStore,
    *,
    client: Optional[DoltHubClient] = None,
    branch: str = DEFAULT_BRANCH,
    resume: bool = True,
) -> IngestionReport:
    """Page a small table into a single partition.

    Only for tables measured small — `rates.us_treasury` is 9,158 rows and
    `stocks.symbol` is 24,058. `DoltHubClient.whole_table` bounds the page
    count so a mistaken call against `ohlcv` fails loudly.
    """
    client = client or DoltHubClient()
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()

    if resume and store.has_partition(spec.dataset_id, "all"):
        report.partitions_skipped.append("all")
        record = _existing_record(store, spec.dataset_id, "all")
        if record is not None:
            report.rows = record.rows
        report.elapsed_seconds = time.perf_counter() - began
        report.client_stats = client.stats.as_dict()
        return report

    rows = client.whole_table(
        spec.repository, spec.table,
        columns=list(spec.columns), key=spec.primary_key, branch=branch,
    )
    if rows:
        frame = normalise_rows(spec, rows)
        record = store.write_partition(
            spec.dataset_id, "all", frame, date_column="date", symbol_column="symbol"
        )
        report.partitions_written.append("all")
        report.rows = record.rows
        _publish_manifest(store, spec, [record], list(frame.columns))

    report.elapsed_seconds = time.perf_counter() - began
    report.client_stats = client.stats.as_dict()
    return report


# ── normalisation ────────────────────────────────────────────────────────────

#: Source column -> canonical column. Applied at the ingestion boundary for
#: the same reason `src/providers` normalises vendor payloads there: a
#: reconciler that compares `act_symbol` with `symbol` compares nothing.
_RENAMES: dict[str, str] = {
    "act_symbol": "symbol",
    "ex_date": "date",
    "last_seen": "date",
}

_NUMERIC_HINTS: tuple[str, ...] = (
    "open", "high", "low", "close", "volume", "amount", "to_factor", "for_factor",
    "consensus", "recent", "count", "high", "low", "year_ago",
    "hv_current", "hv_week_ago", "hv_month_ago", "hv_year_high", "hv_year_low",
    "iv_current", "iv_week_ago", "iv_month_ago", "iv_year_high", "iv_year_low",
    "strike", "bid", "ask", "vol", "delta", "gamma", "theta", "vega", "rho",
    "1_month", "2_month", "3_month", "6_month", "1_year", "2_year", "3_year",
    "5_year", "7_year", "10_year", "20_year", "30_year",
    "is_etf", "is_test_issue", "round_lot_size",
)


def normalise_rows(spec: DatasetSpec, rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Rename to canonical columns and type the values exactly once.

    The API returns every value as a string — including `decimal(14,4)` prices
    and `bigint` volumes. Converting here rather than at each read means one
    place to be wrong, and `errors="coerce"` means an unparseable value becomes
    NULL rather than silently becoming zero. Zero is a price; NULL is the
    absence of one.
    """
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    renames = {source: target for source, target in _RENAMES.items() if source in frame.columns}
    # `symbol.last_seen` renames to `date`, but only when no `date` already
    # exists — otherwise the collision would silently drop one of them.
    if "date" in frame.columns:
        renames.pop("last_seen", None)
        renames.pop("ex_date", None)
    frame = frame.rename(columns=renames)

    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    if "period_end_date" in frame.columns:
        frame["period_end_date"] = pd.to_datetime(
            frame["period_end_date"], errors="coerce"
        ).dt.date
    if "expiration" in frame.columns:
        frame["expiration"] = pd.to_datetime(frame["expiration"], errors="coerce").dt.date

    for column in frame.columns:
        if column in _NUMERIC_HINTS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "symbol" in frame.columns:
        frame["symbol"] = frame["symbol"].astype("string").str.upper()

    return frame


# ── helpers ──────────────────────────────────────────────────────────────────


def _candidate_sessions(start: Date, end: Date) -> list[Date]:
    """Weekdays in [start, end].

    Weekends are excluded locally because no exchange trades them and the
    request would be certain waste. Holidays are *not* excluded: no hardcoded
    holiday table stays correct, so the source is allowed to answer 'no rows'
    and that answer becomes the calendar.
    """
    days: list[Date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _existing_partitions(store: RawStore, dataset_id: str) -> set[str]:
    try:
        return store.manifest(dataset_id).partition_keys()
    except Exception:  # noqa: BLE001 — absence is the normal first-run case
        return set()


def _existing_record(store: RawStore, dataset_id: str, key: str):
    try:
        for partition in store.manifest(dataset_id).partitions:
            if partition.key == key:
                return partition
    except Exception:  # noqa: BLE001
        return None
    return None


def _publish_manifest(
    store: RawStore,
    spec: DatasetSpec,
    partitions: list[Any],
    columns: list[str],
    *,
    gaps: Optional[dict[str, list[str]]] = None,
) -> None:
    """Rewrite the manifest after each partition so an interrupted run is readable.

    The manifest is metadata about immutable files, not one of them — rewriting
    it is how a resumed backfill stays inspectable mid-flight.
    """
    manifest = DatasetManifest(
        dataset_id=spec.dataset_id,
        source=spec.source,
        repository=spec.repository,
        table=spec.table,
        source_version=f"{spec.repository}@{DEFAULT_BRANCH}",
        columns=columns,
        partitions=list(partitions),
        point_in_time_status=spec.point_in_time.value,
        point_in_time_note=spec.point_in_time_note,
        survivorship_status=spec.survivorship.value,
        survivorship_note=spec.survivorship_note,
        licence=spec.licence,
        transformations=[
            "renamed act_symbol->symbol, ex_date/last_seen->date",
            "cast API strings to numeric with errors=coerce (unparseable -> NULL, never 0)",
            "uppercased symbols",
        ],
        notes=[
            *spec.limitations,
            *(
                [
                    f"INCOMPLETE PARTITIONS: {sum(len(v) for v in gaps.values())} session(s) "
                    f"could not be fetched across {len(gaps)} partition(s) and are absent "
                    f"from the data: {json.dumps(gaps)[:600]}. Returns spanning these "
                    "sessions are wrong by the size of the gap."
                ]
                if gaps
                else []
            ),
        ],
    )
    store.write_manifest(manifest)


def ingest_spec(
    spec: DatasetSpec,
    store: RawStore,
    *,
    start: Optional[Date] = None,
    end: Optional[Date] = None,
    symbols: Optional[Sequence[str]] = None,
    client: Optional[DoltHubClient] = None,
    workers: int = DEFAULT_WORKERS,
    on_progress: Optional[ProgressFn] = None,
    dates: Optional[Sequence[Date]] = None,
) -> IngestionReport:
    """Dispatch on the spec's declared ingestion mode."""
    if spec.ingestion is IngestionMode.WHOLE_TABLE:
        return ingest_whole_table(spec, store, client=client)
    if spec.ingestion is IngestionMode.SYMBOL_PARTITIONED:
        if not symbols:
            raise ValueError(f"{spec.dataset_id} is symbol-partitioned and needs symbols")
        return ingest_by_symbol(spec, store, symbols, client=client, workers=workers)
    if spec.ingestion is IngestionMode.DATE_PARTITIONED:
        if start is None or end is None:
            raise ValueError(f"{spec.dataset_id} is date-partitioned and needs start/end")
        return ingest_date_partitioned(
            spec, store, start=start, end=end, symbols=symbols,
            client=client, workers=workers, on_progress=on_progress, dates=dates,
        )
    raise ValueError(
        f"{spec.dataset_id} declares ingestion mode {spec.ingestion.value}, which "
        "this module does not handle — HTTP archives are fetched by their own client"
    )
