"""
Panel schema tests.

The important test in this file is `test_factor_columns_match_engine`. Every
other assertion here protects a property; that one protects a *contract*
between two modules that have no compile-time link. Add a factor to the
engine and forget the panel, and the panel silently stops storing it —
no error, no warning, just a column of nulls nobody notices for a month.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from src.panel.schema import (
    ALL_COLUMNS,
    FACTOR_COLUMNS,
    KEY_COLUMNS,
    META_COLUMNS,
    PANEL_SCHEMA_VERSION,
    SnapshotManifest,
    compute_snapshot_id,
    engine_version,
    panel_arrow_schema,
)
from src.scoring.engine import (
    fundamental_factors,
    momentum_factors,
    news_factor,
    quality_factors,
    reversal_factor,
)


def _synthetic_frame(days: int = 400, seed: int = 7) -> pd.DataFrame:
    """Enough history, with volume, to trigger every price-derived factor."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2022-01-03", periods=days)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, days)))
    return pd.DataFrame(
        {
            "Open": closes * 0.998,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": rng.integers(1_000_000, 5_000_000, days).astype(float),
        },
        index=index,
    )


def _all_engine_factor_names() -> set[str]:
    """Every factor the engine can emit, obtained by actually emitting them.

    Deliberately behavioural rather than a hard-coded list — a hard-coded
    list would need updating in the same commit that breaks the contract,
    which is exactly the commit that will forget.
    """
    frame = _synthetic_frame()
    benchmark = _synthetic_frame(seed=11)

    rows = []
    rows += momentum_factors(frame, benchmark)
    rows += reversal_factor(frame)
    rows += fundamental_factors(
        price=100.0,
        pe_ratio=18.0,
        forward_pe=16.0,
        analyst_target=120.0,
        analyst_count=12,
        earnings_surprise_pct=4.5,
        days_since_earnings=10,
    )
    rows += quality_factors(
        gross_profit_over_assets=0.35,
        net_issuance_yoy=-0.02,
        asset_growth_yoy=0.08,
    )
    rows += news_factor(effective_sentiment=0.3, effective_count=25.0)
    return {row.name for row in rows}


# ── the contract ─────────────────────────────────────────────────────────────

def test_factor_columns_match_engine():
    """The panel stores exactly the factors the engine produces.

    A mismatch in either direction is a bug:
      - engine ⊄ panel: the panel silently drops a factor.
      - panel ⊄ engine: the panel writes a column nothing can ever fill.
    """
    engine_names = _all_engine_factor_names()
    panel_names = set(FACTOR_COLUMNS)

    assert engine_names == panel_names, (
        f"factor contract drift.\n"
        f"  in engine, missing from panel: {sorted(engine_names - panel_names)}\n"
        f"  in panel, unknown to engine:   {sorted(panel_names - engine_names)}\n"
        f"Update FACTOR_COLUMNS in src/panel/schema.py and bump "
        f"PANEL_SCHEMA_VERSION if the layout changed."
    )


def test_factor_count_is_fifteen():
    """The documented engine is '15 factors, 5 sleeves' (CLAUDE.md)."""
    assert len(FACTOR_COLUMNS) == 15


# ── column layout ────────────────────────────────────────────────────────────

def test_all_columns_is_keys_factors_meta_in_order():
    assert ALL_COLUMNS == KEY_COLUMNS + FACTOR_COLUMNS + META_COLUMNS


def test_no_duplicate_columns():
    assert len(set(ALL_COLUMNS)) == len(ALL_COLUMNS)


def test_two_timestamps_present():
    """`date` and `as_of` are the reason this schema exists."""
    assert "date" in KEY_COLUMNS
    assert "as_of" in KEY_COLUMNS


# ── arrow schema ─────────────────────────────────────────────────────────────

def test_arrow_schema_covers_every_column_in_order():
    schema = panel_arrow_schema()
    assert schema.names == list(ALL_COLUMNS)


def test_factors_are_nullable_keys_are_not():
    """Absent is not zero. Keys, by contrast, may never be absent."""
    schema = panel_arrow_schema()
    for name in FACTOR_COLUMNS:
        assert schema.field(name).nullable, f"{name} must be nullable"
        assert schema.field(name).type == pa.float64()
    for name in KEY_COLUMNS:
        assert not schema.field(name).nullable, f"{name} must not be nullable"


def test_dates_are_date32_not_timestamp():
    """A trading day is a day. Storing it as a timestamp invites timezone bugs."""
    schema = panel_arrow_schema()
    assert schema.field("date").type == pa.date32()
    assert schema.field("as_of").type == pa.date32()


# ── snapshot identity ────────────────────────────────────────────────────────

