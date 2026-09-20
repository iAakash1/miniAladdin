"""Validation of the data-completion cycle (v4): foreign store, truncation invariance, gate consistency, v2 dataset, holdout exclusion.

Each component is recorded as PASS, PARTIAL, BLOCKED or FAIL.  Nothing here reads a return, a label statistic or a model output, and no gate
is edited to reach PASS.  Truncation invariance: build with data accepted through T and with the complete source; every observation that was
available on or before T must be identical.
"""

from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from src.quant.features import pit_fundamentals as F
from src.quant.pit import pit_coverage as C
from src.quant.pit import pit_coverage_v4 as C4
from src.quant.pit import rich_panel as R
from src.quant.pit import rich_panel_v2 as V2
from src.quant.pit import security_master as M
from src.quant.pit import security_master_v4 as V4
from src.quant.pit.foreign_facts import FOREIGN_ANNUAL_FORMS
from src.quant.pit.rich_panel_build import load_facts
from src.quant.pit.rich_panel_v2_build import load_foreign_facts

CUTOFF = pd.Timestamp("2025-05-09 23:59:59")
HOLDOUT_START = pd.Timestamp("2025-08-26")
TRUNCATION_POINTS = ("2016-12-30", "2021-06-30")
DOMESTIC_SAMPLE = 150
SNAPSHOT_KEY = "accession"


def _status(passed: bool, **detail: Any) -> dict[str, Any]:
    return {"status": "PASS" if passed else "FAIL", **detail}


def _sample(ciks, n: int, salt: str) -> list[int]:
    return sorted(ciks, key=lambda c: hashlib.sha256(f"{salt}:{int(c)}".encode()).hexdigest())[:n]


def snapshot_invariance(facts: pd.DataFrame, cutoff: pd.Timestamp) -> dict[str, Any]:
    """Snapshots built from facts accepted through `cutoff` against the complete build, on the snapshots that were public by `cutoff`."""
    full = F.build_snapshots(facts)
    part = F.build_snapshots(facts[pd.to_datetime(facts["accepted_at"]) <= cutoff])
    full = full[pd.to_datetime(full["accepted_at"]) <= cutoff].sort_values(SNAPSHOT_KEY).reset_index(drop=True)
    part = part.sort_values(SNAPSHOT_KEY).reset_index(drop=True)
    columns = [c for c in full.columns if c in part.columns and pd.api.types.is_numeric_dtype(full[c])]
    same_keys = list(full[SNAPSHOT_KEY]) == list(part[SNAPSHOT_KEY])
    a, b = full[columns].to_numpy(dtype=float), part[columns].to_numpy(dtype=float) if same_keys else (None, None)
    changed = int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum()) if same_keys else -1
    return {"snapshots_full": int(len(full)), "snapshots_truncated": int(len(part)), "same_snapshot_set": bool(same_keys), "cells_compared": int(a.size) if same_keys else 0,
            "changed_cells": changed}


def check_foreign_store(root: Path) -> dict[str, Any]:
    paths = sorted(glob.glob(str(root / "data/curated/sec_v4_foreign/facts-*.parquet")))
    cols = ["cik", "accession", "form", "accepted_at", "available_session", "canonical_fact", "tag", "period_end", "qtrs", "value", "currency"]
    facts = pd.concat([pd.read_parquet(p, columns=cols) for p in paths], ignore_index=True)
    manifest = json.loads((root / "data/manifests/foreign_facts_v4.json").read_text())
    accepted = pd.to_datetime(facts["accepted_at"])
    duplicated = int(facts.duplicated(["accession", "canonical_fact", "tag", "period_end", "qtrs"]).sum())
    currencies = facts.groupby("accession")["currency"].nunique()
    problems = {"accepted_after_cutoff": int((accepted > CUTOFF).sum()), "non_annual_forms": int((~facts["form"].isin(FOREIGN_ANNUAL_FORMS)).sum()),
                "available_before_acceptance": int((pd.to_datetime(facts["available_session"]) < accepted.dt.normalize()).sum()),
                "duplicate_keys": duplicated, "filings_with_two_currencies": int((currencies > 1).sum()), "null_values": int(facts["value"].isna().sum()),
                "row_count_vs_manifest": int(len(facts) - sum(q["rows"] for q in manifest["quarters"]))}
    return _status(not any(problems.values()), rows=int(len(facts)), filings=int(facts["accession"].nunique()), ciks=int(facts["cik"].nunique()), problems=problems)


