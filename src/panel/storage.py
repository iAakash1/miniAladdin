"""
Panel storage — immutable, content-addressed snapshots on Parquet.

Three properties, each chosen for a reason:

**Immutable.** A snapshot is written once. `write()` refuses an id that
already exists rather than overwriting it. Research results that can be
silently rewritten underneath you are not results; they are opinions with
timestamps.

**Atomic.** A build writes into a staging directory and is promoted by a
single `os.replace`, which is atomic on POSIX. A crashed or killed build
leaves a `.staging-*` directory, never a half-written snapshot that reads
as complete.

**Parquet, not Postgres.** The panel is append-only analytical data read in
columns — the exact workload Parquet exists for. It also happens to be the
format DuckDB reads natively, so the Phase 3 query engine lands on top of
these files with no migration. Postgres keeps what it is good at:
transactional user state.

Layout:

    <root>/
      CURRENT                      text file holding the published id
      snapshots/
        <snapshot_id>/
          manifest.json
          panel.parquet
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import date as Date
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.panel.schema import (
    ALL_COLUMNS,
    PANEL_SCHEMA_VERSION,
    SnapshotManifest,
    panel_arrow_schema,
)

logger = logging.getLogger("omnisignal.panel.storage")

DEFAULT_ROOT = Path("data/panel")
_MANIFEST = "manifest.json"
_PANEL = "panel.parquet"
_CURRENT = "CURRENT"


class SnapshotExistsError(Exception):
    """Raised when a write would overwrite an existing snapshot."""


class SnapshotNotFoundError(Exception):
    """Raised when a requested snapshot is absent."""


class PanelStore:
    """Reads and writes immutable panel snapshots."""

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.snapshots_dir = self.root / "snapshots"

    # ── writing ──────────────────────────────────────────────────────────

    def write(self, frame: pd.DataFrame, manifest: SnapshotManifest) -> SnapshotManifest:
        """Persist a snapshot atomically. Never overwrites.

        Returns the manifest with `content_hash` and `rows` populated from
        the bytes actually written, so the manifest describes the artifact
        rather than the caller's intent.
        """
        if self.exists(manifest.snapshot_id):
            raise SnapshotExistsError(
                f"snapshot {manifest.snapshot_id} already exists — "
                "snapshots are immutable; build with different inputs or delete it explicitly"
            )

        table = self._to_table(frame)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        # Stage beside the target so the promoting rename stays on one
        # filesystem; a cross-device rename is not atomic.
        staging = Path(
            tempfile.mkdtemp(prefix=f".staging-{manifest.snapshot_id}-", dir=self.snapshots_dir)
        )
        try:
            panel_path = staging / _PANEL
            pq.write_table(table, panel_path, compression="zstd", version="2.6")

            complete = manifest.model_copy(
                update={
                    "rows": table.num_rows,
                    "content_hash": _file_sha256(panel_path),
                }
            )
            (staging / _MANIFEST).write_text(
                complete.model_dump_json(indent=2), encoding="utf-8"
            )

            target = self.snapshots_dir / manifest.snapshot_id
            os.replace(staging, target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        logger.info(
            "panel snapshot %s written: %d rows, %d symbols, hash %s",
            complete.snapshot_id,
            complete.rows,
            complete.symbols_built,
            complete.content_hash[:12],
        )
        return complete

    def publish(self, snapshot_id: str) -> None:
        """Point CURRENT at a snapshot. Atomic; readers never see a partial write."""
        if not self.exists(snapshot_id):
            raise SnapshotNotFoundError(snapshot_id)
        self.root.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=self.root, prefix=".current-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(snapshot_id)
            os.replace(tmp, self.root / _CURRENT)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        logger.info("panel CURRENT -> %s", snapshot_id)

    # ── reading ──────────────────────────────────────────────────────────

    def read(self, snapshot_id: Optional[str] = None,
             columns: Optional[list[str]] = None) -> pd.DataFrame:
        """Read a snapshot whole, or the published one when id is omitted.

        `columns` pushes projection into the Parquet reader — the point of a
        columnar format is not reading what you did not ask for.
        """
        resolved = self._resolve(snapshot_id)
        table = pq.read_table(self._panel_path(resolved), columns=columns)
        return table.to_pandas()

    def read_as_of(self, as_of: Date, snapshot_id: Optional[str] = None,
                   columns: Optional[list[str]] = None) -> pd.DataFrame:
        """**The point-in-time read.** Only rows knowable on or before `as_of`.

        This is the single query the schema exists to serve. Any backtest
        or ranking that reads through this method cannot see the future,
        regardless of what the caller intended.
        """
        frame = self.read(snapshot_id, columns=columns)
        if frame.empty:
            return frame
        return frame[frame["as_of"] <= as_of].reset_index(drop=True)

    def manifest(self, snapshot_id: Optional[str] = None) -> SnapshotManifest:
        resolved = self._resolve(snapshot_id)
        raw = (self.snapshots_dir / resolved / _MANIFEST).read_text(encoding="utf-8")
        loaded = SnapshotManifest.model_validate_json(raw)
        if loaded.schema_version != PANEL_SCHEMA_VERSION:
            logger.warning(
                "snapshot %s was written with schema v%d; reader is v%d",
                resolved, loaded.schema_version, PANEL_SCHEMA_VERSION,
            )
        return loaded

    def list_snapshots(self) -> list[SnapshotManifest]:
        """Every snapshot, newest first. Unreadable directories are skipped, loudly."""
        if not self.snapshots_dir.exists():
            return []
        out: list[SnapshotManifest] = []
        for entry in self.snapshots_dir.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            try:
                out.append(self.manifest(entry.name))
            except Exception:  # noqa: BLE001 — one bad snapshot never hides the rest
                logger.exception("unreadable snapshot %s", entry.name)
        return sorted(out, key=lambda m: m.created_at, reverse=True)

    def current(self) -> Optional[str]:
        pointer = self.root / _CURRENT
        if not pointer.exists():
            return None
        value = pointer.read_text(encoding="utf-8").strip()
        return value or None

    def exists(self, snapshot_id: str) -> bool:
        return (self.snapshots_dir / snapshot_id / _PANEL).exists()

    def verify(self, snapshot_id: Optional[str] = None) -> bool:
        """Re-hash the stored bytes and compare against the manifest.

        Detects corruption and tampering. Phase 4's `omni verify` extends
        this to re-deriving the data; this is the integrity half.
        """
        resolved = self._resolve(snapshot_id)
        expected = self.manifest(resolved).content_hash
        actual = _file_sha256(self._panel_path(resolved))
        if actual != expected:
            logger.error(
                "snapshot %s integrity FAILED: manifest %s, actual %s",
                resolved, expected[:12], actual[:12],
            )
            return False
        return True

    # ── internals ────────────────────────────────────────────────────────

    def _resolve(self, snapshot_id: Optional[str]) -> str:
        resolved = snapshot_id or self.current()
        if not resolved:
            raise SnapshotNotFoundError(
                "no snapshot id given and no CURRENT published — run `panel build` first"
            )
        if not self.exists(resolved):
            raise SnapshotNotFoundError(resolved)
        return resolved

    def _panel_path(self, snapshot_id: str) -> Path:
        return self.snapshots_dir / snapshot_id / _PANEL

    @staticmethod
    def _to_table(frame: pd.DataFrame) -> pa.Table:
        """Coerce to the declared schema, sorted for deterministic bytes.

        Sorting matters more than it looks: two builds of identical data must
        produce identical files, or content hashing is worthless. Row order
        out of a dict-keyed build is not guaranteed, so it is imposed here.
        """
        missing = [column for column in ALL_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"panel frame missing required columns: {missing}")

        ordered = frame[list(ALL_COLUMNS)].sort_values(
            ["date", "symbol"], kind="mergesort"
        ).reset_index(drop=True)
        return pa.Table.from_pandas(
            ordered, schema=panel_arrow_schema(), preserve_index=False
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
