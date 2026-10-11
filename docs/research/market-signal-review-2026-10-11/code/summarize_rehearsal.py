#!/usr/bin/env python3
"""Summarise a label-shuffled rehearsal of EXP-012 into validation/rehearsal_summary.json.

The rehearsal runs every code path (all 30 fits, the analysis, the saved artifacts) on real features and the real folds with the label shuffled across firms within each
date, so it carries no information about the hypotheses. What it does give, legitimately and before the registered run, is (a) proof that the pipeline completes and returns
NOT_SUPPORTED on a world with no signal, and (b) the standard error of each paired contrast on this panel, from which the smallest detectable effect follows.

    python docs/research/market-signal-review-2026-10-11/code/summarize_rehearsal.py /tmp/exp012_rehearsal
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
Z_ALPHA = 1.6449          # one-sided 5%
Z_HOLM_FIRST = 2.1280     # one-sided 5% / 3, the strictest Holm step
Z_POWER = 0.8416          # 80% power


def main(out: Path) -> None:
    manifest = json.loads((out / "manifest.json").read_text())
    paired = pd.read_csv(out / "paired_tests.csv").set_index("contrast")
    checkpoints = sorted((out / "checkpoints").glob("*.parquet"))
    finite = sum(bool(np.isfinite(pd.read_parquet(p)["prediction"].to_numpy(dtype=float)).all()) for p in checkpoints)
    se = {}
    for name in ("T1", "T2", "T3"):
        row = paired.loc[name]
        s = abs(float(row["mean_diff"]) / float(row["hac_t"]))
        se[name] = {"standard_error": round(s, 6), "mde_80pct_power_single_test": round((Z_ALPHA + Z_POWER) * s, 6),
                    "mde_80pct_power_strictest_holm_step": round((Z_HOLM_FIRST + Z_POWER) * s, 6), "dates": int(row["dates"])}
    summary = {
        "what": "EXP-012 rehearsal on a label shuffled across firms within each date (seed 20261012); no information about the hypotheses",
        "completion": manifest["completion"], "fits": len(checkpoints), "prediction_files_finite": finite,
        "wall_seconds": manifest["compute"]["wall_seconds"], "workers": manifest["compute"]["workers"],
        "verdicts": {k: v["label"] for k, v in manifest["verdicts"].items()},
        "acceptance": manifest.get("acceptance"), "artifacts_written": sorted(Path(p).name for p in manifest["artifacts"].values()),
        "holdout": {"state": manifest["holdout"]["firewall"]["holdout_state"], "touched": manifest["holdout"]["touched"]},
        "contrast_standard_errors_null_world": se,
        "reading": "mde = (z_alpha + z_power) * SE with z_alpha 1.645 (single one-sided 5% test) or 2.128 (strictest Holm step over three tests) and z_power 0.842 (80% power). "
                   "The SE comes from the Newey-West t of the paired difference series in a world with no signal.",
    }
    (BASE / "validation" / "rehearsal_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
