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


def __getattr__(name: str):
    """Lazy public exports keep Arrow/research storage out of the web import.

    Importing ``src.panel.universe`` necessarily initialises this package.
    Eagerly importing every export therefore loaded pandas and PyArrow merely
    to validate a universe name on ``GET /api/factors``. Heavy components are
    resolved only when an offline panel operation actually asks for them.
    """
    if name == "PanelBuilder":
        from src.panel.builder import PanelBuilder
        return PanelBuilder
    if name in {"FACTOR_COLUMNS", "PANEL_SCHEMA_VERSION", "SnapshotManifest", "panel_arrow_schema"}:
        from src.panel import schema
        return getattr(schema, name)
    if name in {"PanelStore", "SnapshotExistsError", "SnapshotNotFoundError"}:
        from src.panel import storage
        return getattr(storage, name)
    if name == "Universe":
        from src.panel.universe import Universe
        return Universe
    raise AttributeError(name)
