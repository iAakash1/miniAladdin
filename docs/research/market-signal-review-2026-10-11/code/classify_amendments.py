#!/usr/bin/env python3
"""Classify every periodic-report amendment in the SEC Financial Statement Data Sets registry as value-changing or not.

EXP-012/013 counted amendments (10-K/A, 10-Q/A and their transition-period forms). An amendment is not a restatement: many only add an exhibit, an auditor's report or a corrected cover page. Whether an
amendment changed the reported numbers is observable at the amendment's own acceptance time, because both the amendment's facts and the previous version's facts were public then. For each amendment this
script finds the previous version (same CIK, same fiscal period, accepted earlier, latest such filing), compares the 20 canonical facts the curated store extracts (revenue, net income, assets, liabilities,
equity, cash flows ...) on every key present in both versions, and records how many changed and by how much.

Nothing here reads a return or a label. The output is a point-in-time attribute of each amendment, usable from the amendment's acceptance session onward.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/classify_amendments.py

Writes data/research/derived/amendment_classification_v1.parquet (git-ignored) and validation/amendment_classification_summary.json.
"""

from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
SEC = REPO / "data/curated/sec_v3"
OUT = REPO / "data/research/derived/amendment_classification_v1.parquet"
SUMMARY = REPO / "docs/research/market-signal-review-2026-10-11/validation/amendment_classification_summary.json"
AMEND = {"10-K/A": "10-K", "10-Q/A": "10-Q", "10-KT/A": "10-KT", "10-QT/A": "10-QT"}
CORE = ["revenue", "net_income", "assets", "liabilities", "equity", "operating_cash_flow"]
THRESHOLDS = (0.001, 0.01, 0.05)


