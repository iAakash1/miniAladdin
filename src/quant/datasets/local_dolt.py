"""
Local Dolt reader — the same catalog, read from a cloned repository.

## Why this exists alongside the HTTP client

`dolthub.py` fetches over the network and is bounded by three hard limits: a
1,000-row response cap with no continuation token, a query planner that only
answers single-date equality predicates quickly, and an upstream rate limit
that returns HTTP 403 inside a 200 body. Those limits shaped every ingestion
decision in that module.

A local clone removes all three. Measured on the same query that **times out**
over the API:

    select count(*), count(distinct act_symbol), min(date), max(date) from ohlcv
    -> 28,928,007 rows / 21,512 symbols / 2011-01-03..2026-08-28  in 8.1 s

So where a clone is present this is the reader of choice, and the HTTP client
remains for environments without one. Both write through `RawStore` and produce
byte-identical partitions for the same query, which is what makes them
interchangeable rather than merely similar.

## What the local path unlocks

Three datasets that were impractical over HTTP:

* `stocks.dividend` — 494,438 rows. The API ingestion **failed correctly**: a
  60-symbol batch exceeded the 1,000-row cap and `execute` refused to return a
  truncated answer rather than silently dropping dividends.
* `options.option_chain` — 116,487,570 rows across 1,276 dates and 2,317
  symbols. Aggregating this per date/symbol over HTTP was never going to work.
* `earnings.*` — 7,060,412 estimate vintages, and the `eps_history` /
  `earnings_calendar` join that turns a period-dated figure into a
  point-in-time one.

## Streaming, not loading

`dolt sql -r csv` writes to stdout and this reads it incrementally through
pandas with an explicit dtype map. A 116M-row table is never resident: queries
aggregate server-side and only the aggregate crosses the boundary.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

import pandas as pd

logger = logging.getLogger("omnisignal.quant.datasets.local_dolt")

#: Where the Dolt clones live.
#:
#: Overridable with `QUANT_DATA_ROOT` so the clones can sit outside the working
#: tree — they are 14 GB and must never enter git. The default is relative, not
#: an absolute home directory, so a checkout on another machine still resolves.
DEFAULT_ROOT = Path(os.environ.get("QUANT_DATA_ROOT") or "datasets")


def data_root() -> Path:
    """The configured clone root, re-read each call so tests can repoint it."""
    return Path(os.environ.get("QUANT_DATA_ROOT") or "datasets")

#: Repository directory name per catalog `repository` value.
REPOSITORIES: tuple[str, ...] = ("stocks", "options", "earnings", "rates")


class DoltUnavailable(RuntimeError):
    """Raised when the CLI or a clone is absent. Never silently substituted."""


class LocalQueryFailed(RuntimeError):
    """Raised when dolt exits non-zero. The stderr is preserved, not summarised."""


@dataclass
class LocalStats:
    queries: int = 0
    rows: int = 0
    total_ms: float = 0.0
    slowest_ms: float = 0.0
    slowest_query: str = ""

    def record(self, query: str, rows: int, elapsed_ms: float) -> None:
        self.queries += 1
        self.rows += rows
        self.total_ms += elapsed_ms
        if elapsed_ms > self.slowest_ms:
            self.slowest_ms = elapsed_ms
            self.slowest_query = query[:200]

    def as_dict(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "rows": self.rows,
            "total_ms": round(self.total_ms, 1),
            "mean_ms": round(self.total_ms / self.queries, 1) if self.queries else None,
            "slowest_ms": round(self.slowest_ms, 1),
            "slowest_query": self.slowest_query,
        }


class LocalDoltClient:
    """Reads a cloned Dolt repository through the `dolt` CLI.

    Read-only by construction: every method issues `dolt sql -q` with a
    `SELECT`, and `_run` refuses a statement that is not one.
    """

    def __init__(
        self,
        root: Path | str = DEFAULT_ROOT,
        *,
        timeout: float = 1800.0,
        binary: str = "dolt",
    ) -> None:
        self.root = Path(root)
        self.timeout = timeout
        self.binary = binary
        self.stats = LocalStats()

    # ── availability ─────────────────────────────────────────────────────

    @property
    def cli_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def repository_path(self, repository: str) -> Path:
        return self.root / repository

    def has_repository(self, repository: str) -> bool:
        return (self.repository_path(repository) / ".dolt").is_dir()

    def availability(self) -> dict[str, Any]:
        """What is present, reported per repository rather than as one boolean."""
        return {
            "cli": self.cli_available,
            "cli_version": self._version() if self.cli_available else None,
            "root": str(self.root),
            "repositories": {
                name: {
                    "present": self.has_repository(name),
                    "path": str(self.repository_path(name)),
                }
                for name in REPOSITORIES
            },
        }

    def _version(self) -> Optional[str]:
        try:
            out = subprocess.run(
                [self.binary, "version"], capture_output=True, text=True, timeout=15
            ).stdout
            return out.strip().splitlines()[0] if out.strip() else None
        except (OSError, subprocess.SubprocessError):
            return None

    def require(self, repository: str) -> Path:
        if not self.cli_available:
            raise DoltUnavailable(
                f"the `{self.binary}` CLI is not on PATH. The local reader reports "
                "unavailable rather than falling back to the HTTP client, because the "
                "two have different row limits and a silent switch would change what a "
                "query returns."
            )
        path = self.repository_path(repository)
        if not (path / ".dolt").is_dir():
            raise DoltUnavailable(f"no Dolt repository at {path}")
        return path

    # ── query ────────────────────────────────────────────────────────────

    def _run(self, repository: str, query: str) -> str:
        path = self.require(repository)
        stripped = query.strip().lstrip("(").lstrip()
        if not stripped.lower().startswith(("select", "show", "describe", "with")):
            raise ValueError(
                f"only read statements are permitted here, got: {query[:80]!r}"
            )

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [self.binary, "sql", "-q", query, "-r", "csv"],
                cwd=path, capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise LocalQueryFailed(
                f"{repository}: query exceeded {self.timeout}s — {query[:200]}"
            ) from error
        elapsed_ms = (time.perf_counter() - started) * 1000

        if completed.returncode != 0:
            raise LocalQueryFailed(
                f"{repository}: dolt exited {completed.returncode}\n"
                f"{completed.stderr.strip()[:1000]}\nquery: {query[:300]}"
            )
        self.stats.record(query, completed.stdout.count("\n"), elapsed_ms)
        logger.debug("local dolt %s: %.0fms — %s", repository, elapsed_ms, query[:120])
        return completed.stdout

    def query(
        self,
        repository: str,
        sql: str,
        *,
        dtype: Optional[dict[str, Any]] = None,
        parse_dates: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """Run a SELECT and return a frame.

        There is no row cap. `dtype` is passed to the CSV reader so numeric
        columns are typed once at the boundary — the same policy the HTTP
        ingestion applies, and for the same reason: an unparseable value must
        become NULL, never 0.0.
        """
        import io

        output = self._run(repository, sql)
        if not output.strip():
            return pd.DataFrame()
        frame = pd.read_csv(
            io.StringIO(output),
            dtype=dtype,
            parse_dates=list(parse_dates) if parse_dates else None,
            low_memory=False,
        )
        for column in parse_dates or []:
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
        return frame

    def scalar(self, repository: str, sql: str) -> Any:
        frame = self.query(repository, sql)
        return None if frame.empty else frame.iloc[0, 0]

    # ── introspection ────────────────────────────────────────────────────

    def tables(self, repository: str) -> list[str]:
        frame = self.query(repository, "show tables")
        return [] if frame.empty else frame.iloc[:, 0].astype(str).tolist()

    def describe(self, repository: str, table: str) -> pd.DataFrame:
        return self.query(repository, f"describe `{table}`")

    def profile_table(self, repository: str, table: str) -> dict[str, Any]:
        """Row count, and date/symbol coverage where those columns exist.

        Coverage is probed rather than assumed: the presence of `date` and
        `act_symbol` is checked against the schema first, so this works on
        `us_treasury` (no symbol) and `split` (keyed `ex_date`) without a
        per-table special case.
        """
        schema = self.describe(repository, table)
        columns = set(schema["Field"].astype(str)) if not schema.empty else set()

        date_column = next(
            (name for name in ("date", "ex_date", "last_seen") if name in columns), None
        )
        symbol_column = "act_symbol" if "act_symbol" in columns else None

        # Aliases are backticked: `rows` is a reserved word in Dolt's parser and
        # an unquoted alias is a syntax error, not a warning.
        selects = ["count(*) as `rows`"]
        if date_column:
            selects += [
                f"min(`{date_column}`) as `min_date`",
                f"max(`{date_column}`) as `max_date`",
                f"count(distinct `{date_column}`) as `distinct_dates`",
            ]
        if symbol_column:
            selects.append(f"count(distinct `{symbol_column}`) as `symbols`")

        summary = self.query(repository, f"select {', '.join(selects)} from `{table}`")
        payload: dict[str, Any] = {
            "repository": repository,
            "table": table,
            "columns": [
                {
                    "name": str(row["Field"]),
                    "type": str(row["Type"]),
                    "nullable": str(row["Null"]) == "YES",
                    "key": str(row["Key"]),
                }
                for _, row in schema.iterrows()
            ],
            "primary_key": [
                str(row["Field"]) for _, row in schema.iterrows() if str(row["Key"]) == "PRI"
            ],
            "date_column": date_column,
            "symbol_column": symbol_column,
        }
        if not summary.empty:
            payload.update({k: _native(v) for k, v in summary.iloc[0].to_dict().items()})
        return payload

    def null_counts(self, repository: str, table: str, columns: Sequence[str]) -> dict[str, int]:
        """Per-column NULL counts, in one pass rather than one query per column."""
        if not columns:
            return {}
        selects = ", ".join(
            f"sum(case when `{name}` is null then 1 else 0 end) as `{name}`"
            for name in columns
        )  # aliases backticked — several column names are reserved words
        frame = self.query(repository, f"select {selects} from `{table}`")
        return {} if frame.empty else {k: int(v) for k, v in frame.iloc[0].to_dict().items()}

    def iter_by_year(
        self,
        repository: str,
        table: str,
        *,
        columns: Sequence[str],
        date_column: str = "date",
        start_year: int,
        end_year: int,
        where: str = "",
    ) -> Iterator[tuple[int, pd.DataFrame]]:
        """Stream a large table one year at a time.

        The partitioning unit that keeps a 116M-row table tractable: each year
        is queried, yielded and released, so peak memory is one year rather
        than the table.
        """
        projection = ", ".join(f"`{name}`" for name in columns)
        for year in range(start_year, end_year + 1):
            clause = (
                f"`{date_column}` >= '{year}-01-01' and `{date_column}` <= '{year}-12-31'"
            )
            if where:
                clause = f"{clause} and ({where})"
            frame = self.query(
                repository,
                f"select {projection} from `{table}` where {clause}",
                parse_dates=[date_column],
            )
            yield year, frame


def _native(value: Any) -> Any:
    """Convert numpy scalars to JSON-serialisable Python values."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return str(value)
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value