def check_fundamental_truncation(root: Path, identities: pd.DataFrame) -> dict[str, Any]:
    trusted = identities[identities["status"].isin(C.TRUSTED_GRADES)]
    regimes = trusted.drop_duplicates("cik").set_index("cik")["filer_regime"]
    foreign = {int(c) for c, r in regimes.items() if r != "DOMESTIC_10K"}
    domestic = _sample({int(c) for c, r in regimes.items() if r == "DOMESTIC_10K"}, DOMESTIC_SAMPLE, "exp012-truncation-v1")
    results = {}
    foreign_facts = load_foreign_facts(root, foreign)
    domestic_facts = load_facts(root, set(domestic))
    for point in TRUNCATION_POINTS:
        cutoff = pd.Timestamp(point) + pd.Timedelta(hours=23, minutes=59)
        results[point] = {"foreign_all": snapshot_invariance(foreign_facts, cutoff), f"domestic_sample_{DOMESTIC_SAMPLE}": snapshot_invariance(domestic_facts, cutoff)}
    clean = all(r["same_snapshot_set"] and r["changed_cells"] == 0 for by_point in results.values() for r in by_point.values())
    return _status(clean, points=results, foreign_ciks=len(foreign), domestic_sample=len(domestic))


def check_industry_and_share_truncation(root: Path, built: dict[str, Any]) -> dict[str, Any]:
    frame = pd.read_parquet(root / "data/research/derived/exp009b_frame.parquet", columns=["date", "symbol", "in_universe"])
    frame = frame[frame["in_universe"]].drop(columns="in_universe").reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["date"])
    splits = C.split_factor_table(pd.read_parquet(root / "data/research/raw/dolthub_stocks_split/part-all.parquet"))
    base = C.attach_identity(frame, built["identities"])
    maps, hashes = M.load_french_maps(root / "data/raw/french_sic")
    registry = built["registry"]
    multi_listed = V4.multi_listed_ciks(built["identities"])
    full_class = C4.attach_classification_pit(base, built["classification"], registry)
    full_shares = C4.apply_foreign_policy(C.attach_shares(base, built["shares"], splits), built["regimes"], multi_listed)
    out = {}
    for point in TRUNCATION_POINTS:
        cutoff = pd.Timestamp(point)
        rows = base["date"] <= cutoff
        registry_t = registry[pd.to_datetime(registry["accepted_at"]) <= cutoff + pd.Timedelta(hours=23, minutes=59)]
        class_t = M.classification_intervals(registry_t, built["identities"], maps, version="truncation-check")
        cut_class = C4.attach_classification_pit(base[rows], class_t, registry_t)
        industry_changed = int((~((full_class.loc[rows, ["sic", "ff12", "ff48"]].reset_index(drop=True).fillna(-1).astype(str)
                                 == cut_class[["sic", "ff12", "ff48"]].reset_index(drop=True).fillna(-1).astype(str)).all(axis=1))).sum())
        shares_t = built["shares"][pd.to_datetime(built["shares"]["accepted_at"]) <= cutoff + pd.Timedelta(hours=23, minutes=59)]
        cut_shares = C4.apply_foreign_policy(C.attach_shares(base[rows], shares_t, splits), built["regimes"], multi_listed)
        a, b = full_shares.loc[rows, "shares_outstanding"].to_numpy(dtype=float), cut_shares["shares_outstanding"].to_numpy(dtype=float)
        shares_changed = int((~((a == b) | (np.isnan(a) & np.isnan(b)))).sum())
        out[point] = {"rows": int(rows.sum()), "industry_rows_changed": industry_changed, "share_rows_changed": shares_changed}
    return _status(all(v["industry_rows_changed"] == 0 and v["share_rows_changed"] == 0 for v in out.values()), points=out)


