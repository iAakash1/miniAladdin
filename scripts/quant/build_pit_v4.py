"""Data-completion cycle (v4): foreign facts, identity/exit/shares completion, ALFRED, rich PIT v2.  See docs/DATA_COMPLETION_GATE_2026.md."""

from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["foreign-facts", "security-master", "measure", "rich-panel-v2"])
    args = parser.parse_args()
    if args.command == "foreign-facts":
        result = foreign_facts()
    elif args.command == "rich-panel-v2":
        result = rich_panel_v2()
    elif args.command == "measure":
        result = measure_only()
    elif args.command == "security-master":
        result = security_master()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
