"""Build and record the rich PIT panel: a NEW immutable dataset, never an edit of `ds-491d761b9f2a6fc4`."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import rich_panel as R
from src.quant.pit.rich_panel_catalog import CATALOG
from src.quant.pit.sec_foundation import atomic_json, sha256_file
from src.quant.study import exp009b
from src.quant.study.firewall import FIREWALL

PANEL_PATH = Path("data/research/derived/rich_pit_panel.parquet")
MANIFEST_PATH = Path("data/manifests/rich_pit_panel_manifest.json")
CUTOFF = pd.Timestamp("2025-05-09")
FACT_COLUMNS = ["cik", "accession", "form", "accepted_at", "available_session", "fy", "fp", "report_period", "canonical_fact",
                "tag_priority", "qtrs", "unit", "value", "period_end"]


def load_facts(root: Path, ciks: set[int]) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(root / "data/curated/sec_v3/facts-*.parquet"))):
        frame = pd.read_parquet(path, columns=FACT_COLUMNS)
        parts.append(frame[frame["cik"].isin(ciks)])
    return pd.concat(parts, ignore_index=True)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout.strip()


def feature_coverage(panel: pd.DataFrame, columns: list[str], folds: list[dict[str, Any]]) -> dict[str, Any]:
    periods = C.label_periods(panel["date"], folds)
    out = {}
    for column in columns:
        present = panel[column].notna()
        first = panel.loc[present, "date"].min()
        out[column] = {
            "coverage": float(present.mean()), "first_valid_date": None if pd.isna(first) else str(pd.Timestamp(first).date()),
            "by_period": {str(p): float(present[periods == p].mean()) for p in sorted(periods.unique())},
            "by_year": {str(y): float(present[pd.to_datetime(panel["date"]).dt.year == y].mean()) for y in sorted(pd.to_datetime(panel["date"]).dt.year.unique())},
        }
    return out


def missingness_versus_exit(panel: pd.DataFrame, windows: dict[str, Any], sample_column: str = "roa_xs") -> dict[str, Any]:
    """Does a name that stops trading soon have missing fundamentals more often?  (survivorship-through-missingness check)"""
    last = panel["symbol"].map(lambda s: pd.Timestamp(windows[s].last) if s in windows else pd.NaT)
    horizon = pd.to_datetime(panel["date"]) + pd.Timedelta(days=30)
    exits_soon = last.notna() & (last <= horizon) & (last < CUTOFF - pd.Timedelta(days=30))
    present = panel[sample_column].notna()
    trusted = panel["security_id"].notna()
    def share(mask): return float(mask[exits_soon].mean()) if exits_soon.any() else None
    return {
        "rows_exiting_within_30_days": int(exits_soon.sum()),
        "share_present_if_exiting_soon": share(present), "share_present_otherwise": float(present[~exits_soon].mean()),
        "share_identity_trusted_if_exiting_soon": share(trusted), "share_identity_trusted_otherwise": float(trusted[~exits_soon].mean()),
        "reading": "a lower 'present' share for names that exit soon means missingness itself reveals a future delisting",
    }


def build(root: Path) -> dict[str, Any]:
    root = Path(root)
    began = time.perf_counter()
    exp009b.arm_firewall(root)
    master = json.loads((root / "data/manifests/security_master_coverage_v3.json").read_text())
    controls_allowed = bool(master["neutralization_allowed"])
    frame, frozen_manifest = exp009b.load_frame(root)
    frame = frame[frame["in_universe"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    base = frame[["date", "symbol", "close", *R.PASSTHROUGH[:2], *R.LABELS, *R.BASELINE_FEATURES]].copy()
    tables = root / "data/curated/security_master_v3"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    classification = pd.read_parquet(tables / "security_classification_interval.parquet")
    shares = pd.read_parquet(tables / "shares_fact_vintage.parquet")
    trusted_ciks = set(identities.loc[identities["status"].isin(C.TRUSTED_GRADES), "cik"].astype("int64"))
    facts = load_facts(root, trusted_ciks)
    snapshots = F.build_snapshots(facts)
    splits = pd.read_parquet(root / "data/research/raw/dolthub_stocks_split/part-all.parquet")
    panel = R.build_panel(base, identities=identities, classification=classification, shares=shares, snapshots=snapshots,
                          split_table=C.split_factor_table(splits), controls_allowed=controls_allowed)
    out = R.assemble(panel, controls_allowed)
    assert out["date"].max() <= CUTOFF
    out.to_parquet(root / PANEL_PATH, compression="zstd", index=False)  # local; git-ignored under /data/research/
    features = R.feature_columns(controls_allowed)
    columns = ["date", "symbol", "security_id", "cik", "identity_grade", "ff12", "ff17", "ff48", "sic", *R.PASSTHROUGH, *R.LABELS, *features]
    content = R.content_hash(out, columns)
    folds = [f.as_dict() for f in exp009b.recorded_plan(root).folds]
    new_columns = [c for c in features if c not in R.BASELINE_FEATURES]
    coverage = feature_coverage(out, new_columns, folds)
    from src.quant.pit.security_master_build import load_ohlcv, research_universe_symbols
    from src.quant.pit import security_master as M
    ohlcv = load_ohlcv(root)
    windows = M.price_windows(ohlcv[ohlcv["symbol"].isin(set(out["symbol"]))])
    date_str = out["date"]
    manifest = {
        "dataset_id": f"ds-richpit-{content[:16]}", "panel_version": R.PANEL_VERSION, "content_hash": content,
        "rows": int(len(out)), "securities": int(out["security_id"].nunique()), "symbols": int(out["symbol"].nunique()),
        "date_min": str(date_str.min().date()), "date_max": str(date_str.max().date()),
        "feature_count": len(features), "baseline_feature_count": len(R.BASELINE_FEATURES), "new_feature_count": len(new_columns),
        "feature_hash": R.feature_hash(features), "features": features, "new_features": new_columns,
        "targets": list(R.LABELS), "primary_target": "fwd_rank_21",
        "baseline_dataset_id": R.BASELINE_DATASET_ID, "baseline_frozen_content_hash": frozen_manifest["content_hash"],
        "baseline_values_sha256": _baseline_hash(out),
        "controls_allowed": controls_allowed, "controls_withheld": [] if controls_allowed else list(R.CONTROL_FEATURES),
        "controls_gate": {k: master[k] for k in ("security_master_pit", "neutralization_allowed", "size_features_allowed", "failures")},
        "source_manifests": {name: {"sha256": sha256_file(root / "data/manifests" / name)} for name in (
            "sec_archive_verification.json", "sec_fact_coverage_v3.json", "security_master_coverage_v3.json")},
        "sec_version": {"archives": 58, "quarters": "2011q1-2025q2", "tag_map_version": "sec-core-facts-v3",
                        "acceptance_timezone": "America/New_York", "accepted_cutoff": "2025-05-09 23:59:59"},
        "security_master_version": M.SECURITY_MASTER_VERSION, "french_sic_sha256": master["french_sic_sha256"],
        "macro_vintage_status": "BLOCKED_EXTERNAL_FRED_KEY: baseline rates features use the Treasury curve with a one-session lag; no ALFRED vintage series exist",
        "feature_definitions": {name: {"family": R.FAMILY[name], "formula": CATALOG[name][0]} for name in R.NEW_FEATURES if name in CATALOG},
        "coverage": coverage, "missingness_vs_exit": missingness_versus_exit(out, windows),
        "build_commit": _git(root, "rev-parse", "HEAD"), "build_dirty": bool(_git(root, "status", "--porcelain")),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "build_seconds": round(time.perf_counter() - began, 1),
        "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
    }
    atomic_json(root / MANIFEST_PATH, manifest)
    return manifest


def _baseline_hash(panel: pd.DataFrame) -> str:
    import hashlib
    cols = ["date", "symbol", *R.BASELINE_FEATURES]
    ordered = panel[cols].copy()
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.strftime("%Y-%m-%d")
    ordered = ordered.sort_values(["date", "symbol"], kind="mergesort")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()
