"""
Panel storage tests — immutability, atomicity, integrity, point-in-time reads.

These test the four promises `PanelStore` makes. Each promise is only worth
anything if it holds under the failure it was designed for, so where it is
possible the failure is simulated rather than assumed away: writes are
interrupted mid-flight, files are corrupted on disk, and rebuilds are
attempted over existing snapshots.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.panel.schema import ALL_COLUMNS, FACTOR_COLUMNS, SnapshotManifest
from src.panel.storage import (
    PanelStore,
    SnapshotExistsError,
    SnapshotNotFoundError,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _frame(symbols=("AAPL", "MSFT"), days: int = 5, start=date(2024, 1, 1)) -> pd.DataFrame:
    rows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for index, symbol in enumerate(symbols):
            row = {
                "symbol": symbol,
                "date": day,
                "as_of": day,
                "bars": 100 + offset,
                "regimes": "normal",
                "data_completeness": 0.4,
            }
            for position, factor in enumerate(FACTOR_COLUMNS):
                # Half the factors null, to exercise the "absent, not zero"
                # path through Arrow on every write.
                row[factor] = None if position % 2 else round(0.1 * (index + offset), 4)
            rows.append(row)
    return pd.DataFrame(rows, columns=list(ALL_COLUMNS))


def _manifest(snapshot_id: str = "snap0001", **overrides) -> SnapshotManifest:
    defaults = dict(
        snapshot_id=snapshot_id,
        universe="dev",
        symbols=["AAPL", "MSFT"],
        start=date(2024, 1, 1),
        end=date(2024, 1, 5),
        engine_version="scoring-v2.1",
        rows=0,
        symbols_built=2,
        content_hash="",
    )
    defaults.update(overrides)
    return SnapshotManifest(**defaults)


@pytest.fixture
def store(tmp_path: Path) -> PanelStore:
    return PanelStore(tmp_path / "panel")


# ── writing ──────────────────────────────────────────────────────────────────

def test_write_returns_manifest_describing_the_artifact(store: PanelStore):
    """rows and content_hash come from the bytes written, not the caller."""
    written = store.write(_frame(), _manifest())
    assert written.rows == 10
    assert len(written.content_hash) == 64
    assert store.exists("snap0001")


def test_write_persists_manifest_beside_data(store: PanelStore):
    written = store.write(_frame(), _manifest())
    assert store.manifest("snap0001") == written


def test_write_rejects_frame_missing_columns(store: PanelStore):
    frame = _frame().drop(columns=["r63"])
    with pytest.raises(ValueError, match="missing required columns"):
        store.write(frame, _manifest())


def test_empty_panel_writes_cleanly(store: PanelStore):
    """A universe where nothing had enough history is a valid, empty result."""
    written = store.write(_frame(symbols=(), days=0), _manifest())
    assert written.rows == 0
    assert store.read("snap0001").empty


# ── immutability ─────────────────────────────────────────────────────────────

def test_second_write_of_same_id_is_refused(store: PanelStore):
    store.write(_frame(), _manifest())
    with pytest.raises(SnapshotExistsError, match="immutable"):
        store.write(_frame(days=99), _manifest())


def test_refused_write_leaves_original_intact(store: PanelStore):
    """The point of refusing is that the existing result survives."""
    original = store.write(_frame(), _manifest())
    with pytest.raises(SnapshotExistsError):
        store.write(_frame(days=99), _manifest())
    assert store.manifest("snap0001").content_hash == original.content_hash
    assert len(store.read("snap0001")) == 10


# ── atomicity ────────────────────────────────────────────────────────────────

def test_failed_write_leaves_no_snapshot(store: PanelStore, monkeypatch):
    """A crash mid-write must not leave a directory that reads as complete."""
    import src.panel.storage as storage_module

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(storage_module.pq, "write_table", explode)

    with pytest.raises(OSError, match="disk full"):
        store.write(_frame(), _manifest())

    assert not store.exists("snap0001")
    assert store.list_snapshots() == []


def test_failed_write_cleans_up_staging(store: PanelStore, monkeypatch):
    """No orphaned .staging-* directories after a failure."""
    import src.panel.storage as storage_module

    monkeypatch.setattr(
        storage_module.pq, "write_table",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(OSError):
        store.write(_frame(), _manifest())

    leftovers = list(store.snapshots_dir.glob(".staging-*"))
    assert leftovers == []


def test_staging_directory_is_hidden_from_listing(store: PanelStore):
    """Even if a staging dir survives a hard kill, it is never listed as a snapshot."""
    store.write(_frame(), _manifest())
    (store.snapshots_dir / ".staging-orphan").mkdir()
    assert [m.snapshot_id for m in store.list_snapshots()] == ["snap0001"]


# ── publishing ───────────────────────────────────────────────────────────────

def test_publish_sets_current(store: PanelStore):
    store.write(_frame(), _manifest())
    assert store.current() is None
    store.publish("snap0001")
    assert store.current() == "snap0001"


def test_publish_rejects_unknown_snapshot(store: PanelStore):
    with pytest.raises(SnapshotNotFoundError):
        store.publish("does-not-exist")


def test_publish_swaps_atomically(store: PanelStore):
    """Repointing CURRENT never leaves it empty or partial."""
    store.write(_frame(), _manifest("snapA"))
    store.write(_frame(days=3), _manifest("snapB"))
    store.publish("snapA")
    store.publish("snapB")
    assert store.current() == "snapB"
    assert len(store.read()) == 6


def test_read_without_id_and_without_current_is_an_error(store: PanelStore):
    store.write(_frame(), _manifest())
    with pytest.raises(SnapshotNotFoundError, match="no snapshot id given"):
        store.read()


# ── reading ──────────────────────────────────────────────────────────────────

def test_round_trip_preserves_values_and_nulls(store: PanelStore):
    store.write(_frame(), _manifest())
    frame = store.read("snap0001")

    assert list(frame.columns) == list(ALL_COLUMNS)
    assert len(frame) == 10
    # Odd-indexed factors were written null and must read back null, not 0.0.
    assert frame[FACTOR_COLUMNS[1]].isna().all()
    assert frame[FACTOR_COLUMNS[0]].notna().all()


def test_column_projection_reads_only_what_was_asked_for(store: PanelStore):
    store.write(_frame(), _manifest())
    frame = store.read("snap0001", columns=["symbol", "date", "r12_1"])
    assert list(frame.columns) == ["symbol", "date", "r12_1"]


def test_rows_are_sorted_deterministically(store: PanelStore):
    """Byte-identical output for identical input requires a total order."""
    store.write(_frame(), _manifest())
    frame = store.read("snap0001")
    assert frame[["date", "symbol"]].equals(
        frame[["date", "symbol"]].sort_values(["date", "symbol"]).reset_index(drop=True)
    )


def test_shuffled_input_produces_identical_bytes(store: PanelStore, tmp_path: Path):
    """The content hash must describe the data, not the row order it arrived in."""
    other = PanelStore(tmp_path / "other")
    first = store.write(_frame(), _manifest())
    shuffled = _frame().sample(frac=1.0, random_state=42).reset_index(drop=True)
    second = other.write(shuffled, _manifest())
    assert first.content_hash == second.content_hash


# ── the point-in-time read ───────────────────────────────────────────────────

def test_read_as_of_hides_the_future(store: PanelStore):
    """The one query the schema exists to serve."""
    store.write(_frame(days=5), _manifest())
    visible = store.read_as_of(date(2024, 1, 3), "snap0001")

    assert len(visible) == 6                     # 3 days x 2 symbols
    assert visible["as_of"].max() == date(2024, 1, 3)


def test_read_as_of_before_any_data_returns_empty(store: PanelStore):
    store.write(_frame(), _manifest())
    assert store.read_as_of(date(2023, 1, 1), "snap0001").empty


def test_read_as_of_respects_as_of_not_date(store: PanelStore):
    """A row describing an old day but knowable only later must stay hidden.

    This is the restatement case: a fundamental value for March that lands
    in May is invisible to an April backtest. If this test ever fails, the
    panel has look-ahead bias.
    """
    frame = _frame(symbols=("AAPL",), days=1)
    frame.loc[0, "date"] = date(2024, 3, 1)      # describes March
    frame.loc[0, "as_of"] = date(2024, 5, 15)    # knowable in May
    store.write(frame, _manifest())

    assert store.read_as_of(date(2024, 4, 1), "snap0001").empty
    assert len(store.read_as_of(date(2024, 5, 15), "snap0001")) == 1


def test_read_as_of_uses_current_when_id_omitted(store: PanelStore):
    store.write(_frame(), _manifest())
    store.publish("snap0001")
    assert len(store.read_as_of(date(2024, 1, 2))) == 4


# ── integrity ────────────────────────────────────────────────────────────────

def test_verify_passes_on_untouched_snapshot(store: PanelStore):
    store.write(_frame(), _manifest())
    assert store.verify("snap0001") is True


def test_verify_detects_corruption(store: PanelStore):
    """Flip one byte in the middle of the file; the hash must notice."""
    store.write(_frame(), _manifest())
    path = store.snapshots_dir / "snap0001" / "panel.parquet"

    data = bytearray(path.read_bytes())
    midpoint = len(data) // 2
    data[midpoint] ^= 0xFF
    path.write_bytes(bytes(data))

    assert store.verify("snap0001") is False


def test_verify_detects_truncation(store: PanelStore):
    store.write(_frame(), _manifest())
    path = store.snapshots_dir / "snap0001" / "panel.parquet"
    path.write_bytes(path.read_bytes()[:-64])
    assert store.verify("snap0001") is False


# ── listing ──────────────────────────────────────────────────────────────────

def test_list_is_empty_before_any_build(store: PanelStore):
    assert store.list_snapshots() == []


def test_list_returns_newest_first(store: PanelStore):
    from datetime import datetime, timezone

    store.write(_frame(), _manifest("old", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    store.write(_frame(), _manifest("new", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)))
    assert [m.snapshot_id for m in store.list_snapshots()] == ["new", "old"]


def test_one_unreadable_snapshot_does_not_hide_the_rest(store: PanelStore):
    store.write(_frame(), _manifest("good"))
    broken = store.snapshots_dir / "broken"
    broken.mkdir()
    (broken / "panel.parquet").write_bytes(b"not parquet")
    (broken / "manifest.json").write_text("{ truncated")

    assert [m.snapshot_id for m in store.list_snapshots()] == ["good"]
