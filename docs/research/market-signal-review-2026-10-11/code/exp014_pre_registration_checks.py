#!/usr/bin/env python3
"""Everything that is measured about the independent sample BEFORE EXP-014 is registered, and nothing that is not.

Produces validation/exp014_pre_registration_checks.json with four blocks:

* label_free_counts   how many companies and rows carry each treatment in the confirmatory and time-separate samples (reads treatment indicators, never a label);
* size_calibration    the registered inference applied to placebo amendments given to randomly chosen firms: the rejection rate must not exceed the nominal 5%
                      (reads the label, but only against placebo treatments; no real amendment variable is related to a label);
* mid_panel           row, date and identity coverage of the independent panel, from its manifest;
* edgar_registry      coverage of the EDGAR registry and the result of the acceptance-clock audit, from its manifest.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/exp014_pre_registration_checks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp014  # noqa: E402

OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/exp014_pre_registration_checks.json"


def main() -> int:
    calendar = exp014.read_calendar(REPO)
    conf, sep, counts = exp014.build_samples(REPO, calendar)
    treatments = ("core_730", "other_730", "unchanged_730", "unclass_730", "any_730")

    def block(frame):
        return {"rows": int(len(frame)), "firms": int(frame["firm"].nunique()), "dates": int(frame["date"].nunique()), "rows_without_history": int(frame["D_core_730"].isna().sum()),
                "treatments": {t: {"rows": int((frame[f"D_{t}"] > 0).sum()), "firms": int(frame.loc[frame[f"D_{t}"] > 0, "firm"].nunique())} for t in treatments}}

    label_free = {**counts, "confirmatory": block(conf), "time_separate": block(sep)}
    calibration = exp014.placebo_event_calibration(conf, draws=200, seed=exp014.SEED + 30)
    pm = json.loads((REPO / exp014.MID_MANIFEST).read_text())
    universe = json.loads((REPO / "data/manifests/mid_sample_universe.json").read_text())
    edgar = json.loads((REPO / "data/manifests/edgar_filings_v1.json").read_text())
    audit = edgar["validation"]["clock_audit"]
    wrong = 1.0 - audit["shares"]["utc_correct (+4/+5 h)"]
    result = {
        "label_free_counts": label_free, "size_calibration": calibration,
        "mid_panel": {"rows": pm["rows"], "dates": pm["dates"], "symbols": pm["symbols"], "securities": pm["securities"], "trusted_share": pm["identity"]["share_trusted"],
                      "identity_gate": pm["identity_gate"], "content_hash": pm["content_hash"], "universe_snapshots": universe["snapshots"], "universe_unique_members": universe["unique_members"],
                      "overlap_with_frozen_universe_ever": universe["overlap_with_frozen_universe_ever"]},
        "edgar_registry": {"companies": edgar["validation"]["companies"], "rows": edgar["validation"]["rows"], "share_registry_stamp_wrong": wrong, "clock_audit_shares": audit["shares"],
                           "amendments": edgar["validation"]["amendments"], "item_4_02_8k": edgar["validation"]["item_4_02_8k"]},
    }
    OUT.write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({"counts": {k: label_free[k] for k in ("confirmatory", "time_separate")}, "size_calibration": calibration}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
