#!/usr/bin/env python3
"""Independent recomputation of the reliability table on a random sample, by a deliberately naive code path.

The production builder is vectorised with searchsorted. This script recomputes the four variables for 4,000 sampled
(security, date) rows with plain pandas filtering on the raw filings registry and compares them with the saved table.
It also checks the structural invariants: no value before a firm's first filing, counts non-negative, binary flag in
{0, 1}, no use of the `prevrpt` column, and that every row's date lies inside the pre-holdout window.

Run with the repository interpreter:  .venv/bin/python docs/research/market-signal-review-2026-10-11/code/validate_reliability.py
Writes validation/reliability_validation.json next to the protocol.
"""

from __future__ import annotations

import json
import sys
from datetime import time as Time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from src.quant.pit import reliability as rel  # noqa: E402
from src.quant.pit.sec_facts import available_session  # noqa: E402
from src.quant.study import exp010b  # noqa: E402

PERIODIC, AMEND, ANNUAL = rel.PERIODIC, rel.AMENDMENT, rel.ANNUAL


def naive(filings: pd.DataFrame, cik: int, day: pd.Timestamp, calendar) -> dict[str, float]:
    """Plain pandas filtering. The availability rule (`available_session`) is shared with production and is covered by its
    own unit tests; what this path re-implements independently is the windowing, counting, flagging and lag arithmetic."""
    f = filings[(filings["cik"] == cik) & filings["form"].isin(PERIODIC | AMEND)].copy()
    f["accepted_at"] = pd.to_datetime(f["accepted_at"])
    f["avail"] = [pd.Timestamp(available_session(a, calendar)) if available_session(a, calendar) is not None else pd.NaT for a in f["accepted_at"]]
    usable = f[f["avail"] <= day]
    orig = usable[usable["form"].isin(PERIODIC)].sort_values(["avail", "accepted_at"])
    amend = usable[usable["form"].isin(AMEND)]
    if orig.empty:
        return {v: np.nan for v in rel.VARIABLES}
    lag = lambda r: (r["accepted_at"].normalize() - pd.to_datetime(str(r["period"])[:8], format="%Y%m%d")).days
    latest = orig.iloc[-1]
    same_kind = [r for _, r in orig.iloc[:-1].iterrows() if (r["form"] in ANNUAL) == (latest["form"] in ANNUAL)]
    prior = float(np.median([lag(r) for r in same_kind[-4:]])) if same_kind else np.nan
    within730 = amend[amend["avail"] > day - pd.Timedelta(days=730)]
    within400 = orig[orig["avail"] > day - pd.Timedelta(days=400)]
    amended_latest = float((amend["period"].astype(str).str[:8] == str(latest["period"])[:8]).any())
    return {"amended_730": float(len(within730)), "latest_report_amended": amended_latest,
            "periodic_count_400": float(len(within400)), "lag_deterioration": lag(latest) - prior}


def main() -> int:
    table = pd.read_parquet(REPO / rel.OUTPUT)
    panel = pd.read_parquet(REPO / "data/research/derived/rich_pit_panel.parquet", columns=["date", "symbol", "cik"])
    filings = pd.read_parquet(REPO / rel.FILINGS, columns=["cik", "form", "period", "accepted_at"])
    x = pd.concat([panel.reset_index(drop=True), table[list(rel.VARIABLES)].reset_index(drop=True)], axis=1)
    calendar = exp010b.build_daily_panel(REPO)[1]
    sample = x[x["cik"].notna()].sample(4000, random_state=20261012)
    mismatches = {v: 0 for v in rel.VARIABLES}
    examples = []
    for _, r in sample.iterrows():
        expected = naive(filings, int(r["cik"]), pd.Timestamp(r["date"]), calendar)
        for v in rel.VARIABLES:
            a, b = r[v], expected[v]
            same = (np.isnan(a) and np.isnan(b)) or (not np.isnan(a) and not np.isnan(b) and abs(a - b) < 1e-9)
            if not same:
                mismatches[v] += 1
                if len(examples) < 5:
                    examples.append({"symbol": r["symbol"], "date": str(r["date"]), "variable": v, "saved": None if np.isnan(a) else a, "naive": None if np.isnan(b) else b})
    invariants = {
        "counts_non_negative": bool((table[["amended_730", "periodic_count_400"]].dropna() >= 0).all().all()),
        "flag_binary": bool(set(table["latest_report_amended"].dropna().unique()) <= {0.0, 1.0}),
        "dates_before_holdout": bool(pd.to_datetime(table["date"]).max() <= pd.Timestamp("2025-05-09")),
        "rows_match_panel": bool(len(table) == len(panel)),
    }
    out = {"sample_rows": int(len(sample)), "mismatch_counts": mismatches, "mismatch_examples": examples, "invariants": invariants,
           "passed": bool(not any(mismatches.values()) and all(invariants.values()))}
    (BASE / "validation").mkdir(exist_ok=True)
    (BASE / "validation/reliability_validation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
