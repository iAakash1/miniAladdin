"""Data-completion cycle (v4): foreign facts, identity/exit/shares completion, ALFRED, rich PIT v2.  See docs/DATA_COMPLETION_GATE_2026.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from scripts.quant.build_pit_data import ROOT, MANIFESTS, RAW_SEC, trading_dates
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_foundation import atomic_json

CURATED_FOREIGN = ROOT / "data/curated/sec_v4_foreign"


def foreign_facts() -> dict:
    from src.quant.pit import foreign_facts as X

    report = X.build_foreign_store(RAW_SEC, MANIFESTS / "sec_download_manifest.json", CURATED_FOREIGN,
                                   calendar=TradingCalendar.from_dates(trading_dates()))
    atomic_json(MANIFESTS / "foreign_facts_v4.json", report)
    X.mapping_table().to_csv(ROOT / "data/manifests/ifrs_core_facts_v1_map.csv", index=False)
    return {k: v for k, v in report.items() if k != "quarters"}


def foreign_invariance() -> dict:
    """Real-data parser invariance on a high-volume archive; no labels or outcomes are read."""
    from src.quant.pit import foreign_facts as X

    download = json.loads((MANIFESTS / "sec_download_manifest.json").read_text())
    hashes = {row["filename"]: row["sha256"] for row in download["archives"]}
    archive = "2024q2.zip"
    report = X.validate_chunk_invariance(
        RAW_SEC / archive, hashes[archive], calendar=TradingCalendar.from_dates(trading_dates())
    )
    atomic_json(MANIFESTS / "foreign_chunk_invariance.json", report)
    manifest_path = MANIFESTS / "foreign_facts_v4.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["store_content_hash"] = hashlib.sha256(json.dumps(
        [(row["quarter"], row["output_sha256"]) for row in manifest["quarters"]], separators=(",", ":")
    ).encode()).hexdigest()
    manifest["chunk_invariance"] = {
        "status": report["status"], "archive": archive,
        "chunk_rows": report["chunk_rows"], "manifest": "data/manifests/foreign_chunk_invariance.json",
    }
    atomic_json(manifest_path, manifest)
    return report


def security_master() -> dict:
    from src.quant.pit import security_master_v4 as V4
    from src.quant.study import exp009b

    built = V4.build(ROOT)
    folds = [f.as_dict() for f in exp009b.recorded_plan(ROOT).folds]
    report = V4.measure(ROOT, built, folds)
    atomic_json(MANIFESTS / "security_master_coverage_v4.json", report)
    return {k: v for k, v in report.items() if k not in ("coverage", "coverage_all_rows", "share_tiers_by_year", "share_tiers_by_period", "ticker_reuse_review")}


def measure_only() -> dict:
    from src.quant.pit import security_master_v4 as V4
    from src.quant.study import exp009b

    report = V4.measure(ROOT, V4.load_built(ROOT), [f.as_dict() for f in exp009b.recorded_plan(ROOT).folds])
    atomic_json(MANIFESTS / "security_master_coverage_v4.json", report)
    return {k: v for k, v in report.items() if k not in ("coverage", "coverage_all_rows", "share_tiers_by_year", "share_tiers_by_period", "ticker_reuse_review")}


def rich_panel_v2() -> dict:
    from src.quant.pit import rich_panel_v2_build as B

    manifest = B.build(ROOT)
    return {k: manifest[k] for k in ("dataset_id", "content_hash", "rows", "securities", "tickers", "feature_count", "old_feature_count",
                                     "incremental_feature_count", "old_feature_hash", "incremental_feature_hash", "old_block_invariance")}


def alfred() -> dict:
    """Vintage table when FRED_API_KEY is present; otherwise records BLOCKED_EXTERNAL_FRED_KEY.  Never prints the key."""
    from src.quant.pit import alfred_vintage as A

    return A.build(ROOT / "data/raw/alfred", MANIFESTS / "alfred_manifest.json")


def validate() -> dict:
    from src.quant.pit.validate_v4 import validate_v4

    result = validate_v4(ROOT)
    atomic_json(MANIFESTS / "pit_validation_v4.json", result)
    return {"status": result["status"], **{k: v["status"] for k, v in result["checks"].items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["foreign-facts", "foreign-invariance", "security-master", "measure", "alfred", "rich-panel-v2", "validate"])
    args = parser.parse_args()
    if args.command == "foreign-facts":
        result = foreign_facts()
    elif args.command == "foreign-invariance":
        result = foreign_invariance()
    elif args.command == "rich-panel-v2":
        result = rich_panel_v2()
    elif args.command == "validate":
        result = validate()
    elif args.command == "alfred":
        result = alfred()
    elif args.command == "measure":
        result = measure_only()
    elif args.command == "security-master":
        result = security_master()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
