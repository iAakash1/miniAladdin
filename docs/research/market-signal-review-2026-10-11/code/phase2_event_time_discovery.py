#!/usr/bin/env python3
"""Phase II step 4c: is the amendment association a post-event effect, an anticipation effect, or a marker of persistent trouble? (discovery sample, exploratory)

Event-time regression with the registered EXP-014 definitions, on the discovery sample's validation period (2017-05..2025-05, identity-trusted rows): indicators for a value-changing amendment available in
(-365, 0], (-730, -365], (-1460, -730] days (past) and in (0, 365], (365, 730] days (future; used only as a diagnostic, never as a predictor). If the effect were information released by the amendment, only the
past bins should be negative. If the firms are simply troubled before and after, the future bins will be about as negative. The wild-cluster bootstrap p-values use 4,999 draws.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/phase2_event_time_discovery.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from src.quant.study import exp014  # noqa: E402

OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/phase2_event_time_discovery.json"


def main() -> int:
    calendar = exp014.read_calendar(REPO)
    frozen = pd.read_parquet(REPO / exp014.FROZEN_PANEL)
    frozen["date"] = pd.to_datetime(frozen["date"])
    rows = frozen[(frozen["date"] >= "2017-05-05") & frozen["security_id"].notna() & frozen[exp014.LABEL].notna()].reset_index(drop=True)
    d = exp014.assemble(rows, REPO, calendar)
    bins = ["D_core_prev365", "D_core_prev730b", "D_core_old", "D_core_next365", "D_core_next730b", "D_other_730", "D_unchanged_730", "D_unclass_730"]
    res = {"status": "EXPLORATORY discovery-sample reading of the registered event-time diagnostic; not confirmatory", "rows": int(len(d)), "firms": int(d["firm"].nunique()), "bins": {}}
    for focus in bins[:5]:
        r = exp014.regress(d, focus, bins, exp014.BASE_CONTROLS, draws=4999, seed=exp014.SEED, label=focus)
        res["bins"][focus] = {k: r[k] for k in ("coef", "t_two_way", "wcr_p_negative", "treated_firms", "treated_rows")}
        print(f"{focus:18s} coef {r['coef']:+.4f}  t(two-way) {r['t_two_way']:+.2f}  WCR p(neg) {r['wcr_p_negative']:.4f}  treated firms {r['treated_firms']:3d} rows {r['treated_rows']:5d}")
    prev, nxt = res["bins"]["D_core_prev365"]["coef"], res["bins"]["D_core_next365"]["coef"]
    res["anticipation_ratio"] = nxt / prev if prev < 0 else None
    res["reading"] = ("ratio below 0.5: the association is concentrated after the amendment (TIME_SPECIFIC); at or above 0.5: the firms look just as weak before the amendment as after (MARKER_OF_PERSISTENT_TROUBLE)")
    print("anticipation ratio (next365 / prev365):", res["anticipation_ratio"])
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