def test_snapshot_id_is_deterministic():
    args = ("dev", ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 6, 30), "scoring-v2.1")
    assert compute_snapshot_id(*args) == compute_snapshot_id(*args)


def test_snapshot_id_ignores_symbol_order():
    """Universe membership is a set; its serialization order must not leak in."""
    a = compute_snapshot_id("dev", ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 6, 30), "v1")
    b = compute_snapshot_id("dev", ["MSFT", "AAPL"], date(2024, 1, 1), date(2024, 6, 30), "v1")
    assert a == b


@pytest.mark.parametrize(
    "universe,symbols,start,end,version",
    [
        ("prod", ["AAPL"], date(2024, 1, 1), date(2024, 6, 30), "scoring-v2.1"),
        ("dev", ["AAPL", "NVDA"], date(2024, 1, 1), date(2024, 6, 30), "scoring-v2.1"),
        ("dev", ["AAPL"], date(2023, 1, 1), date(2024, 6, 30), "scoring-v2.1"),
        ("dev", ["AAPL"], date(2024, 1, 1), date(2024, 7, 31), "scoring-v2.1"),
        ("dev", ["AAPL"], date(2024, 1, 1), date(2024, 6, 30), "scoring-v3.0"),
    ],
)
def test_snapshot_id_changes_with_every_input(universe, symbols, start, end, version):
    """Any input change must produce a new id, or a rebuild would collide."""
    baseline = compute_snapshot_id(
        "dev", ["AAPL"], date(2024, 1, 1), date(2024, 6, 30), "scoring-v2.1"
    )
    assert compute_snapshot_id(universe, symbols, start, end, version) != baseline


def test_snapshot_id_is_short_and_hex():
    value = compute_snapshot_id("dev", ["AAPL"], date(2024, 1, 1), date(2024, 6, 30), "v1")
    assert len(value) == 16
    assert all(character in "0123456789abcdef" for character in value)


@pytest.mark.parametrize(
    "changed",
    [
        {"step": 5},
        {"lookback": 1260},
        {"benchmark": "QQQ"},
        {"fundamentals": False},
        {"vectorized": False},
        {"git_commit": "abc123"},
        {"source_versions": {"market_data": "vendor-v2"}},
        {"raw_data_hashes": {"price:AAPL": "deadbeef"}},
    ],
)
def test_snapshot_id_tracks_quant_build_inputs(changed):
    args = ("dev", ["AAPL"], date(2024, 1, 1), date(2024, 6, 30), "v1")
    assert compute_snapshot_id(*args, **changed) != compute_snapshot_id(*args)


# ── manifest ─────────────────────────────────────────────────────────────────

def _manifest(**overrides) -> SnapshotManifest:
    defaults = dict(
        snapshot_id="abc123",
        universe="dev",
        symbols=["AAPL", "MSFT"],
        start=date(2024, 1, 1),
        end=date(2024, 6, 30),
        engine_version="scoring-v2.1",
        rows=100,
        symbols_built=2,
        content_hash="deadbeef",
    )
    defaults.update(overrides)
    return SnapshotManifest(**defaults)


def test_manifest_records_schema_version():
    assert _manifest().schema_version == PANEL_SCHEMA_VERSION


def test_manifest_round_trips_through_json():
    original = _manifest()
    restored = SnapshotManifest.model_validate_json(original.model_dump_json())
    assert restored == original


def test_input_hash_ignores_outputs():
    """Two builds of the same inputs share an input hash even if outputs differ.

    That is what makes the hash useful: when input hashes match but content
    hashes do not, the upstream data was revised.
    """
    assert _manifest(rows=100, content_hash="aaa").input_hash() == _manifest(
        rows=999, content_hash="bbb"
    ).input_hash()


def test_input_hash_tracks_inputs():
    assert _manifest().input_hash() != _manifest(engine_version="scoring-v3.0").input_hash()


def test_input_hash_tracks_source_and_build_configuration():
    base = _manifest()
    for changed in (
        {"step": 5},
        {"lookback": 1260},
        {"benchmark": "QQQ"},
        {"fundamentals": False},
        {"vectorized": False},
        {"git_commit": "abc123"},
        {"source_versions": {"prices": "v2"}},
        {"raw_data_hashes": {"price:AAPL": "deadbeef"}},
    ):
        assert base.input_hash() != _manifest(**changed).input_hash()


def test_engine_version_is_read_from_the_engine():
    """Not duplicated — a model bump must reach snapshot ids automatically."""
    from src.scoring.engine import ScoreCard

    assert engine_version() == ScoreCard.model_fields["model_version"].default
    assert engine_version().startswith("scoring-")
