"""Build and record rich PIT v2 (outcome-blind: coverage and data-quality statistics only)."""

from __future__ import annotations

import glob
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import pit_coverage_v4 as C4
from src.quant.pit import rich_panel as R
from src.quant.pit import rich_panel_v2 as V2
from src.quant.pit import security_master as M
from src.quant.pit import security_master_v4 as V4
from src.quant.pit.rich_panel_build import load_facts
from src.quant.pit.sec_foundation import atomic_json, sha256_file
from src.quant.pit.security_master_build import load_ohlcv
from src.quant.study import exp009b

PANEL_PATH = Path("data/research/derived/rich_pit_v2_panel.parquet")
MANIFEST_PATH = Path("data/manifests/rich_pit_v2_manifest.json")
FOREIGN_FACT_COLUMNS = ["cik", "accession", "form", "accepted_at", "available_session", "fy", "fp", "report_period", "canonical_fact",
                        "tag_priority", "qtrs", "unit", "value", "period_end"]
META_V2 = ("security_id", "cik", "identity_grade", "ff12", "ff17", "ff48", "sic")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout.strip()


def load_foreign_facts(root: Path, ciks: set[int]) -> pd.DataFrame:
    parts = []
    for path in sorted(glob.glob(str(root / "data/curated/sec_v4_foreign/facts-*.parquet"))):
        frame = pd.read_parquet(path, columns=FOREIGN_FACT_COLUMNS)
        parts.append(frame[frame["cik"].isin(ciks) & (frame["fp"] == "FY")])
    return pd.concat(parts, ignore_index=True)


def incremental_coverage(panel: pd.DataFrame, columns: list[str], folds: list[dict[str, Any]], regimes: pd.Series,
                         exiting: pd.Series) -> dict[str, Any]:
    """Coverage of each incremental column: overall, by year, by fold, by identity grade, by filer regime, exiting or not, and share-tier dependence."""
    periods = C.label_periods(panel["date"], folds)
    years = pd.to_datetime(panel["date"]).dt.year
    regime = panel["v2_cik"].map(regimes).fillna("UNRESOLVED")
    grade = panel["v2_identity_grade"].fillna("NONE")
    basis = panel["_shares_basis"].fillna("NONE")
    out = {}
    for column in columns:
        present = panel[column].notna()
        out[column] = {
            "overall": float(present.mean()), "first_valid_date": None if not present.any() else str(pd.Timestamp(panel.loc[present, "date"].min()).date()),
            "by_year": {str(y): float(present[years == y].mean()) for y in sorted(years.unique())},
            "by_period": {str(p): float(present[periods == p].mean()) for p in sorted(periods.unique())},
            "by_identity_grade": {str(g): float(present[grade == g].mean()) for g in sorted(grade.unique())},
            "by_filer_regime": {str(g): float(present[regime == g].mean()) for g in sorted(regime.unique())},
            "exiting_within_30_days": float(present[exiting].mean()) if exiting.any() else None,
            "not_exiting": float(present[~exiting].mean()),
            "by_share_basis": {str(b): float(present[basis == b].mean()) for b in sorted(basis.unique())},
        }
    return out


