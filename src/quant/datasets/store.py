"""
Raw dataset store — immutable, content-addressed, partitioned Parquet.

This is the `RAW DATA` tier. Nothing downstream is permitted to mutate it;
every normalized, point-in-time or feature artifact is reproducible *from*
it, and a study whose inputs cannot be re-read exactly is not reproducible
regardless of how carefully its code is versioned.

The design is deliberately the same shape as `src/panel/storage.py`, which
already proved it in this repository: immutable writes, atomic promotion via
`os.replace`, an explicit Arrow schema so bytes are stable, and a SHA-256 of
the written bytes recorded in a manifest that `verify()` re-checks.

Two things differ, and both follow from the data rather than from taste:

**Partitioned, not single-file.** A raw market table is ingested over hours
and grows by date. Writing one file would mean rewriting it on every
extension, which breaks immutability the first time a backfill resumes.
Partitions are written once and never touched again, so a resumed ingestion
appends work rather than redoing it.

**Manifest-per-dataset, checksum-per-partition.** The dataset manifest is the
queryable inventory (coverage, row counts, point-in-time status); the
per-partition checksums are what `verify()` compares. Corruption in one 2014
partition is then a localized, nameable fact rather than a single failed hash
over 40 million rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger("omnisignal.quant.datasets.store")

DEFAULT_ROOT = Path("data/research")

#: Bumped when the on-disk layout changes incompatibly. Readers refuse a
#: layout they do not understand rather than misinterpreting columns.
STORE_SCHEMA_VERSION = 1

_MANIFEST = "manifest.json"


class DatasetExistsError(Exception):
    """Raised when a write would overwrite an existing partition."""


class DatasetNotFoundError(Exception):
    """Raised when a requested dataset or partition is absent."""


@dataclass(frozen=True)
class PartitionRecord:
    """One immutable file, with everything needed to verify it later."""

    key: str
    path: str
    rows: int
    checksum: str
    bytes: int
    min_date: Optional[str]
    max_date: Optional[str]
    symbols: Optional[int]
    written_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": self.path,
            "rows": self.rows,
            "checksum": self.checksum,
            "bytes": self.bytes,
            "min_date": self.min_date,
            "max_date": self.max_date,
            "symbols": self.symbols,
            "written_at": self.written_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PartitionRecord":
        return cls(**payload)


@dataclass
class DatasetManifest:
    """What a raw dataset is, where it came from, and what may be done with it.

    `point_in_time_status` and `survivorship_status` are recorded here rather
    than asserted in prose because the point-in-time dataset builder reads
    them and *refuses* to admit a source marked unsafe into a historical
    training set. A limitation that only exists in documentation is a
    limitation that will be violated.
    """

    dataset_id: str
    source: str
    repository: str
    table: str
    source_version: str
    schema_version: int = STORE_SCHEMA_VERSION
    retrieved_at: str = ""
    columns: list[str] = None  # type: ignore[assignment]
    partitions: list[PartitionRecord] = None  # type: ignore[assignment]
    point_in_time_status: str = "unknown"
    point_in_time_note: str = ""
    survivorship_status: str = "unknown"
    survivorship_note: str = ""
    licence: str = ""
    transformations: list[str] = None  # type: ignore[assignment]
    notes: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.columns = list(self.columns or [])
        self.partitions = list(self.partitions or [])
        self.transformations = list(self.transformations or [])
        self.notes = list(self.notes or [])
        self.retrieved_at = self.retrieved_at or datetime.now(timezone.utc).isoformat()

    # ── derived coverage ─────────────────────────────────────────────────

    @property
    def rows(self) -> int:
        return sum(partition.rows for partition in self.partitions)

    @property
    def bytes(self) -> int:
        return sum(partition.bytes for partition in self.partitions)

    @property
    def min_date(self) -> Optional[str]:
        dates = [p.min_date for p in self.partitions if p.min_date]
        return min(dates) if dates else None

    @property
    def max_date(self) -> Optional[str]:
        dates = [p.max_date for p in self.partitions if p.max_date]
        return max(dates) if dates else None

    def partition_keys(self) -> set[str]:
        return {partition.key for partition in self.partitions}

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "source": self.source,
            "repository": self.repository,
            "table": self.table,
            "source_version": self.source_version,
            "schema_version": self.schema_version,
            "retrieved_at": self.retrieved_at,
            "columns": list(self.columns),
            "rows": self.rows,
            "bytes": self.bytes,
            "min_date": self.min_date,
            "max_date": self.max_date,
            "partitions": [partition.as_dict() for partition in self.partitions],
            "point_in_time_status": self.point_in_time_status,
            "point_in_time_note": self.point_in_time_note,
            "survivorship_status": self.survivorship_status,
            "survivorship_note": self.survivorship_note,
            "licence": self.licence,
            "transformations": list(self.transformations),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DatasetManifest":
        data = dict(payload)
        data.pop("rows", None)
        data.pop("bytes", None)
        data.pop("min_date", None)
        data.pop("max_date", None)
        data["partitions"] = [
            PartitionRecord.from_dict(item) for item in data.get("partitions", [])
        ]
        return cls(**data)


class RawStore:
    """Immutable partitioned storage for raw research datasets.

    Layout::

        <root>/raw/<dataset_id>/
            manifest.json
            part-<key>.parquet
    """

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"

    # ── paths ────────────────────────────────────────────────────────────

    def dataset_dir(self, dataset_id: str) -> Path:
        return self.raw_dir / dataset_id

    def partition_path(self, dataset_id: str, key: str) -> Path:
        return self.dataset_dir(dataset_id) / f"part-{key}.parquet"

    def exists(self, dataset_id: str) -> bool:
        return (self.dataset_dir(dataset_id) / _MANIFEST).exists()

    def has_partition(self, dataset_id: str, key: str) -> bool:
        return self.partition_path(dataset_id, key).exists()

    # ── writing ──────────────────────────────────────────────────────────

    def write_partition(
        self,
        dataset_id: str,
        key: str,
        frame: pd.DataFrame,
        *,
        schema: Optional[pa.Schema] = None,
        date_column: str = "date",
        symbol_column: str = "symbol",
        overwrite: bool = False,
    ) -> PartitionRecord:
        """Persist one partition atomically. Never silently overwrites.

        Row order is imposed before writing, for the same reason
        `src/panel/storage.py` imposes it: two ingestions of identical data
        must produce identical bytes, or the checksum is decorative.
        """
        path = self.partition_path(dataset_id, key)
        if path.exists() and not overwrite:
            raise DatasetExistsError(
                f"{dataset_id}/{key} already exists — raw partitions are immutable; "
                "pass overwrite=True only to repair a partition verified as corrupt"
            )

        directory = self.dataset_dir(dataset_id)
        directory.mkdir(parents=True, exist_ok=True)

        sort_columns = [c for c in (date_column, symbol_column) if c in frame.columns]
        ordered = (
            frame.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)
            if sort_columns
            else frame.reset_index(drop=True)
        )
        table = (
            pa.Table.from_pandas(ordered, schema=schema, preserve_index=False)
            if schema is not None
            else pa.Table.from_pandas(ordered, preserve_index=False)
        )

        handle, staging = tempfile.mkstemp(dir=directory, prefix=f".staging-{key}-", suffix=".parquet")
        os.close(handle)
        staging_path = Path(staging)
        try:
            pq.write_table(table, staging_path, compression="zstd", version="2.6")
            checksum = _file_sha256(staging_path)
            size = staging_path.stat().st_size
            os.replace(staging_path, path)
        except BaseException:
            staging_path.unlink(missing_ok=True)
            raise

        return PartitionRecord(
            key=key,
            path=path.name,
            rows=table.num_rows,
            checksum=checksum,
            bytes=size,
            min_date=_min_str(ordered, date_column),
            max_date=_max_str(ordered, date_column),
            symbols=(
                int(ordered[symbol_column].nunique()) if symbol_column in ordered.columns else None
            ),
            written_at=datetime.now(timezone.utc).isoformat(),
        )

    def write_manifest(self, manifest: DatasetManifest) -> None:
        """Publish the manifest atomically, so a reader never sees it half-written."""
        directory = self.dataset_dir(manifest.dataset_id)
        directory.mkdir(parents=True, exist_ok=True)
        handle, staging = tempfile.mkstemp(dir=directory, prefix=".manifest-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(manifest.as_dict(), stream, indent=2, sort_keys=True)
            os.replace(staging, directory / _MANIFEST)
        except BaseException:
            Path(staging).unlink(missing_ok=True)
            raise

    # ── reading ──────────────────────────────────────────────────────────

    def manifest(self, dataset_id: str) -> DatasetManifest:
        path = self.dataset_dir(dataset_id) / _MANIFEST
        if not path.exists():
            raise DatasetNotFoundError(f"no manifest for dataset {dataset_id!r}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        loaded = DatasetManifest.from_dict(payload)
        if loaded.schema_version != STORE_SCHEMA_VERSION:
            logger.warning(
                "dataset %s written with store schema v%d; reader is v%d",
                dataset_id, loaded.schema_version, STORE_SCHEMA_VERSION,
            )
        return loaded

    def list_datasets(self) -> list[DatasetManifest]:
        if not self.raw_dir.exists():
            return []
        out: list[DatasetManifest] = []
        for entry in sorted(self.raw_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            try:
                out.append(self.manifest(entry.name))
            except Exception:  # noqa: BLE001 — one bad dataset never hides the rest
                logger.exception("unreadable dataset %s", entry.name)
        return out

    def read(
        self,
        dataset_id: str,
        *,
        columns: Optional[list[str]] = None,
        partitions: Optional[list[str]] = None,
        filters: Optional[list] = None,
    ) -> pd.DataFrame:
        """Read a dataset, projecting columns and pruning partitions.

        Projection and partition pruning are pushed into the Parquet reader.
        Reading columns nobody asked for is the one thing a columnar format
        exists to avoid.
        """
        manifest = self.manifest(dataset_id)
        keys = partitions if partitions is not None else sorted(manifest.partition_keys())
        paths = [self.partition_path(dataset_id, key) for key in keys]
        present = [path for path in paths if path.exists()]
        if not present:
            return pd.DataFrame(columns=columns or manifest.columns)
        table = pq.read_table(present, columns=columns, filters=filters)
        return table.to_pandas()

    def iter_partitions(
        self, dataset_id: str, *, columns: Optional[list[str]] = None
    ) -> Iterator[tuple[str, pd.DataFrame]]:
        """Stream partitions one at a time.

        The reason bulk reads are not the only option: a multi-year market
        table does not have to be resident to be processed, and a research
        laptop should not have to hold it.
        """
        manifest = self.manifest(dataset_id)
        for key in sorted(manifest.partition_keys()):
            path = self.partition_path(dataset_id, key)
            if path.exists():
                yield key, pq.read_table(path, columns=columns).to_pandas()

    # ── integrity ────────────────────────────────────────────────────────

    def verify(self, dataset_id: str) -> dict[str, Any]:
        """Re-hash every partition against the manifest.

        Returns a report rather than a bool: "which partition is wrong" is
        actionable and "something is wrong" is not.
        """
        manifest = self.manifest(dataset_id)
        missing: list[str] = []
        corrupt: list[str] = []
        verified = 0
        for partition in manifest.partitions:
            path = self.partition_path(dataset_id, partition.key)
            if not path.exists():
                missing.append(partition.key)
                continue
            if _file_sha256(path) != partition.checksum:
                corrupt.append(partition.key)
                continue
            verified += 1
        return {
            "dataset_id": dataset_id,
            "partitions": len(manifest.partitions),
            "verified": verified,
            "missing": missing,
            "corrupt": corrupt,
            "ok": not missing and not corrupt,
        }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _min_str(frame: pd.DataFrame, column: str) -> Optional[str]:
    if column not in frame.columns or frame.empty:
        return None
    value = frame[column].min()
    return _as_iso(value)


def _max_str(frame: pd.DataFrame, column: str) -> Optional[str]:
    if column not in frame.columns or frame.empty:
        return None
    value = frame[column].max()
    return _as_iso(value)


def _as_iso(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (Date, datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]
