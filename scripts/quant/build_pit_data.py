"""Download, build and validate the literature-selected PIT data foundation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from src.quant.pit.alfred import download_alfred
from src.quant.pit.sec_foundation import (
    atomic_json, build_fundamentals, build_security_master, coverage_report,
    download_sec, estimate_download,
)

ROOT = Path(__file__).resolve().parents[2]
RAW_SEC = ROOT / "data/raw/sec"
RAW_SECURITY = ROOT / "data/raw/security_master"
RAW_ALFRED = ROOT / "data/raw/alfred"
CURATED_SEC = ROOT / "data/curated/sec"
CURATED_SEC_V3 = ROOT / "data/curated/sec_v3"
CURATED_SECURITY = ROOT / "data/curated/security_master"
MANIFESTS = ROOT / "data/manifests"


def universe_symbols() -> list[str]:
    payload = json.loads((ROOT / "data/research/universe/liquid.json").read_text())
    return sorted({symbol for snapshot in payload["snapshots"] for symbol in snapshot["symbols"]})


def trading_dates() -> list:
    dates = set()
    for path in sorted((ROOT / "data/research/raw/dolthub_stocks_ohlcv").glob("part-*.parquet")):
        frame = pd.read_parquet(path, columns=["date"])
        dates.update(pd.to_datetime(frame["date"]).dt.date)
    return sorted(dates)


def snapshot_map() -> pd.DataFrame:
    payload = json.loads((RAW_SECURITY / "company_tickers_exchange.json").read_text())
    frame = pd.DataFrame(payload["data"], columns=[str(value).lower() for value in payload["fields"]])
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    return frame


def build_all_fundamentals() -> dict:
    mapping = snapshot_map()
    ciks = set(mapping.loc[mapping["ticker"].isin(universe_symbols()), "cik"].astype(int))
    report = build_fundamentals(RAW_SEC, CURATED_SEC, MANIFESTS / "sec_download_manifest.json",
                                calendar_dates=trading_dates(), universe_ciks=ciks)
    atomic_json(MANIFESTS / "sec_fact_coverage.json", report)
    return report


def build_master() -> dict:
    report = build_security_master(RAW_SECURITY / "company_tickers_exchange.json", universe_symbols(),
                                   CURATED_SEC, CURATED_SECURITY,
                                   local_symbol_snapshot=ROOT / "data/research/raw/dolthub_stocks_symbol/part-all.parquet")
    atomic_json(MANIFESTS / "security_master_coverage.json", report)
    return report


def validate() -> dict:
    sec = coverage_report(CURATED_SEC)
    master_path = MANIFESTS / "security_master_coverage.json"
    master = json.loads(master_path.read_text()) if master_path.exists() else {"status": "NOT_BUILT"}
    result = {
        "status": "PASS" if sec.get("status") == "BUILT" and master.get("identity_intervals", 0) > 0 else "FAIL",
        "sec": sec, "security_master": master,
        "checks": {
            "accepted_at_present": bool(sec.get("rows", 0) and sec.get("accepted_min")),
            "no_future_acceptances": not sec.get("accepted_max", "9999").startswith(("2026", "2027")),
            "conflicts_surfaced": "conflict_count" in sec,
            "neutralization_prohibited": master.get("neutralization_allowed") is False,
        },
    }
    result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    atomic_json(MANIFESTS / "pit_data_validation.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["estimate", "download-sec", "verify-sec", "build-fundamentals", "build-facts-v3", "build-security-master-v3", "build-rich-panel", "build-security-master", "validate-all", "build-alfred", "validate", "all"])
    parser.add_argument("--reverify-archives", action="store_true", help="validate-all: re-hash and CRC every SEC archive (about 2 minutes)")
    parser.add_argument("--no-source-check", action="store_true", help="skip the HEAD size check against sec.gov")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "estimate":
        result = estimate_download(user_agent=os.environ.get("SEC_USER_AGENT", "miniAladdin-research aakashjawle101@gmail.com"))
    elif args.command == "download-sec":
        result = download_sec(RAW_SEC, MANIFESTS / "sec_download_manifest.json", force=args.force,
                              user_agent=os.environ.get("SEC_USER_AGENT", "miniAladdin-research aakashjawle101@gmail.com"))
    elif args.command == "verify-sec":
        from src.quant.pit.sec_archive_audit import verify_archives
        result = verify_archives(RAW_SEC, MANIFESTS / "sec_download_manifest.json", check_source=not args.no_source_check)
        atomic_json(MANIFESTS / "sec_archive_verification.json", result)
        result = {k: v for k, v in result.items() if k != "archives"}
    elif args.command == "build-facts-v3":
        from src.quant.pit import sec_facts
        from src.quant.pit.calendar import TradingCalendar
        report = sec_facts.build_store(RAW_SEC, MANIFESTS / "sec_download_manifest.json", CURATED_SEC_V3, ciks=None,
                                       calendar=TradingCalendar.from_dates(trading_dates()))
        coverage = sec_facts.coverage_report(CURATED_SEC_V3)
        atomic_json(MANIFESTS / "sec_fact_coverage_v3.json", {"build": report, "coverage": coverage})
        result = {"build": {k: v for k, v in report.items() if k != "quarters"}, "coverage_rows": coverage.get("rows")}
    elif args.command == "build-security-master-v3":
        from src.quant.pit import security_master_build as B
        from src.quant.study import exp009b
        built = B.build(ROOT)
        folds = [f.as_dict() for f in exp009b.recorded_plan(ROOT).folds]
        report = B.measure(ROOT, built, folds)
        atomic_json(MANIFESTS / "security_master_coverage_v3.json", report)
        result = {k: v for k, v in report.items() if k not in ("coverage",)}
    elif args.command == "build-rich-panel":
        from src.quant.pit import rich_panel_build
        manifest = rich_panel_build.build(ROOT)
        result = {k: manifest[k] for k in ("dataset_id", "rows", "securities", "feature_count", "new_feature_count", "feature_hash", "content_hash", "controls_allowed")}
    elif args.command == "validate-all":
        from src.quant.pit.validate_all import validate_all
        result = validate_all(ROOT, reverify_archives=args.reverify_archives)
        atomic_json(MANIFESTS / "pit_validation.json", result)
        print(json.dumps({"status": result["status"], **{k: v["status"] for k, v in result["checks"].items()}}, indent=2))
        return 1 if result["status"] == "FAIL" else 0
    elif args.command == "build-fundamentals":
        result = build_all_fundamentals()
    elif args.command == "build-security-master":
        result = build_master()
    elif args.command == "build-alfred":
        result = download_alfred(RAW_ALFRED, MANIFESTS / "alfred_manifest.json")
    elif args.command == "validate":
        result = validate()
    else:
        estimate = estimate_download(user_agent=os.environ.get("SEC_USER_AGENT", "miniAladdin-research aakashjawle101@gmail.com"))
        print(json.dumps({"estimate": estimate}, indent=2), flush=True)
        download_sec(RAW_SEC, MANIFESTS / "sec_download_manifest.json", force=args.force,
                     user_agent=os.environ.get("SEC_USER_AGENT", "miniAladdin-research aakashjawle101@gmail.com"))
        build_all_fundamentals()
        build_master()
        alfred = download_alfred(RAW_ALFRED, MANIFESTS / "alfred_manifest.json")
        result = {"validation": validate(), "alfred": alfred}
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status", result.get("validation", {}).get("status", "PASS")) != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
