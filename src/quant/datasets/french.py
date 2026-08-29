"""
Kenneth French Data Library — the benchmark that makes one word usable.

## Why this source, specifically

This repository's terminology standard is explicit: a strategy's return minus
a benchmark's return is a **return difference**, and calling it alpha without
a model that produces an intercept is a claim the arithmetic does not support.
Honouring that standard requires factor returns, and the French library is the
canonical free source of them.

With these series a strategy's returns can be regressed on

    r_t - rf_t = a + b1*MktRF + b2*SMB + b3*HML + b4*RMW + b5*CMA + b6*MOM + e_t

and `a` is an intercept with a standard error. That is the only number in this
codebase permitted to be called alpha, and `src/quant/backtest/attribution.py`
is the only place that computes it.

It also answers, directly rather than by assertion, the research question
"does the model add information beyond simple factors?" — a signal whose
returns are fully explained by momentum has not added information, however
good its information coefficient looks.

## Revision, and why it bars this from features

The library is rebuilt when CRSP is revised, so a value downloaded today for
2015-03-10 is not necessarily what was published in 2015. It is therefore
catalogued `PUBLICATION_LAGGED`, not `POINT_IN_TIME`, and the distinction is
enforced by use rather than by memory:

* **Permitted** — evaluating realised strategy returns after the fact. Revision
  moves the benchmark's history, not the strategy's, and an attribution is an
  explicitly retrospective statement.
* **Barred** — any feature. A feature is consumed by a model that trades on it,
  and feeding it a revised series backdates knowledge that did not exist.

`src/quant/pit/dataset.py` refuses to admit this dataset as a feature source.
"""

from __future__ import annotations

import http.client
import io
import logging
import time
import urllib.request
import zipfile
from typing import Any, Optional

import pandas as pd

from src.quant.datasets.catalog import FRENCH_FACTORS
from src.quant.datasets.ingest import IngestionReport
from src.quant.datasets.store import DatasetManifest, RawStore

logger = logging.getLogger("omnisignal.quant.datasets.french")

_ROOT = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"

FIVE_FACTOR_URL = f"{_ROOT}/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
MOMENTUM_URL = f"{_ROOT}/F-F_Momentum_Factor_daily_CSV.zip"

_USER_AGENT = "OmniSignal-Research/1.0 (academic factor benchmark retrieval)"

#: Source header -> canonical name. The library's headers carry stray spaces
#: and a hyphen; normalising here means one place to be wrong.
_COLUMN_MAP = {
    "Mkt-RF": "mkt_rf",
    "SMB": "smb",
    "HML": "hml",
    "RMW": "rmw",
    "CMA": "cma",
    "RF": "rf",
    "Mom": "mom",
    "MOM": "mom",
}


class FrenchDownloadError(RuntimeError):
    """Raised rather than returning a partial factor set."""


def _download(url: str, *, timeout: float = 120.0, retries: int = 6) -> bytes:
    """Fetch a zip, resuming by byte range until the archive is intact.

    Observed against this host: transfers intermittently end short of the
    advertised `Content-Length`, and for one of the two files they end short at
    the *same* offset every time — so plain retry never converges. The host
    advertises `Accept-Ranges: bytes`, so the fix is to resume from where the
    stream stopped rather than restart it.

    Acceptance is `zipfile` opening the bytes and its members passing CRC, not
    a length comparison. That is the property that matters: a short read
    carrying a complete archive is usable, and a full-length read of a corrupt
    one is not.
    """
    buffer = bytearray()
    last: Exception | None = None

    for attempt in range(retries):
        headers = {"User-Agent": _USER_AGENT}
        if buffer:
            headers["Range"] = f"bytes={len(buffer)}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                # A server that ignores Range replies 200 with the whole body;
                # appending it to what we already hold would corrupt the file.
                if buffer and response.status != 206:
                    buffer.clear()
                buffer.extend(response.read())
        except http.client.IncompleteRead as error:
            buffer.extend(error.partial)
            last = error
        except Exception as error:  # noqa: BLE001 — retried, then raised
            last = error

        if buffer and _archive_is_intact(bytes(buffer)):
            return bytes(buffer)
        logger.warning(
            "french: %s incomplete after attempt %d (%d bytes held); resuming",
            url.rsplit("/", 1)[-1], attempt + 1, len(buffer),
        )
        if attempt < retries - 1:
            time.sleep(1.0 * (attempt + 1))

    raise FrenchDownloadError(
        f"{url}: {retries} attempts produced no intact archive "
        f"({len(buffer)} bytes held; last error: {last})"
    )


