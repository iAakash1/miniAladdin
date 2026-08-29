"""
Panel schema — the storage contract for the factor panel.

Two design decisions are encoded here and both are load-bearing.

**Wide, not long.** One row per (symbol, date), one column per factor.
The factor set is closed and known (the engine defines it), every query
wants all factors for a cell, and cross-sectional ranking reads one factor
column across all symbols on a date. A long table would triple the row
count and force a pivot on every read. Long layout is correct only for an
open or sparse factor set; ours is neither.

**Two timestamps, never one.** `date` is the trading day a factor value
describes. `as_of` is the day that value became KNOWABLE. For price-derived
factors these coincide (a close is known at that close). For fundamentals
they diverge by weeks — Q1 revenue describes March and is knowable in May,
when the filing lands. Storing only `date` makes look-ahead bias
unrepresentable in the schema and therefore undetectable in results.

Every point-in-time read is `as_of <= T`. That single predicate is what the
schema exists to make possible.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as Date
from datetime import datetime, timezone
from typing import Any, Optional

import pyarrow as pa
from pydantic import BaseModel, Field

# Bump when the physical layout changes incompatibly. Snapshots record the
# version that wrote them, so a reader can refuse a layout it cannot parse
# rather than silently misinterpreting columns.
PANEL_SCHEMA_VERSION = 2

# Factor columns, in engine order. This tuple IS the contract: adding a
# factor to the engine without adding it here means the panel silently drops
# it, so `test_panel_schema` asserts the two stay in sync.
FACTOR_COLUMNS: tuple[str, ...] = (
    # momentum sleeve
    "r12_1",
    "r63",
    "r21",
    "vol_confirm",
    "high52_prox",
    "rel21_vs_spy",
    # reversal sleeve (single merged component)
    "reversal",
    # fundamental sleeve
    "target_upside",
    "earnings_yield",
    "pe_gap",
    "pead",
    # quality sleeve
    "gross_profitability",
    "net_issuance",
    "asset_growth",
    # news sleeve
    "sentiment",
)

# Identity and provenance columns that accompany every row.
KEY_COLUMNS: tuple[str, ...] = ("symbol", "date", "as_of")
META_COLUMNS: tuple[str, ...] = ("bars", "regimes", "data_completeness")

ALL_COLUMNS: tuple[str, ...] = KEY_COLUMNS + FACTOR_COLUMNS + META_COLUMNS


def panel_arrow_schema() -> pa.Schema:
    """Explicit Arrow schema.

    Declared rather than inferred: inference would silently widen a column
    to float64 on one build and int64 on another depending on whether a
    factor happened to be null, which breaks byte-level snapshot comparison
    — the property `omni verify` will depend on.
    """
    fields: list[pa.Field] = [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("date", pa.date32(), nullable=False),
        pa.field("as_of", pa.date32(), nullable=False),
    ]
    # Factors are nullable by design: a factor whose inputs are absent is
    # ABSENT, never zero. Zero is a value; null is the absence of one, and
    # conflating them would let missing data masquerade as a neutral signal.
    fields += [pa.field(name, pa.float64(), nullable=True) for name in FACTOR_COLUMNS]
    fields += [
        pa.field("bars", pa.int32(), nullable=False),
        pa.field("regimes", pa.string(), nullable=False),
        pa.field("data_completeness", pa.float64(), nullable=False),
    ]
    return pa.schema(fields)


class SnapshotManifest(BaseModel):
    """What a snapshot is, and what produced it.

    Written beside every snapshot and never mutated. This is deliberately
    the shape a reproducibility check needs: `omni verify` (Phase 4) will
    rebuild from these inputs and compare `content_hash`.
    """

    snapshot_id: str
    schema_version: int = PANEL_SCHEMA_VERSION

    # Inputs — everything required to reproduce the build.
    universe: str
    symbols: list[str]
    start: Date
    end: Date
    engine_version: str
    step: int = Field(default=1, ge=1)
    lookback: int = Field(default=2520, ge=1)
    benchmark: str = "SPY"
    fundamentals: bool = True
    vectorized: bool = True
    git_commit: str = "unknown"
    source_versions: dict[str, str] = Field(default_factory=dict)
    raw_data_hashes: dict[str, str] = Field(default_factory=dict)
    reproducibility_status: str = "partial"

    # Outputs — what the build produced.
    rows: int
    symbols_built: int
    symbols_skipped: list[str] = Field(default_factory=list)
    content_hash: str

    # Provenance.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    build_seconds: float = 0.0
    notes: str = ""

    def input_hash(self) -> str:
        """Hash of the build's *inputs* only.

        Two builds sharing an input hash should produce an identical
        content hash. When they do not, either the engine changed or the
        upstream data was revised — and the panel can say which.
        """
        payload = {
            "universe": self.universe,
            "symbols": sorted(self.symbols),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "engine_version": self.engine_version,
            "step": self.step,
            "lookback": self.lookback,
            "benchmark": self.benchmark,
            "fundamentals": self.fundamentals,
            "vectorized": self.vectorized,
            "git_commit": self.git_commit,
            "source_versions": self.source_versions,
            "raw_data_hashes": self.raw_data_hashes,
            "reproducibility_status": self.reproducibility_status,
            "schema_version": self.schema_version,
            "factors": list(FACTOR_COLUMNS),
        }
        return _sha256_json(payload)


def compute_snapshot_id(
    universe: str,
    symbols: list[str],
    start: Date,
    end: Date,
    engine_version: str,
    *,
    step: int = 1,
    lookback: int = 2520,
    benchmark: str = "SPY",
    fundamentals: bool = True,
    vectorized: bool = True,
    git_commit: str = "unknown",
    source_versions: Optional[dict[str, str]] = None,
    raw_data_hashes: Optional[dict[str, str]] = None,
) -> str:
    """Deterministic, content-addressed identifier for a build.

    Derived from inputs alone, so requesting the same build twice targets
    the same id — which is how the store detects and refuses an accidental
    rebuild over an existing snapshot.
    """
    payload = {
        "universe": universe,
        "symbols": sorted(symbols),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "engine_version": engine_version,
        "step": step,
        "lookback": lookback,
        "benchmark": benchmark,
        "fundamentals": fundamentals,
        "vectorized": vectorized,
        "git_commit": git_commit,
        "source_versions": source_versions or {},
        "raw_data_hashes": raw_data_hashes or {},
        "schema_version": PANEL_SCHEMA_VERSION,
        "factors": list(FACTOR_COLUMNS),
    }
    return _sha256_json(payload)[:16]


def _sha256_json(payload: dict[str, Any]) -> str:
    """Stable hash of a JSON-serializable payload.

    `sort_keys` and a fixed separator make the digest independent of dict
    ordering and of json's default whitespace, both of which vary across
    Python versions.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def engine_version() -> str:
    """The scoring engine's own version marker.

    Read from the engine rather than duplicated, so a model change is
    reflected in every snapshot id without a second place to update.
    """
    from src.scoring.engine import ScoreCard

    field = ScoreCard.model_fields["model_version"]
    default: Optional[str] = field.default
    return default or "unknown"