def check_identity_stability(root: Path, built: dict[str, Any]) -> dict[str, Any]:
    """Identity is anchored on the *current* SEC ticker file and graded against filings evidence over the whole price window, so a trust grade is a
    retrospective judgement and not truncation-invariant.  What is measured: does the CIK a ticker maps to change when only filings and prices
    through T are visible?  Always PARTIAL: the design is retrospective and is disclosed as such."""
    ohlcv = built["ohlcv"]
    vendor = pd.read_parquet(root / "data/research/raw/dolthub_stocks_symbol/part-all.parquet", columns=["symbol", "security_name", "listing_exchange"])
    payload = json.loads((root / "data/raw/security_master/company_tickers_exchange.json").read_text())
    current = pd.DataFrame(payload["data"], columns=[str(f).lower() for f in payload["fields"]])
    current["ticker"] = current["ticker"].astype(str).str.upper()
    full = built["resolution"].drop_duplicates("ticker").set_index("ticker")
    out = {}
    for point in TRUNCATION_POINTS:
        cutoff = pd.Timestamp(point)
        prices = ohlcv[ohlcv["date"] <= cutoff]
        windows = M.price_windows(prices)
        registry_t = built["registry"][pd.to_datetime(built["registry"]["accepted_at"]) <= cutoff + pd.Timedelta(hours=23, minutes=59)]
        early = M.resolve_universe(sorted(windows), current, vendor, registry_t, windows, evidence_end=cutoff.date()).drop_duplicates("ticker").set_index("ticker")
        both = early.index.intersection(full.index)
        cik_equal = (early.loc[both, "cik"].fillna(-1).astype("int64") == full.loc[both, "cik"].fillna(-1).astype("int64"))
        grade_equal = early.loc[both, "grade"] == full.loc[both, "grade"]
        out[point] = {"tickers": int(len(both)), "cik_unchanged": float(cik_equal.mean()), "grade_unchanged": float(grade_equal.mean())}
    return {"status": "PARTIAL", "reason": "trust grades are a retrospective judgement over the whole price window (documented); the CIK assignment stability is reported", "points": out}


def check_gate_consistency(root: Path) -> dict[str, Any]:
    coverage = json.loads((root / "data/manifests/security_master_coverage_v4.json").read_text())
    recomputed = C.security_master_status({"by_year": coverage["coverage"]["by_year"], "by_period": coverage["coverage"]["by_period"]})
    keys = ("security_master_pit", "size_features_allowed", "neutralization_allowed")
    same = all(recomputed[k] == coverage[k] for k in keys)
    return _status(same, stored={k: coverage[k] for k in keys}, recomputed={k: recomputed[k] for k in keys}, thresholds=C.THRESHOLDS)


