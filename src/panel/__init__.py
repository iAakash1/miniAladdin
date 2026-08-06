"""
Point-in-time factor panel.

The panel is the research substrate: for every (symbol, date) in a universe,
the value of every factor the engine computes — recorded with the date on
which that value became KNOWABLE, not merely the date it describes.

That distinction is the whole point. A backtest that uses a factor value
before it was knowable is not a backtest, it is a leak, and the leak is
invisible in the results. The panel makes point-in-time correctness a
property of the storage layer rather than a discipline the caller must
remember.

Public surface:

    PanelBuilder    OHLCV → factor panel, look-ahead impossible by construction
    PanelStore      immutable, content-addressed snapshots on Parquet
    SnapshotManifest  what a snapshot is, and what produced it
    Universe        which symbols a build covers
"""

from src.panel.builder import PanelBuilder
from src.panel.schema import (
    FACTOR_COLUMNS,
    PANEL_SCHEMA_VERSION,
    SnapshotManifest,
    panel_arrow_schema,
)
from src.panel.storage import PanelStore, SnapshotExistsError, SnapshotNotFoundError
from src.panel.universe import Universe

__all__ = [
    "FACTOR_COLUMNS",
    "PANEL_SCHEMA_VERSION",
    "PanelBuilder",
    "PanelStore",
    "SnapshotExistsError",
    "SnapshotManifest",
    "SnapshotNotFoundError",
    "Universe",
    "panel_arrow_schema",
]