def build(root: Path) -> dict[str, Any]:
    root = Path(root)
    began = time.perf_counter()
    exp009b.arm_firewall(root)
    from src.quant.study import exp011

    frozen, frozen_checks = exp011.load_rich_panel(root)          # refuses unless every EXP-011 pin verifies
    frozen["date"] = pd.to_datetime(frozen["date"])
    frame, frozen_manifest = exp009b.load_frame(root)
    frame = frame[frame["in_universe"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    base = frame[["date", "symbol", "close", *R.PASSTHROUGH[:2], *R.LABELS, *R.BASELINE_FEATURES]].copy()

    tables = root / "data/curated/security_master_v4"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    classification = pd.read_parquet(tables / "security_classification_interval.parquet")
    shares = pd.read_parquet(tables / "shares_fact_vintage.parquet")
    coverage_v4 = json.loads((root / "data/manifests/security_master_coverage_v4.json").read_text())
    regimes = identities.drop_duplicates("cik").set_index("cik")["filer_regime"]
    trusted = identities[identities["status"].isin(C.TRUSTED_GRADES)]
    domestic_ciks = set(trusted.loc[trusted["filer_regime"] != "FOREIGN_20F_40F", "cik"].astype("int64"))
    foreign_ciks = set(trusted.loc[trusted["filer_regime"] != "DOMESTIC_10K", "cik"].astype("int64"))
    folds = [f.as_dict() for f in exp009b.recorded_plan(root).folds]
    splits = pd.read_parquet(root / "data/research/raw/dolthub_stocks_split/part-all.parquet")

    multi_listed = V4.multi_listed_ciks(identities)
    foreign_regime_ciks = {int(c) for c, r in regimes.items() if r == "FOREIGN_20F_40F"}
    shares = shares[~shares["cik"].isin(multi_listed | foreign_regime_ciks)]                # D2 + D5: no share count, so no market cap
    domestic_snapshots = F.build_snapshots(load_facts(root, domestic_ciks))
    frame_v1 = R.build_panel(base, identities=identities, classification=classification, shares=shares, snapshots=domestic_snapshots,
                             split_table=C.split_factor_table(splits), controls_allowed=True)     # v1 code, v4 inputs; only the CONTROL columns are used
    foreign_snapshots = F.build_snapshots(load_foreign_facts(root, foreign_ciks))
    is_foreign_row = frame_v1["cik"].map(regimes).eq("FOREIGN_20F_40F")
    reference = frame_v1.loc[frame_v1["security_id"].notna() & ~is_foreign_row, ["date", *V2.FOREIGN_FEATURES]]
    fblock = V2.foreign_block(frame_v1[["date", "cik"]], foreign_snapshots, domestic_snapshots, reference)
    industry = C4.attach_classification_pit(frame_v1[["date", "cik"]], classification, V4.augmented_registry(root))    # corrected PIT rule
    cblock = V2.control_block(frame_v1, industry["ff12"])

    # frozen gates ----------------------------------------------------------------------------------------------
    market_by_fold = {k: v["market_cap_of_identified"] for k, v in coverage_v4["coverage"]["by_period"].items() if k.startswith("fold_")}
    controls = V2.control_gate(coverage_v4, market_by_fold)
    fcov = V2.foreign_coverage(frame_v1[["date", "cik", "security_id"]], fblock, regimes, folds)
    foreign = V2.foreign_gate(fcov)
    admitted = [*controls["admitted_columns"], *foreign["admitted_columns"]]
    enough = len(admitted) >= V2.GATE["minimum_incremental_columns"]

    increment = pd.concat([frame_v1[["date", "symbol"]].reset_index(drop=True),
                           cblock.reset_index(drop=True) if controls["passed"] else pd.DataFrame(index=range(len(frame_v1))),
                           fblock.reset_index(drop=True)[foreign["admitted_columns"]] if foreign["passed"] else pd.DataFrame(index=range(len(frame_v1)))], axis=1)
    meta_source = frame_v1[["date", "symbol", "security_id", "cik", "identity_grade"]].join(industry[["ff12", "ff17", "ff48", "sic"]])
    meta = meta_source[["date", "symbol", *META_V2]].rename(columns={c: f"v2_{c}" for c in META_V2}).reset_index(drop=True)
    meta["v2_filer_regime"] = meta["v2_cik"].map(regimes)
    meta["_shares_basis"] = frame_v1["shares_basis"].reset_index(drop=True)
    panel = frozen.merge(meta, on=["date", "symbol"], how="left", validate="one_to_one").merge(increment, on=["date", "symbol"], how="left", validate="one_to_one")
    panel = panel.sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
    assert panel["date"].max() <= pd.Timestamp("2025-05-09") and len(panel) == len(frozen)

    old_features = list(exp011.feature_list("rich"))
    new_columns = [c for c in admitted if c in panel.columns]
    features = old_features + new_columns
    invariance = V2.old_block_invariance(frozen, panel, old_features)
    assert invariance["changed_cells"] == 0, f"old block changed: {invariance}"

    ohlcv = load_ohlcv(root)
    windows = M.price_windows(ohlcv[ohlcv["symbol"].isin(set(panel["symbol"]))])
    last = panel["symbol"].map(lambda s: pd.Timestamp(windows[s].last) if s in windows else pd.NaT)
    exiting = last.notna() & (last <= pd.to_datetime(panel["date"]) + pd.Timedelta(days=30)) & (last < pd.Timestamp("2025-05-09") - pd.Timedelta(days=30))
    coverage = incremental_coverage(panel, new_columns, folds, regimes, exiting)

    columns = ["date", "symbol", *[f"v2_{c}" for c in META_V2], "v2_filer_regime", *R.PASSTHROUGH, *R.LABELS, *features]
    content = R.content_hash(panel, columns)
    panel[columns].to_parquet(root / PANEL_PATH, compression="zstd", index=False)
    manifest = {
        "dataset_id": f"ds-richpit2-{content[:16]}", "version": V2.V2_VERSION, "content_hash": content, "rows": int(len(panel)),
        "securities": int(panel["v2_security_id"].nunique()), "tickers": int(panel["symbol"].nunique()),
        "date_min": str(panel["date"].min().date()), "date_max": str(panel["date"].max().date()),
        "feature_count": len(features), "old_feature_count": len(old_features), "incremental_feature_count": len(new_columns),
        "features": features, "incremental_features": new_columns, "feature_hash": R.feature_hash(features),
        "old_feature_hash": R.feature_hash(old_features), "incremental_feature_hash": R.feature_hash(new_columns),
        "old_block_invariance": invariance, "frozen_dataset": {"dataset_id": "ds-richpit-ff3d3f556488b7da", "content_hash": exp011.RICH_CONTENT_HASH,
                                                                 "panel_checks": frozen_checks},
        "admission": {"controls": controls, "foreign": {**foreign, "coverage": fcov}, "minimum_incremental_columns": V2.GATE["minimum_incremental_columns"],
                      "enough_for_exp012": bool(enough)},
        "targets": list(R.LABELS), "primary_target": "fwd_rank_21",
        "source_manifests": {n: {"sha256": sha256_file(root / "data/manifests" / n)} for n in (
            "sec_archive_verification.json", "sec_fact_coverage_v3.json", "foreign_facts_v4.json", "security_master_coverage_v4.json")},
        "security_master_version": coverage_v4["version"], "security_master_pit": coverage_v4["security_master_pit"],
        "sec_fact_version": "sec-core-facts-v3", "ifrs_map_version": "ifrs-core-facts-v1", "ff_map_version": coverage_v4["french_sic_sha256"],
        "alfred": json.loads((root / "data/manifests/alfred_manifest.json").read_text()) if (root / "data/manifests/alfred_manifest.json").exists() else {"status": "NOT_BUILT"},
        "coverage": coverage, "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
        "build_commit": _git(root, "rev-parse", "HEAD"), "build_dirty": bool(_git(root, "status", "--porcelain")),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "build_seconds": round(time.perf_counter() - began, 1),
    }
    atomic_json(root / MANIFEST_PATH, manifest)
    return manifest