def _archive_is_intact(payload: bytes) -> bool:
    """Whether these bytes are a zip whose members pass their CRC."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return archive.testzip() is None and bool(archive.namelist())
    except (zipfile.BadZipFile, OSError, EOFError):
        return False


def parse_french_csv(payload: bytes) -> pd.DataFrame:
    """Parse one library zip into a tidy daily frame.

    The file format is a prose header of unpredictable length, then a CSV block
    keyed by `YYYYMMDD`, then a copyright footer — and for some files, further
    annual blocks after a blank line. The parser therefore locates the daily
    block by **row shape** (an 8-digit date token) rather than by a hardcoded
    skiprows count, which is the only version of this that survives the library
    reformatting its preamble.
    """
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = archive.namelist()[0]
        text = archive.read(name).decode("latin-1")

    lines = text.splitlines()
    header: Optional[list[str]] = None
    records: list[dict[str, Any]] = []

    for line in lines:
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) < 2:
            continue
        token = cells[0]
        if token.isdigit() and len(token) == 8:
            if header is None:
                continue
            values = cells[1 : len(header) + 1]
            if len(values) < len(header):
                continue
            row: dict[str, Any] = {"date": token}
            usable = True
            for name_, value in zip(header, values):
                try:
                    number = float(value)
                except ValueError:
                    usable = False
                    break
                # The library publishes percent; -99.99 is its missing marker.
                row[name_] = None if number <= -99.0 else number / 100.0
            if usable:
                records.append(row)
        elif not token and any(cell for cell in cells[1:]):
            candidate = [_COLUMN_MAP.get(cell, cell.lower()) for cell in cells[1:] if cell]
            if candidate:
                header = candidate

    if not records:
        raise FrenchDownloadError("no daily rows parsed — the file layout changed")

    frame = pd.DataFrame(records)
    frame["date"] = pd.to_datetime(frame["date"], format="%Y%m%d").dt.date
    return frame.sort_values("date").reset_index(drop=True)


def fetch_french_factors() -> pd.DataFrame:
    """Download and join the 5-factor and momentum daily series.

    An **inner** join on date, deliberately. The two files are published on
    different schedules, so an outer join yields trailing rows where momentum
    is present and the market factor is not. A factor model estimated on rows
    with a missing regressor is not the model that was specified, and silently
    dropping those rows inside the regression would hide which dates the
    estimate actually covers.
    """
    five = parse_french_csv(_download(FIVE_FACTOR_URL))
    momentum = parse_french_csv(_download(MOMENTUM_URL))
    joined = five.merge(momentum[["date", "mom"]], on="date", how="inner")
    missing = [c for c in ("mkt_rf", "smb", "hml", "rmw", "cma", "rf", "mom") if c not in joined]
    if missing:
        raise FrenchDownloadError(f"factor columns absent after parse: {missing}")
    return joined[["date", "mkt_rf", "smb", "hml", "rmw", "cma", "rf", "mom"]]


def ingest_french_factors(store: RawStore, *, resume: bool = True) -> IngestionReport:
    """Fetch and store the factor library as one immutable partition."""
    spec = FRENCH_FACTORS
    report = IngestionReport(dataset_id=spec.dataset_id)
    began = time.perf_counter()

    if resume and store.has_partition(spec.dataset_id, "all"):
        report.partitions_skipped.append("all")
        report.elapsed_seconds = time.perf_counter() - began
        return report

    frame = fetch_french_factors()
    record = store.write_partition(spec.dataset_id, "all", frame, symbol_column="__none__")
    store.write_manifest(
        DatasetManifest(
            dataset_id=spec.dataset_id,
            source=spec.source,
            repository=spec.repository,
            table=spec.table,
            source_version=f"downloaded {record.written_at[:10]}",
            columns=list(frame.columns),
            partitions=[record],
            point_in_time_status=spec.point_in_time.value,
            point_in_time_note=spec.point_in_time_note,
            survivorship_status=spec.survivorship.value,
            survivorship_note=spec.survivorship_note,
            licence=spec.licence,
            transformations=[
                "parsed the daily block by row shape, not a fixed skiprows",
                "converted percent to decimal (value / 100)",
                "mapped the library's -99.99 missing marker to NULL, never 0",
                "inner-joined 5-factor and momentum on date",
            ],
            notes=list(spec.limitations),
        )
    )
    report.partitions_written.append("all")
    report.rows = record.rows
    report.elapsed_seconds = time.perf_counter() - began
    logger.info("french factors: %d daily rows", record.rows)
    return report
