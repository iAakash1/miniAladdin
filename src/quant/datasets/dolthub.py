"""
DoltHub SQL-over-HTTP client — the ingestion path for deep market history.

## Why this exists

`docs/PANEL.md` §5.2 records the binding constraint on every backtest in this
repository: the vendor fabric's free tiers cap daily history at roughly **501
bars (~2 years)** regardless of the range requested. §5.1 records the other
one: universes are *current* membership, so every historical study is
survivorship-biased and there is no free source of point-in-time membership.

`post-no-preference/stocks` on DoltHub answers both. Measured directly
against the live API (not inferred from documentation):

* `ohlcv` covers **2011-01-03 → 2026-08-21**, 3,844 symbols on the first day
  and 12,470 on the last.
* `symbol` carries `last_seen`, and delisted names are present with honest
  terminal dates — SIVB and SBNY both carry `financial_status = 'Bankrupt'`
  and `last_seen = 2023-03-26`, and SIVB's bars stop the day trading was
  halted, after a -60% close.

That makes a survivorship-free universe constructible for the first time.

## The query-shape constraint, measured

The table's primary key is `(date, act_symbol)`, and the deployed engine only
uses the index for an **equality** predicate on `date`. This is not a guess;
it is the difference between a query that answers and one that does not:

| Query shape                                   | Result          |
| --------------------------------------------- | --------------- |
| `date = '2024-01-02' AND act_symbol IN (50)`   | 50 rows, 0.95 s |
| `date BETWEEN 4 days AND act_symbol IN (5)`    | 20 rows, 30.8 s |
| `act_symbol = 'AAPL' AND date BETWEEN 1 month` | **timeout**     |

So every ingestion here partitions on a **single date** and fans out across
dates. The alternative — streaming the table's CSV export — was measured at
~271 KB/s, which is ~1.6 h for the ~1.6 GB `ohlcv` table and pulls 12,000
symbols to use 50. Date-partitioned SQL fetches only the universe asked for.

## Truncation is an error, never a shrug

The API caps every response at 1,000 rows and signals it with
`query_execution_status = "RowLimit"` — with **no pagination token**. A client
that ignores that field silently returns a truncated answer that looks
complete, which is the single worst failure mode a research data path can
have. `execute()` raises `RowLimitExceeded` instead, and callers that expect
volume must partition until each partition fits.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

logger = logging.getLogger("omnisignal.quant.datasets.dolthub")

API_ROOT = "https://www.dolthub.com/api/v1alpha1"

#: Substrings in `query_execution_message` that indicate a transient upstream
#: condition rather than a malformed query. Matched case-insensitively.
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "http status: 403",   # upstream rate limit, returned inside a 200 body
    "http status: 429",
    "http status: 50",    # 500/502/503/504
    "context deadline exceeded",
    "connection reset",
    "temporarily unavailable",
    "too many requests",
)

#: The API's hard response cap. Rows beyond this are dropped with a status
#: flag and no continuation token, so the ceiling has to be known here.
ROW_LIMIT = 1000

#: Rows per page for the paginated whole-market path. Defaults to the API's
#: own cap, because a smaller page only costs extra round trips.
#:
#: Lower it on a constrained network. Some HTTP paths — a filtering proxy, for
#: instance — truncate large response bodies, which surfaces as
#: `IncompleteRead` at a *consistent* byte offset. Retrying a deterministically
#: truncated request never converges, so the correct response is a smaller
#: page, not more attempts. `OMNISIGNAL_DOLT_PAGE_SIZE` sets it without a code
#: change. Truncation is never silently accepted: `_get_with_retry` treats it
#: as a failure and the ingestion records the date as failed.
SAFE_PAGE_SIZE = max(50, min(ROW_LIMIT, int(os.getenv("OMNISIGNAL_DOLT_PAGE_SIZE", ROW_LIMIT))))

#: Default branch for the `post-no-preference` repositories. `main` does not
#: exist on them and returns "branch not found"; this was verified per repo.
DEFAULT_BRANCH = "master"

_USER_AGENT = "OmniSignal-Research/1.0 (quantitative research; contact via repository)"


class DoltHubError(RuntimeError):
    """Base class for every failure this client reports rather than hides."""


class QueryFailed(DoltHubError):
    """The server executed the query and returned an error message."""


class TransientQueryError(QueryFailed):
    """A server-side error that is worth retrying.

    The endpoint answers HTTP 200 and reports upstream failures **inside the
    JSON body** — `query_execution_message` carries strings like
    `"query error: http status: 403"` or `"query error: context deadline
    exceeded"`. A client that classifies on HTTP status alone therefore sees a
    successful response and treats a transient rate-limit as a permanent
    failure, which in an ingestion means a silently missing date.
    """


class RowLimitExceeded(DoltHubError):
    """The response was truncated at :data:`ROW_LIMIT`.

    Raised rather than returned because a truncated result is
    indistinguishable from a complete one at the call site, and a research
    dataset assembled from silently truncated partitions is wrong in a way
    that no downstream test can detect.
    """


@dataclass(frozen=True)
class QueryResult:
    """One executed query, with the timing and status needed for provenance."""

    rows: list[dict[str, Any]]
    columns: list[str]
    status: str
    elapsed_ms: float
    query: str
    repository: str
    branch: str

    @property
    def truncated(self) -> bool:
        return self.status == "RowLimit"


@dataclass
class ClientStats:
    """Counters an ingestion run reports instead of estimating."""

    requests: int = 0
    rows: int = 0
    retries: int = 0
    errors: int = 0
    total_ms: float = 0.0
    slowest_ms: float = 0.0
    per_repository: dict[str, int] = field(default_factory=dict)

    def record(self, repository: str, rows: int, elapsed_ms: float) -> None:
        self.requests += 1
        self.rows += rows
        self.total_ms += elapsed_ms
        self.slowest_ms = max(self.slowest_ms, elapsed_ms)
        self.per_repository[repository] = self.per_repository.get(repository, 0) + rows

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "rows": self.rows,
            "retries": self.retries,
            "errors": self.errors,
            "total_ms": round(self.total_ms, 1),
            "mean_ms": round(self.total_ms / self.requests, 1) if self.requests else None,
            "slowest_ms": round(self.slowest_ms, 1),
            "per_repository": dict(self.per_repository),
        }


class DoltHubClient:
    """Read-only SQL access to a DoltHub repository.

    Read-only is structural, not a convention: the endpoint this talks to
    serves `SELECT` and nothing else, so there is no write path to guard.
    """

    def __init__(
        self,
        owner: str = "post-no-preference",
        *,
        timeout: float = 90.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.5,
    ) -> None:
        self.owner = owner
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.stats = ClientStats()

    # ── core ─────────────────────────────────────────────────────────────

    def execute(
        self,
        repository: str,
        query: str,
        *,
        branch: str = DEFAULT_BRANCH,
        allow_truncation: bool = False,
    ) -> QueryResult:
        """Run one SQL statement.

        Raises :class:`RowLimitExceeded` when the server truncated the
        response, unless the caller explicitly says a partial answer is what
        it wanted (schema probes, existence checks).
        """
        url = (
            f"{API_ROOT}/{self.owner}/{repository}/{branch}"
            f"?q={urllib.parse.quote(query)}"
        )
        last_transient: Exception | None = None
        for attempt in range(self.max_retries):
            payload = self._get_with_retry(url, repository, query)
            message = payload.get("query_execution_message") or ""
            status = payload.get("query_execution_status") or "Unknown"
            if status in {"Success", "RowLimit"}:
                break
            self.stats.errors += 1
            if not _is_transient(message):
                raise QueryFailed(f"{repository}: {message or status} — query: {query[:200]}")
            last_transient = TransientQueryError(f"{repository}: {message}")
            self.stats.retries += 1
            if attempt < self.max_retries - 1:
                delay = self.backoff_seconds * (2**attempt) * 2.0
                logger.warning(
                    "dolthub %s transient error (%s); retrying in %.1fs", repository, message, delay
                )
                time.sleep(delay)
        else:
            raise last_transient or QueryFailed(f"{repository}: exhausted retries")

        rows = payload.get("rows") or []
        columns = [column["columnName"] for column in payload.get("schema") or []]
        result = QueryResult(
            rows=rows,
            columns=columns,
            status=status,
            elapsed_ms=payload["_elapsed_ms"],
            query=query,
            repository=repository,
            branch=branch,
        )
        if result.truncated and not allow_truncation:
            raise RowLimitExceeded(
                f"{repository}: response truncated at {ROW_LIMIT} rows and the API "
                "offers no continuation token — partition the query further. "
                f"Query: {query[:200]}"
            )
        return result

    def _get_with_retry(self, url: str, repository: str, query: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        last: Exception | None = None

        for attempt in range(self.max_retries):
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                elapsed_ms = (time.perf_counter() - started) * 1000
                payload["_elapsed_ms"] = elapsed_ms
                self.stats.record(repository, len(payload.get("rows") or []), elapsed_ms)
                return payload
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                json.JSONDecodeError,
                http.client.HTTPException,  # IncompleteRead lives here, not under OSError
                OSError,
            ) as error:
                last = error
                self.stats.retries += 1
                if attempt < self.max_retries - 1:
                    delay = self.backoff_seconds * (2**attempt)
                    logger.warning(
                        "dolthub %s attempt %d/%d failed (%s); retrying in %.1fs",
                        repository, attempt + 1, self.max_retries, error, delay,
                    )
                    time.sleep(delay)

        self.stats.errors += 1
        raise DoltHubError(
            f"{repository}: {self.max_retries} attempts failed ({last}) — query: {query[:200]}"
        )

    # ── introspection ────────────────────────────────────────────────────

    def tables(self, repository: str, *, branch: str = DEFAULT_BRANCH) -> list[str]:
        result = self.execute(repository, "show tables", branch=branch)
        return [next(iter(row.values())) for row in result.rows]

    def describe(
        self, repository: str, table: str, *, branch: str = DEFAULT_BRANCH
    ) -> list[dict[str, Any]]:
        result = self.execute(repository, f"describe `{table}`", branch=branch)
        return [
            {
                "column": row["Field"],
                "type": row["Type"],
                "nullable": row["Null"] == "YES",
                "key": row["Key"],
            }
            for row in result.rows
        ]

    def distinct_dates(
        self,
        repository: str,
        table: str,
        *,
        column: str = "date",
        ascending: bool = True,
        limit: int = 1000,
        branch: str = DEFAULT_BRANCH,
    ) -> list[str]:
        """Dates present in a table, cheapest-first.

        Grouping is done server-side on the primary-key prefix, which is the
        one aggregate shape the engine answers quickly.
        """
        order = "asc" if ascending else "desc"
        query = (
            f"select `{column}` from `{table}` "
            f"group by `{column}` order by `{column}` {order} limit {int(limit)}"
        )
        result = self.execute(repository, query, branch=branch, allow_truncation=True)
        return [str(row[column]) for row in result.rows]

    # ── date-partitioned reads ───────────────────────────────────────────

    def rows_for_date(
        self,
        repository: str,
        table: str,
        trade_date: str,
        *,
        symbols: Optional[Sequence[str]] = None,
        columns: Optional[Sequence[str]] = None,
        symbol_column: str = "act_symbol",
        date_column: str = "date",
        branch: str = DEFAULT_BRANCH,
    ) -> list[dict[str, Any]]:
        """Every row for one date, optionally restricted to a symbol list.

        The single-date equality predicate is the whole reason this signature
        exists — see the module docstring's measured query table. When
        `symbols` is omitted the caller is responsible for the row cap; a
        full market day is ~12,000 rows and *will* raise.
        """
        projection = ", ".join(f"`{name}`" for name in columns) if columns else "*"
        clauses = [f"`{date_column}` = '{_sql_date(trade_date)}'"]
        if symbols:
            clauses.append(f"`{symbol_column}` in ({_sql_symbol_list(symbols)})")
        query = f"select {projection} from `{table}` where {' and '.join(clauses)}"
        return self.execute(repository, query, branch=branch).rows

    def rows_for_date_paginated(
        self,
        repository: str,
        table: str,
        trade_date: str,
        *,
        columns: Optional[Sequence[str]] = None,
        date_column: str = "date",
        symbol_column: str = "act_symbol",
        page_size: int = SAFE_PAGE_SIZE,
        max_pages: int = 120,
        branch: str = DEFAULT_BRANCH,
    ) -> list[dict[str, Any]]:
        """A whole market date, assembled by keyset pagination within the date.

        Used when the universe is the entire market — universe construction and
        breadth. Pages advance on `symbol > last_seen_symbol` rather than
        `OFFSET`, for the reason measured in `whole_table`: offset cost grows
        with depth and a 12,000-row date is twelve pages deep.

        The symbol column is unique within a date (it is the rest of the primary
        key), so pages compose into the whole date with no row skipped or
        repeated.
        """
        projection = ", ".join(f"`{name}`" for name in columns) if columns else "*"
        if columns and symbol_column not in columns:
            projection = ", ".join(f"`{name}`" for name in [*columns, symbol_column])

        collected: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        for _ in range(max_pages):
            clauses = [f"`{date_column}` = '{_sql_date(trade_date)}'"]
            if cursor is not None:
                clauses.append(f"`{symbol_column}` > {_sql_literal(cursor)}")
            query = (
                f"select {projection} from `{table}` where {' and '.join(clauses)} "
                f"order by `{symbol_column}` limit {page_size}"
            )
            rows = self.execute(
                repository, query, branch=branch, allow_truncation=True
            ).rows
            collected.extend(rows)
            if len(rows) < page_size:
                return collected
            cursor = rows[-1][symbol_column]

        raise DoltHubError(
            f"{repository}.{table} on {trade_date}: still returning full pages after "
            f"{max_pages} pages ({len(collected)} rows) — refusing to guess where it ends"
        )

    def whole_table(
        self,
        repository: str,
        table: str,
        *,
        key: Sequence[str],
        columns: Optional[Sequence[str]] = None,
        page_size: int = SAFE_PAGE_SIZE,
        max_pages: int = 400,
        branch: str = DEFAULT_BRANCH,
    ) -> list[dict[str, Any]]:
        """Page through a table in full using **keyset** pagination.

        Not `OFFSET`. Measured on `stocks.symbol` (24,058 rows) with the full
        eight-column projection, holding everything but the pagination method
        fixed, and repeated to separate depth cost from the source's response
        caching:

        | Access                | Cold    | Repeat  |
        | --------------------- | ------- | ------- |
        | keyset, any depth     | 2.3 s   | 3.1 s   |
        | `OFFSET 1000`         | 4.0 s   | —       |
        | `OFFSET 20000`        | 47.7 s  | 35.7 s  |

        `OFFSET n` makes the engine produce and discard `n` rows, so cost grows
        with depth — and it stays slow on repeat, which is what distinguishes
        it from a cold cache. Keyset pagination asks for `key > last_key_seen`,
        an index seek, and is flat at ~2-3 s wherever it is in the table.

        `key` must be the table's primary key in key order, which guarantees
        both uniqueness (so no row is skipped or repeated at a page boundary)
        and index-ordered access. Composite keys use MySQL row-value syntax,
        `(a, b) > (x, y)`, which Dolt supports.
        """
        if not key:
            raise ValueError("keyset pagination requires the table's primary key")

        projection = ", ".join(f"`{name}`" for name in columns) if columns else "*"
        # The key must be selected even when the caller did not ask for it, or
        # there is no cursor to advance.
        needed = list(columns) if columns else None
        if needed is not None:
            for column in key:
                if column not in needed:
                    needed.append(column)
            projection = ", ".join(f"`{name}`" for name in needed)

        order = ", ".join(f"`{column}`" for column in key)
        collected: list[dict[str, Any]] = []
        cursor: Optional[tuple[Any, ...]] = None

        for page in range(max_pages):
            where = ""
            if cursor is not None:
                left = ", ".join(f"`{column}`" for column in key)
                right = ", ".join(_sql_literal(value) for value in cursor)
                where = (
                    f"where ({left}) > ({right}) "
                    if len(key) > 1
                    else f"where {left} > {right} "
                )
            query = (
                f"select {projection} from `{table}` {where}"
                f"order by {order} limit {page_size}"
            )
            result = self.execute(
                repository, query, branch=branch, allow_truncation=True
            )
            collected.extend(result.rows)
            logger.info(
                "dolthub %s.%s keyset page %d: +%d rows (%d total) in %.0fms",
                repository, table, page, len(result.rows), len(collected), result.elapsed_ms,
            )
            if len(result.rows) < page_size:
                return collected
            cursor = tuple(result.rows[-1][column] for column in key)

        raise DoltHubError(
            f"{repository}.{table}: exceeded {max_pages} keyset pages "
            f"({len(collected)} rows) — this table is larger than `whole_table` is meant for"
        )


def _is_transient(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


def _sql_literal(value: Any) -> str:
    """Render a keyset cursor value as a SQL literal.

    Only used for primary-key values that the server itself just returned, but
    quoted and escaped anyway: a value that round-trips through a query string
    is untrusted the moment it is concatenated, regardless of where it came from.
    """
    if value is None:
        raise ValueError("a keyset cursor cannot contain NULL")
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if len(text) > 128 or "\\" in text:
        raise ValueError(f"unsupported keyset cursor value {value!r}")
    return "'" + text.replace("'", "''") + "'"


def _sql_date(value: str) -> str:
    """Validate a date literal rather than interpolating whatever arrives.

    These queries are built by string composition because the endpoint takes a
    URL-encoded statement and offers no bind parameters. Validation therefore
    has to happen here, and it is strict: anything that is not `YYYY-MM-DD` is
    rejected outright rather than escaped and hoped for.
    """
    text = str(value)[:10]
    parts = text.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"invalid date literal {value!r}")
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        raise ValueError(f"invalid date literal {value!r}")
    return text


def _sql_symbol_list(symbols: Iterable[str]) -> str:
    """Render a symbol IN-list, refusing anything that is not a ticker.

    Same reasoning as `_sql_date`: no bind parameters are available, so the
    allowed alphabet is enumerated instead of escaped.
    """
    cleaned: list[str] = []
    for symbol in symbols:
        text = str(symbol).strip().upper()
        if not text or len(text) > 32:
            raise ValueError(f"invalid symbol {symbol!r}")
        if not all(character.isalnum() or character in ".-$/^" for character in text):
            raise ValueError(f"invalid symbol {symbol!r}")
        cleaned.append(f"'{text}'")
    if not cleaned:
        raise ValueError("symbol list cannot be empty")
    return ",".join(cleaned)
