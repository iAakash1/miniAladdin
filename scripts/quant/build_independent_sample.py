"""Build an independent firm sample for the follow-up to EXP-012/013: names ranked 251 to 1,000 by liquidity.

EXP-012/013 used the 250 most liquid US names per month. The amendment signal they found rests on about 60 firms. A test on different firms needs a different universe: here, the next 750 names
by the same rule (non-ETF, non-test issue, close >= 5, trailing 3-month median dollar volume, membership read from each month's whole-market cross-section, so delisted names are present in the
months they were liquid). Membership at each month-end is the size-1,000 universe minus the size-250 universe of the same month; the size-250 rebuild is checked against the frozen universe file.

Everything is read from the local Dolt clone (`datasets/stocks`, `datasets/rates`) through the repository's own ingestion code and written to a NEW store, `data/research_mid/`, with immutable
partitions, checksums and the clone's commit hash in every manifest. No existing store is modified. **Prices are capped at 2025-06-30**: the sealed holdout starts 2025-08-26, and nothing at or
after it is ever written to the new store.

Stages (each resumable and idempotent):

    python -m scripts.quant.build_independent_sample universe
    python -m scripts.quant.build_independent_sample ingest
    python -m scripts.quant.build_independent_sample baseline --workers 6

The `baseline` stage builds the 26-feature baseline frame and the labels with the same `DatasetBuilder` that built the frozen frame, from 2014-04-01 (the first date with split coverage) to
2025-05-09. No relationship between a feature and a label is computed anywhere in this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import date as Date
from pathlib import Path

import pandas as pd

from src.quant.datasets import catalog
from src.quant.datasets.local_dolt import LocalDoltClient
from src.quant.datasets.local_ingest import ingest_by_year_local, ingest_whole_table_local, repository_commit
from src.quant.datasets.store import DatasetManifest, RawStore
from src.quant.pit.universe import UniverseHistory, UniverseSnapshot, build_pit_universe

SOURCE = Path("data/research")
TARGET = Path("data/research_mid")
MANIFESTS = Path("data/manifests")
CAP = Date(2025, 6, 30)                 # nothing later is ever written to the new store
FIRST_DECISION = Date(2014, 4, 1)
LAST_DECISION = Date(2025, 5, 9)
HOLDOUT_START = Date(2025, 8, 26)
UNIVERSE_NAME = "mid"
logger = logging.getLogger("build_independent_sample")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def stage_universe() -> dict:
    assert CAP < HOLDOUT_START
    source = RawStore(SOURCE)
    big = build_pit_universe(source, size=1000, name="liquid1000")
    small = build_pit_universe(source, size=250, name="liquid250_rebuilt")
    frozen = UniverseHistory.load(SOURCE / "universe")
    frozen_by_date = {s.as_of: s.symbols for s in frozen.snapshots}
    checked = mismatched = 0
    for snap in small.snapshots:
        if snap.as_of > CAP or snap.as_of not in frozen_by_date:
            continue
        checked += 1
        mismatched += int(frozen_by_date[snap.as_of] != snap.symbols)
    if mismatched:
        raise RuntimeError(f"the size-250 rebuild disagrees with the frozen universe file on {mismatched} of {checked} snapshots; not proceeding")
    small_by_date = {s.as_of: set(s.symbols) for s in small.snapshots}
    mid = []
    for snap in big.snapshots:
        if snap.as_of > CAP or snap.as_of not in small_by_date:
            continue
        members = tuple(sorted(set(snap.symbols) - small_by_date[snap.as_of]))
        mid.append(UniverseSnapshot(as_of=snap.as_of, symbols=members, candidates=snap.candidates, dropped_etf=snap.dropped_etf, dropped_price=snap.dropped_price,
                                    dropped_delisted=snap.dropped_delisted, min_dollar_volume=snap.min_dollar_volume, coverage_class=snap.coverage_class))
    history = UniverseHistory(name=UNIVERSE_NAME, size=750, snapshots=mid, built_from=big.built_from + " (ranks 251-1000)", notes=[
        "Liquidity ranks 251 to 1,000 by 3-month trailing-median dollar volume; membership = size-1,000 universe minus size-250 universe of the same month.",
        "Not index membership. Survivorship-free by construction (selected from each month's whole-market cross-section). Same screens as the frozen universe: non-ETF, non-test issue, close >= 5.",
        "Snapshots after 2025-06-30 are not built: the sealed holdout starts 2025-08-26.", *big.notes[3:]])
    path = history.save(TARGET / "universe")
    sizes = [len(s.symbols) for s in mid]
    summary = history.summary()
    summary.update({"snapshots_checked_against_frozen_size_250": checked, "mismatches": mismatched, "members_per_snapshot": {"min": min(sizes), "median": sorted(sizes)[len(sizes) // 2], "max": max(sizes)},
                    "overlap_with_frozen_universe_ever": len(set(history.all_members()) & set(frozen.all_members())), "file": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    summary.pop("notes", None)
    _write_json(MANIFESTS / "mid_sample_universe.json", summary)
    return summary


def _copy_dataset(dataset_id: str, *, cap: Date, date_column: str = "date") -> dict:
    """Copy a whole-market dataset from the existing store, truncated to `cap`, as new immutable partitions."""
    source, target = RawStore(SOURCE), RawStore(TARGET)
    original = source.manifest(dataset_id)
    frame = source.read(dataset_id)
    frame = frame[pd.to_datetime(frame[date_column]).dt.date <= cap]
    records, years = [], sorted(pd.to_datetime(frame[date_column]).dt.year.unique())
    for year in years:
        key = str(year)
        part = frame[pd.to_datetime(frame[date_column]).dt.year == year]
        if not target.has_partition(dataset_id, key):
            records.append(target.write_partition(dataset_id, key, part))
        else:
            records.extend(p for p in target.manifest(dataset_id).partitions if p.key == key)
    manifest = DatasetManifest(dataset_id=dataset_id, source=original.source, repository=original.repository, table=original.table, source_version=original.source_version, columns=list(frame.columns),
                               partitions=records, point_in_time_status=original.point_in_time_status, point_in_time_note=original.point_in_time_note,
                               survivorship_status=original.survivorship_status, survivorship_note=original.survivorship_note, licence=original.licence,
                               transformations=[*original.transformations, f"copied from data/research and truncated to {cap}"], notes=list(original.notes))
    target.write_manifest(manifest)
    return {"dataset_id": dataset_id, "rows": int(len(frame)), "max_date": str(frame[date_column].max())}


def stage_ingest() -> dict:
    target = RawStore(TARGET)
    history = UniverseHistory.load(TARGET / "universe", name=UNIVERSE_NAME)
    symbols = history.all_members()
    client = LocalDoltClient()
    cap = CAP.isoformat()
    report = {"clone_commits": {r: repository_commit(client, r) for r in ("stocks", "rates")}, "universe_symbols": len(symbols), "cap": cap}
    r = ingest_by_year_local(catalog.STOCKS_OHLCV, target, start_year=2011, end_year=CAP.year, client=client, symbols=symbols, where=f"`date` <= '{cap}'")
    report["ohlcv"] = {"partitions_written": r.partitions_written, "skipped": r.partitions_skipped, "rows": r.rows}
    # The symbol table is deliberately NOT copied: its `date` column holds listing snapshots up to 2026-08-22, inside the sealed holdout window. The mid security master reads the three name columns it needs
    # from the frozen store's copy of the same table, restricted to snapshots on or before the research cutoff (scripts/quant/build_mid_security_master.py).
    for spec, where in ((catalog.STOCKS_DIVIDEND, f"`ex_date` <= '{cap}'"), (catalog.STOCKS_SPLIT, f"`ex_date` <= '{cap}'"), (catalog.RATES_TREASURY, f"`date` <= '{cap}'")):
        r = ingest_whole_table_local(spec, target, client=client, where=where)
        report[spec.dataset_id] = {"rows": r.rows, "skipped": r.partitions_skipped}
    report["monthly"] = _copy_dataset("dolthub_stocks_ohlcv_monthly", cap=CAP)
    # verify the new store: checksums, and that nothing at or after the holdout start was written
    verification = {}
    for manifest in target.list_datasets():
        verdict = target.verify(manifest.dataset_id)
        verification[manifest.dataset_id] = {k: verdict[k] for k in verdict if k in ("ok", "partitions", "rows", "problems")}
        if manifest.max_date and manifest.max_date >= HOLDOUT_START.isoformat():
            raise RuntimeError(f"{manifest.dataset_id} reaches {manifest.max_date}, inside the sealed holdout window")
    report["verification"] = verification
    _write_json(MANIFESTS / "mid_sample_ingest.json", report)
    return report


def stage_baseline(workers: int) -> dict:
    from src.quant.pit.dataset import DatasetBuilder

    store = RawStore(TARGET)
    history = UniverseHistory.load(TARGET / "universe", name=UNIVERSE_NAME)
    dataset = DatasetBuilder(store, history).build(start=FIRST_DECISION, end=LAST_DECISION, step_sessions=5, workers=workers)
    out = TARGET / "derived" / "mid_baseline_frame.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    dataset.frame.to_parquet(out, compression="zstd")
    manifest = dataset.manifest.as_dict()
    frame = dataset.frame
    dates = pd.to_datetime(frame["date"])
    if dates.max() > pd.Timestamp(LAST_DECISION):
        raise RuntimeError("the baseline frame extends past the registered last decision date")
    summary = {"frame": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "rows": int(len(frame)), "symbols": int(frame["symbol"].nunique()), "dates": int(dates.nunique()),
               "date_min": str(dates.min().date()), "date_max": str(dates.max().date()), "in_universe_rows": int(frame["in_universe"].sum()) if "in_universe" in frame.columns else None,
               "columns": list(frame.columns), "builder_manifest": manifest}
    _write_json(MANIFESTS / "mid_sample_baseline.json", summary)
    return {k: v for k, v in summary.items() if k not in ("columns", "builder_manifest")}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["universe", "ingest", "baseline"])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    result = {"universe": stage_universe, "ingest": stage_ingest, "baseline": lambda: stage_baseline(args.workers)}[args.stage]()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