def main() -> int:
    reg = pd.read_parquet(SEC / "filings.parquet", columns=["adsh", "cik", "form", "period", "accepted_at"])
    reg["accepted_at"] = pd.to_datetime(reg["accepted_at"])
    periodic = reg[reg["form"].isin(set(AMEND) | set(AMEND.values()))].copy()
    am = periodic[periodic["form"].isin(AMEND)].copy()
    # previous version: same cik and period, accepted strictly earlier, latest such
    prev = periodic.rename(columns={"adsh": "prev_adsh", "form": "prev_form", "accepted_at": "prev_accepted_at"})
    joined = am.merge(prev[["cik", "period", "prev_adsh", "prev_form", "prev_accepted_at"]], on=["cik", "period"], how="left")
    joined = joined[joined["prev_accepted_at"].isna() | (joined["prev_accepted_at"] < joined["accepted_at"])]
    joined = joined.sort_values(["adsh", "prev_accepted_at"]).groupby("adsh", as_index=False).tail(1)
    result = am.merge(joined[["adsh", "prev_adsh", "prev_form", "prev_accepted_at"]], on="adsh", how="left")
    wanted = set(result["adsh"]) | set(result["prev_adsh"].dropna())
    parts = []
    for path in sorted(glob.glob(str(SEC / "facts-*.parquet"))):
        f = pd.read_parquet(path, columns=["accession", "canonical_fact", "qtrs", "unit", "period_end", "value", "tag_priority"])
        parts.append(f[f["accession"].isin(wanted)])
    facts = pd.concat(parts, ignore_index=True)
    facts = facts.sort_values("tag_priority", kind="mergesort").drop_duplicates(["accession", "canonical_fact", "qtrs", "unit", "period_end"], keep="first")
    facts["key"] = facts["canonical_fact"] + "|" + facts["qtrs"].astype(str) + "|" + facts["unit"].astype(str) + "|" + facts["period_end"].astype(str)
    by_acc = {a: g.set_index("key")["value"] for a, g in facts.groupby("accession")}
    rows = []
    for r in result.itertuples(index=False):
        rec = {"adsh": r.adsh, "cik": int(r.cik), "form": r.form, "period": r.period, "accepted_at": r.accepted_at, "prev_adsh": r.prev_adsh, "prev_form": r.prev_form, "prev_accepted_at": r.prev_accepted_at,
               "has_facts": r.adsh in by_acc, "prev_has_facts": (r.prev_adsh in by_acc) if isinstance(r.prev_adsh, str) else False}
        rec.update({"n_keys_compared": 0, "max_rel_change": np.nan, "max_rel_change_core": np.nan, **{f"n_changed_{int(t * 1000)}": 0 for t in THRESHOLDS}, **{f"core_changed_{c}": False for c in CORE}})
        if rec["has_facts"] and rec["prev_has_facts"]:
            a, p = by_acc[r.adsh], by_acc[r.prev_adsh]
            common = a.index.intersection(p.index)
            rec["n_keys_compared"] = int(len(common))
            if len(common):
                av, pv = a.loc[common].astype(float).to_numpy(), p.loc[common].astype(float).to_numpy()
                denom = np.maximum(np.abs(pv), 1.0)
                rel = np.abs(av - pv) / denom
                rec["max_rel_change"] = float(rel.max())
                for t in THRESHOLDS:
                    rec[f"n_changed_{int(t * 1000)}"] = int((rel > t).sum())
                names = np.array([k.split("|")[0] for k in common])
                core = np.isin(names, CORE)
                if core.any():
                    rec["max_rel_change_core"] = float(rel[core].max())
                for c in CORE:
                    m = names == c
                    rec[f"core_changed_{c}"] = bool((rel[m] > 0.01).any()) if m.any() else False
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["classifiable"] = out["n_keys_compared"] > 0
    out["value_changing_1pct"] = out["classifiable"] & (out["n_changed_10"] > 0)
    out["core_changing_1pct"] = out["classifiable"] & out[[f"core_changed_{c}" for c in CORE]].any(axis=1)
    out["unchanged_numbers"] = out["classifiable"] & (out["n_changed_1"] == 0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, compression="zstd", index=False)
    year = out["accepted_at"].dt.year
    summary = {
        "status": "newly generated; label-free point-in-time attribute of each amendment",
        "inputs": {"registry": "data/curated/sec_v3/filings.parquet", "facts": "data/curated/sec_v3/facts-*.parquet", "canonical_facts": sorted(facts["canonical_fact"].unique().tolist())},
        "amendments": int(len(out)), "with_previous_version": int(out["prev_adsh"].notna().sum()), "classifiable": int(out["classifiable"].sum()),
        "classifiable_share": float(out["classifiable"].mean()),
        "of_classifiable": {"unchanged_numbers (no key differs by >0.1%)": float(out.loc[out["classifiable"], "unchanged_numbers"].mean()),
                            "value_changing_1pct (any key differs by >1%)": float(out.loc[out["classifiable"], "value_changing_1pct"].mean()),
                            "core_changing_1pct (revenue, net income, assets, liabilities, equity or operating cash flow differs by >1%)": float(out.loc[out["classifiable"], "core_changing_1pct"].mean())},
        "by_form": {f: {"n": int((out["form"] == f).sum()), "core_changing_1pct_share_of_classifiable": float(out.loc[(out["form"] == f) & out["classifiable"], "core_changing_1pct"].mean())} for f in sorted(out["form"].unique())},
        "by_year": {int(y): {"n": int((year == y).sum()), "core_changing_1pct_share_of_classifiable": float(out.loc[(year == y) & out["classifiable"], "core_changing_1pct"].mean())} for y in sorted(year.unique())},
        "output": {"path": str(OUT.relative_to(REPO)), "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(), "rows": int(len(out))},
        "rule": "previous version = latest filing with the same cik and fiscal period accepted strictly before the amendment; keys compared = canonical fact x quarters x unit x period end present in both; relative change = |a - b| / max(|b|, 1)",
    }
    SUMMARY.write_text(json.dumps(summary, indent=1, default=float) + "\n")
    print(json.dumps(summary, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
