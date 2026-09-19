"""`validate-all`: one command that re-derives the PIT data foundation's claims from the files.

Statuses per check: PASS, PARTIAL (built but a preregistered coverage threshold is not met), BLOCKED
(an external dependency or an unbuilt input prevents the check), FAIL (a violated invariant).  The
overall status is FAIL if any check fails, else BLOCKED if any is blocked, else PARTIAL if any is
partial, else PASS.  Missing is never zero and never PASS.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from src.quant.pit import pit_coverage as C
from src.quant.pit import sec_facts as S
from src.quant.pit import security_master as M
from src.quant.pit.calendar import TradingCalendar
from src.quant.pit.sec_foundation import sha256_file

CUTOFF = pd.Timestamp("2025-05-09 23:59:59")
HOLDOUT_START = pd.Timestamp("2025-08-26")


def result(status: str, detail: Any = None, **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **extra}


def overall(checks: dict[str, dict[str, Any]]) -> str:
    statuses = {c["status"] for c in checks.values()}
    for level in ("FAIL", "BLOCKED", "PARTIAL"):
        if level in statuses:
            return level
    return "PASS"


# ── individual checks ────────────────────────────────────────────────────────

def check_sec_archives(root: Path, *, reverify: bool) -> dict[str, Any]:
    manifest = root / "data/manifests/sec_archive_verification.json"
    if reverify:
        from src.quant.pit.sec_archive_audit import verify_archives
        report = verify_archives(root / "data/raw/sec", root / "data/manifests/sec_download_manifest.json",
                                 check_source=False, progress=None)
        manifest.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    elif manifest.exists():
        report = json.loads(manifest.read_text())
    else:
        return result("BLOCKED", "sec_archive_verification.json not built; run verify-sec")
    ok = report["status"] == "PASS"
    return result("PASS" if ok else "FAIL", {"archives": report["present_archives"], "continuous": report["continuity"]["continuous"],
                                             "problems": report["problems"][:5], "bytes": report["total_bytes"]},
                  reverified_now=reverify)


def check_facts_store(root: Path) -> dict[str, Any]:
    directory = root / "data/curated/sec_v3"
    manifest_path = root / "data/manifests/sec_fact_coverage_v3.json"
    if not directory.exists() or not manifest_path.exists():
        return result("BLOCKED", "v3 fact store not built")
    manifest = json.loads(manifest_path.read_text())
    problems, rows = [], 0
    recorded = {q["quarter"]: q for q in manifest["build"]["quarters"]}
    for path in sorted(directory.glob("facts-*.parquet")):
        quarter = path.stem.replace("facts-", "")
        if sha256_file(path) != recorded[quarter]["output_sha256"]:
            problems.append(f"{quarter}: file hash differs from the build manifest")
        frame = pd.read_parquet(path, columns=["accepted_at", "unit", "value", "tag_map_version"])
        rows += len(frame)
        if frame["unit"].isna().any():
            problems.append(f"{quarter}: null unit")
        if frame["value"].isna().any():
            problems.append(f"{quarter}: null value")
        if frame["accepted_at"].max() > CUTOFF:
            problems.append(f"{quarter}: accepted after the research cutoff")
        if set(frame["tag_map_version"]) - {S.TAG_MAP_VERSION}:
            problems.append(f"{quarter}: unexpected tag-map version")
    if rows != manifest["coverage"]["rows"]:
        problems.append(f"row count {rows} != manifest {manifest['coverage']['rows']}")
    if len(recorded) != 58:
        problems.append(f"{len(recorded)} quarters recorded, expected 58")
    return result("PASS" if not problems else "FAIL", {"rows": rows, "quarters": len(recorded), "problems": problems[:8]})


def check_restatement_invariance(root: Path, quarters: tuple[str, ...] = ("2019q1", "2019q2", "2019q3", "2019q4"),
                                 cut: str = "2019-07-01 00:00:00") -> dict[str, Any]:
    """Rebuild from archives truncated at `cut`; everything accepted before `cut` must be identical."""
    raw = root / "data/raw/sec"
    if not all((raw / f"{q}.zip").exists() for q in quarters):
        return result("BLOCKED", "archives absent")
    hashes = {r["filename"]: r["sha256"] for r in json.loads((root / "data/manifests/sec_download_manifest.json").read_text())["archives"]}
    full_parts, cut_parts = [], []
    for quarter in quarters:
        _, facts_full, _ = S.curate_archive(raw / f"{quarter}.zip", hashes[f"{quarter}.zip"], calendar=None)
        _, facts_cut, _ = S.curate_archive(raw / f"{quarter}.zip", hashes[f"{quarter}.zip"], calendar=None, accepted_cutoff=cut)
        full_parts.append(facts_full)
        cut_parts.append(facts_cut)
    full, truncated = pd.concat(full_parts, ignore_index=True), pd.concat(cut_parts, ignore_index=True)
    before = full[full["accepted_at"] <= pd.Timestamp(cut)]
    same_rows = S.content_hash(before) == S.content_hash(truncated)
    columns = S.FACT_KEY + ["accession", "value", "tag"]
    a = S.as_of(full, cut).sort_values(S.FACT_KEY)[columns].reset_index(drop=True)
    b = S.as_of(truncated, cut).sort_values(S.FACT_KEY)[columns].reset_index(drop=True)
    same_view = a.astype(str).equals(b.astype(str))
    first_full = S.first_reported(full)
    first_full = first_full[first_full["accepted_at"] <= pd.Timestamp(cut)].sort_values(S.FACT_KEY)[columns].reset_index(drop=True)
    first_cut = S.first_reported(truncated).sort_values(S.FACT_KEY)[columns].reset_index(drop=True)
    same_first = first_full.astype(str).equals(first_cut.astype(str))
    later = full[full["accepted_at"] > pd.Timestamp(cut)]
    keys_before = set(map(tuple, truncated[S.FACT_KEY].astype(str).to_numpy()))
    restated_later = int(sum(1 for k in map(tuple, later[S.FACT_KEY].astype(str).to_numpy()) if k in keys_before))
    amendments_after = int(later["amendment"].sum())
    ok = same_rows and same_view and same_first
    return result("PASS" if ok else "FAIL", {
        "quarters": list(quarters), "truncation": cut, "rows_before_cut": int(len(before)), "identical_rows": same_rows,
        "identical_as_of_view": same_view, "identical_first_reported": same_first,
        "later_vintages_of_pre_cut_keys": restated_later, "amendment_rows_after_cut": amendments_after,
        "note": "the test bites only if later vintages of pre-cut keys exist" if restated_later else "no later vintage in this window: test is weak"})


def check_availability_rule(root: Path, sample: int = 200_000) -> dict[str, Any]:
    directory = root / "data/curated/sec_v3"
    if not directory.exists():
        return result("BLOCKED", "v3 fact store not built")
    path = sorted(directory.glob("facts-2021q*.parquet"))[0]
    frame = pd.read_parquet(path, columns=["accepted_at", "available_session"]).dropna().head(sample)
    accepted = pd.to_datetime(frame["accepted_at"])
    available = pd.to_datetime(frame["available_session"])
    after_close = accepted.dt.time >= S.MARKET_CLOSE
    same_day_after_close = ((available.dt.normalize() == accepted.dt.normalize()) & after_close).sum()
    before_acceptance = (available.dt.normalize() < accepted.dt.normalize()).sum()
    ok = same_day_after_close == 0 and before_acceptance == 0
    return result("PASS" if ok else "FAIL", {"rows": int(len(frame)), "after_close_available_same_day": int(same_day_after_close),
                                            "available_before_acceptance": int(before_acceptance),
                                            "timezone": S.ACCEPTANCE_TIMEZONE, "close": S.MARKET_CLOSE.isoformat()})


def check_identity(root: Path) -> dict[str, Any]:
    path = root / "data/curated/security_master_v3/security_identity_interval.parquet"
    if not path.exists():
        return result("BLOCKED", "identity intervals not built")
    ids = pd.read_parquet(path)
    try:
        M.check_no_overlap(ids)
        overlap = None
    except ValueError as error:
        overlap = str(error)
    reuse = int((ids.groupby("ticker")["cik"].nunique() > 1).sum())
    late = int((pd.to_datetime(ids["effective_from"]) > CUTOFF).sum())
    grades = ids["status"].value_counts().to_dict()
    problems = [p for p in (overlap, f"{late} intervals begin after the research cutoff" if late else None) if p]
    return result("FAIL" if problems else "PASS", {"intervals": int(len(ids)), "grades": {k: int(v) for k, v in grades.items()},
                                                   "tickers_with_more_than_one_cik": reuse, "problems": problems})


def check_classification(root: Path) -> dict[str, Any]:
    path = root / "data/curated/security_master_v3/security_classification_interval.parquet"
    if not path.exists():
        return result("BLOCKED", "classification intervals not built")
    table = pd.read_parquet(path)
    missing = {level: float(table[level].isna().mean()) for level in ("ff12", "ff17", "ff48")}
    monotone = bool((table.groupby("cik")["effective_from"].apply(lambda s: s.is_monotonic_increasing)).all())
    status = "PASS" if monotone and max(missing.values()) < 0.05 else "FAIL"
    return result(status, {"intervals": int(len(table)), "ciks": int(table["cik"].nunique()), "missing_share": missing, "monotone": monotone,
                           "source": "SEC sic as of the filing date (per the FSDS readme) mapped by the Kenneth French SIC files; no GICS"})


def check_shares_and_market_cap(root: Path) -> dict[str, Any]:
    manifest = root / "data/manifests/security_master_coverage_v3.json"
    if not manifest.exists():
        return result("BLOCKED", "security master coverage not built")
    report = json.loads(manifest.read_text())
    folds = {k: v for k, v in report["coverage"]["by_period"].items() if k.startswith("fold_")}
    floor = C.THRESHOLDS["size_feature_share_min_each_validation_fold"]
    worst = min((v["market_cap_of_identified"] or 0.0) for v in folds.values())
    return result("PASS" if worst >= floor else "PARTIAL", {"worst_fold_market_cap_share_of_identified": worst, "required": floor,
                                                            "shares_vintages": report["shares_vintages"], "by_basis": report["shares_by_basis"]})


def check_security_master_gate(root: Path) -> dict[str, Any]:
    manifest = root / "data/manifests/security_master_coverage_v3.json"
    if not manifest.exists():
        return result("BLOCKED", "security master coverage not built")
    report = json.loads(manifest.read_text())
    recomputed = C.security_master_status(report["coverage"])
    consistent = recomputed["security_master_pit"] == report["security_master_pit"]
    if not consistent:
        return result("FAIL", "manifest flag disagrees with the thresholds")
    return result("PASS" if report["security_master_pit"] else "PARTIAL", {
        "security_master_pit": report["security_master_pit"], "neutralization_allowed": report["neutralization_allowed"],
        "size_features_allowed": report["size_features_allowed"], "failures": report["failures"][:10], "unresolved_tickers": report["unresolved_tickers"]})


def check_holdout_exclusion(root: Path) -> dict[str, Any]:
    problems = []
    store = root / "data/curated/sec_v3"
    if store.exists():
        latest = max(pd.read_parquet(p, columns=["accepted_at"])["accepted_at"].max() for p in store.glob("facts-*.parquet"))
        if latest >= HOLDOUT_START:
            problems.append(f"SEC facts accepted {latest} reach the holdout")
    ids = root / "data/curated/security_master_v3/security_identity_interval.parquet"
    if ids.exists():
        table = pd.read_parquet(ids)
        end = pd.to_datetime(table["effective_to"]).max()
        if pd.notna(end) and end >= HOLDOUT_START:
            problems.append(f"identity window ends {end}, inside the holdout")
    manifest = root / "experiments/EXP-010B/manifest.json"
    if manifest.exists() and json.loads(manifest.read_text())["holdout"]["touched"] is not False:
        problems.append("EXP-010B manifest reports a touched holdout")
    return result("FAIL" if problems else "PASS", {"cutoff": str(CUTOFF), "holdout_start": str(HOLDOUT_START), "problems": problems})


def check_alfred(root: Path) -> dict[str, Any]:
    manifest = root / "data/manifests/alfred_manifest.json"
    key_present = bool(os.environ.get("FRED_API_KEY"))
    if not key_present:
        return result("BLOCKED", "BLOCKED_EXTERNAL_FRED_KEY: no FRED_API_KEY in the environment; no macro vintage data exists", series=["DGS3MO", "DGS2", "DGS10"])
    if not manifest.exists() or json.loads(manifest.read_text()).get("status") != "BUILT":
        return result("BLOCKED", "key present but ALFRED vintages not built; run build-alfred")
    return result("PASS", json.loads(manifest.read_text()))


def check_hashes(root: Path) -> dict[str, Any]:
    inventory = root / "data/manifests/data_inventory.json"
    if not inventory.exists():
        return result("BLOCKED", "data_inventory.json not built")
    payload = json.loads(inventory.read_text())
    bad = [e["id"] for e in payload["normalized_datasets"] if not e["sha256"]["first_partition_recomputed_matches"]]
    return result("PASS" if not bad else "FAIL", {"datasets": len(payload["normalized_datasets"]), "first_partition_mismatches": bad})


def validate_all(root: Path, *, reverify_archives: bool = False, run_restatement: bool = True) -> dict[str, Any]:
    root = Path(root)
    checks: dict[str, dict[str, Any]] = {}
    plan: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("sec_archive_integrity", lambda: check_sec_archives(root, reverify=reverify_archives)),
        ("sec_fact_store_v3", lambda: check_facts_store(root)),
        ("sec_availability_after_close_rule", lambda: check_availability_rule(root)),
        ("restatement_invariance_real_data", (lambda: check_restatement_invariance(root)) if run_restatement else (lambda: result("BLOCKED", "skipped"))),
        ("identity_intervals_and_ticker_reuse", lambda: check_identity(root)),
        ("sic_and_french_industries", lambda: check_classification(root)),
        ("shares_and_market_cap", lambda: check_shares_and_market_cap(root)),
        ("security_master_pit_gate", lambda: check_security_master_gate(root)),
        ("holdout_exclusion", lambda: check_holdout_exclusion(root)),
        ("alfred_macro_vintages", lambda: check_alfred(root)),
        ("raw_and_curated_hashes", lambda: check_hashes(root)),
    ]
    for name, check in plan:
        try:
            checks[name] = check()
        except Exception as error:  # a crashing check is a failed check, never a skipped one
            checks[name] = result("FAIL", f"{type(error).__name__}: {error}")
    return {"validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": overall(checks),
            "checks": checks, "missing_is_not_zero": True}