def check_v2_dataset(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "data/manifests/rich_pit_v2_manifest.json").read_text())
    panel = pd.read_parquet(root / "data/research/derived/rich_pit_v2_panel.parquet")
    panel["date"] = pd.to_datetime(panel["date"])
    features = manifest["features"]
    incremental = manifest["incremental_features"]
    recomputed = R.content_hash(panel, [c for c in panel.columns])
    problems = {
        "content_hash_mismatch": recomputed != manifest["content_hash"],
        "dataset_id_mismatch": manifest["dataset_id"] != f"ds-richpit2-{manifest['content_hash'][:16]}",
        "duplicate_keys": int(panel.duplicated(["date", "symbol"]).sum()),
        "rows_after_cutoff": int((panel["date"] > CUTOFF).sum()), "rows_in_holdout": int((panel["date"] >= HOLDOUT_START).sum()),
        "old_block_changed_cells": manifest["old_block_invariance"]["changed_cells"],
        "old_feature_hash_mismatch": manifest["old_feature_hash"] != R.feature_hash(features[:manifest["old_feature_count"]]),
        "incremental_out_of_range": int(sum(int(((panel[c] < -1.0000001) | (panel[c] > 1.0000001)).sum()) for c in incremental)),
        "incremental_without_identity": int(panel.loc[panel["v2_security_id"].isna(), incremental].notna().any(axis=1).sum()) if incremental else 0,
        "foreign_values_on_domestic_regime": int(panel.loc[panel["v2_filer_regime"].eq("DOMESTIC_10K"), incremental].notna().any(axis=1).sum()) if incremental else 0,
        "feature_count_mismatch": len(features) != manifest["feature_count"] or manifest["feature_count"] != manifest["old_feature_count"] + manifest["incremental_feature_count"],
        "holdout_touched": bool(manifest["holdout"]["touched"]), "built_from_dirty_tree": bool(manifest["build_dirty"]),
    }
    return _status(not any(bool(v) for v in problems.values()), dataset_id=manifest["dataset_id"], rows=int(len(panel)), features=len(features), problems=problems)


def check_holdout(root: Path) -> dict[str, Any]:
    tables = root / "data/curated/security_master_v4"
    identities = pd.read_parquet(tables / "security_identity_interval.parquet")
    exits = pd.read_parquet(tables / "security_exit_event.parquet")
    shares = pd.read_parquet(tables / "shares_fact_vintage.parquet")
    latest = {"identity_effective_from": identities["effective_from"].max(), "identity_effective_to": identities["effective_to"].max(),
              "exit_effective_date": pd.to_datetime(exits["effective_date"]).max(), "shares_accepted_at": pd.to_datetime(shares["accepted_at"]).max()}
    latest["foreign_facts_accepted_at"] = max(pd.read_parquet(p, columns=["accepted_at"])["accepted_at"].max() for p in sorted(glob.glob(str(root / "data/curated/sec_v4_foreign/facts-*.parquet"))))
    clean = all(pd.isna(v) or pd.Timestamp(v) <= CUTOFF for v in latest.values())
    return _status(bool(clean), latest={k: None if pd.isna(v) else str(pd.Timestamp(v)) for k, v in latest.items()}, cutoff=str(CUTOFF), holdout_start=str(HOLDOUT_START))


def check_alfred(root: Path) -> dict[str, Any]:
    state = json.loads((root / "data/manifests/alfred_manifest.json").read_text())
    if state.get("status") == "BLOCKED_EXTERNAL_FRED_KEY":
        return {"status": "BLOCKED", "reason": "BLOCKED_EXTERNAL_FRED_KEY: no FRED_API_KEY; no vintage table; revised data not substituted; ALFRED would add no predictor columns", "series": state.get("series")}
    return {"status": "PARTIAL", "reason": f"ALFRED status {state.get('status')} - vintage comparison not part of this validator"}


def validate_v4(root: Path) -> dict[str, Any]:
    root = Path(root)
    built = V4.load_built(root)
    checks: dict[str, Callable[[], dict[str, Any]]] = {
        "foreign_store": lambda: check_foreign_store(root),
        "fundamental_truncation_invariance": lambda: check_fundamental_truncation(root, built["identities"]),
        "industry_and_share_truncation_invariance": lambda: check_industry_and_share_truncation(root, built),
        "identity_cik_stability": lambda: check_identity_stability(root, built),
        "security_master_gate_consistency": lambda: check_gate_consistency(root),
        "alfred": lambda: check_alfred(root),
        "rich_pit_v2_dataset": lambda: check_v2_dataset(root),
        "holdout_exclusion": lambda: check_holdout(root),
    }
    results = {name: run() for name, run in checks.items()}
    states = {v["status"] for v in results.values()}
    overall = "FAIL" if "FAIL" in states else ("PARTIAL" if states & {"PARTIAL", "BLOCKED"} else "PASS")
    return {"status": overall, "version": "pit-validation-v4", "checks": results}
