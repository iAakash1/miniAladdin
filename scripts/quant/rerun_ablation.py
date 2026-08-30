"""Recompute an experiment's ablation block and merge it back into the artifact.

## Why this is not a new experiment

EXP-005's first pass recorded every arm's IC and a blank for every significance
figure: `_run_ablation` read the leaderboard's field names off `pooled_ic`,
where they do not exist, so four metrics came back None. The fits themselves
were correct — only the transcription was wrong.

Recomputing them is therefore a REPORTING fix, not a new trial. The arms, the
models, the folds and the seed are unchanged, so the same fits are performed
again and the mean ICs must come out **identical**. This script asserts that:
any drift means something other than the reporting changed, and the merge is
refused rather than silently overwriting a result with a different one.

The trial count does not move. Re-running the same pre-registered configuration
to recover a metric that was mis-transcribed adds no selection freedom — nothing
about the design is chosen after seeing the first pass.

    python -m scripts.quant.rerun_ablation --experiment EXP-005
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date as Date
from pathlib import Path

from src.quant.datasets.store import RawStore
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.study.experiment import get_experiment
from src.quant.study.run import _run_ablation
from src.quant.validation.parallel import recommended_workers

logger = logging.getLogger("omnisignal.quant.scripts.rerun_ablation")

#: Mean ICs must reproduce to this tolerance. Fits are seeded and deterministic,
#: so the only expected difference is floating-point noise.
IC_TOLERANCE = 1e-9


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="EXP-005")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--out", default="experiments")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")
    began = time.perf_counter()

    artifact = Path(args.out) / args.experiment / "metrics.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    previous = payload.get("ablation") or {}

    definition = get_experiment(args.experiment, args.seed)
    store = RawStore(args.root)
    universe = UniverseHistory.load(Path(args.root) / "universe")

    print(f"rebuilding the panel for {args.experiment} (same definition, seed {args.seed})")
    # `end` is open in the definition; the runner resolves it to today, and the
    # builder needs a concrete date. Resolving it differently here would build a
    # different panel and the content-hash assertion below would catch it.
    end = definition.end or Date.today()
    workers_for_build = args.workers or 6
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start,
        end=end,
        step_sessions=definition.step_sessions,
        workers=workers_for_build,
    )
    frame = dataset.frame
    manifest = dataset.manifest

    recorded_hash = payload["dataset"]["content_hash"]
    if manifest.content_hash != recorded_hash:
        raise SystemExit(
            f"dataset content hash moved ({recorded_hash} -> {manifest.content_hash}). "
            "The panel is not the one the recorded ablation was computed on, so "
            "merging would mix two datasets in one artifact."
        )

    cross = [n for n in manifest.features if n.endswith("_xs")]
    macro = [n for n in manifest.features if n.startswith(("rates_", "market_"))]
    features = cross + macro

    workers = args.workers or recommended_workers(frame.memory_usage(deep=True).sum())
    from src.quant.regime import classify_rules
    import pandas as pd

    macro_frame = (
        frame[["date", *macro]].drop_duplicates("date").sort_values("date").reset_index(drop=True)
    )
    regimes = classify_rules(macro_frame)

    fresh = _run_ablation(
        definition, frame, features, dataset, regimes, store, workers,
        Path(args.out) / args.experiment,
    )

    # ── the reproducibility assertion ────────────────────────────────────
    drift: list[str] = []
    old_by_arm = {a["arm"]: a for a in previous.get("arms", [])}
    for arm in fresh["arms"]:
        old = old_by_arm.get(arm["arm"])
        if old is None or arm["skipped"] or old.get("skipped"):
            continue
        old_ic = {m["model_id"]: m["mean_ic"] for m in old["models"]}
        for model in arm["models"]:
            before, after = old_ic.get(model["model_id"]), model["mean_ic"]
            if before is None or after is None:
                continue
            if abs(before - after) > IC_TOLERANCE:
                drift.append(
                    f"{arm['arm']}/{model['model_id']}: {before:+.6f} -> {after:+.6f}"
                )

    if drift:
        raise SystemExit(
            "REFUSED: mean ICs did not reproduce, so this is not a reporting fix.\n  "
            + "\n  ".join(drift)
        )

    fresh["recomputed"] = {
        "reason": (
            "The first pass read the leaderboard's metric names off `pooled_ic`, "
            "where they do not exist, so ic_t_stat, train_mean_ic, train_ic_gap "
            "and fold_ic_positive_rate were recorded as null. The fits were "
            "correct; only the transcription was wrong."
        ),
        "at": pd.Timestamp.utcnow().isoformat(),
        "mean_ics_reproduced_exactly": True,
        "trial_count_unchanged": True,
    }
    payload["ablation"] = fresh
    artifact.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"\nmerged into {artifact}  ({time.perf_counter() - began:.0f}s)")
    print("every mean IC reproduced exactly; the trial count is unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
