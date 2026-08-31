"""
Materialise a deployable artifact from a frozen experiment specification.

## Read this before using the artifact for anything

EXP-006 never persisted a fitted estimator, and neither did any earlier study.
`run_walk_forward` constructs a fresh model per fold through `model_factory()`
and discards it once the fold is scored — which is correct for research, because
the object of study is the *specification*, not any one fitted instance.

So there is no "the trained EXP-006 model" to load. This script produces one, and
the distinction it introduces has to travel with it:

* **What EXP-006 measured** is the out-of-sample behaviour of a specification —
  27 features, fixed hyperparameters, seed 0 — estimated from **eight separate
  fits**, each trained on an expanding window and scored on the fold after it.
  IC +0.0290, t +2.66, gross Sharpe +0.384, net Sharpe −0.102 describe that.
* **What this script builds** is a *single* fit of the same specification over
  the whole pre-holdout window. It is the object you would deploy. It is **not**
  the object those numbers were computed on, and no metric here is re-derived.

Reporting the walk-forward metrics as though they belonged to this artifact would
be a category error. `/model` therefore serves them clearly attributed to the
specification, alongside `fit_scope` describing this object.

## What this does not do

No hyperparameter is chosen, no feature is added, no threshold moves, no metric
is recomputed, and the holdout is never read — the fit window is truncated
strictly below the holdout start and the firewall is armed to enforce it.

    python -m scripts.quant.build_artifact --experiment EXP-006
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import sys
import time
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.datasets.store import RawStore
from src.quant.models.base import FoldImputer
from src.quant.models.factory import ModelSpec
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.study.experiment import get_experiment
from src.quant.study.families import FeatureArm, arm_features
from src.quant.study.firewall import FIREWALL

logger = logging.getLogger("omnisignal.quant.build_artifact")

DEFAULT_OUT = Path("artifacts")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build(
    experiment_id: str,
    model_id: str,
    *,
    root: Path,
    out: Path,
    seed: int = 0,
) -> dict[str, Any]:
    import joblib

    artifact_dir = Path("experiments") / experiment_id
    metrics = json.loads((artifact_dir / "metrics.json").read_text(encoding="utf-8"))
    definition = get_experiment(experiment_id, seed)

    recorded_hash = metrics["dataset"]["content_hash"]
    holdout_start = Date.fromisoformat(metrics["holdout"]["start"])
    target = definition.primary_target

    spec = next((s for s in definition.models if s.name == model_id), None)
    if spec is None:
        raise SystemExit(f"{model_id} is not in {experiment_id}'s model ladder")

    print(f"building deployable artifact for {model_id} from {experiment_id}")
    print(f"  target        {target}")
    print(f"  families      {definition.feature_families or '(all)'}")
    print(f"  seed          {spec.seed}")
    print(f"  holdout start {holdout_start} — fit window truncated strictly below it")

    store = RawStore(root)
    universe = UniverseHistory.load(Path(root) / "universe")
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start,
        end=definition.end or Date.today(),
        step_sessions=definition.step_sessions,
        workers=6,
    )
    frame, manifest = dataset.frame, dataset.manifest

    if manifest.content_hash != recorded_hash:
        raise SystemExit(
            f"dataset content hash moved ({recorded_hash} -> {manifest.content_hash}). "
            "The panel is not the one EXP-006 was run on, so an artifact built here "
            "would not correspond to the recorded evidence."
        )
    print(f"  dataset       {manifest.dataset_version} hash {manifest.content_hash} MATCHES")

    cross = [n for n in manifest.features if n.endswith("_xs")]
    macro = [n for n in manifest.features if n.startswith(("rates_", "market_"))]
    available = cross + macro
    if definition.feature_families:
        features = arm_features(
            FeatureArm("declared", definition.feature_families, "frozen in the definition"),
            available,
        )
    else:
        features = available
    print(f"  features      {len(features)}")

    # The firewall, armed explicitly. This script does not call `build_plan`, so
    # nothing else would declare the window — and a fit that silently included
    # holdout rows is exactly what it exists to prevent.
    FIREWALL.arm_window(holdout_start, Date.fromisoformat(metrics["holdout"]["end"]))

    usable = frame[frame["in_universe"]] if "in_universe" in frame.columns else frame
    usable = usable.dropna(subset=[target])
    fit_rows = usable[usable["date"] < holdout_start].copy()
    FIREWALL.assert_clear(fit_rows, context="deployable artifact fit window")

    if fit_rows.empty:
        raise SystemExit("no pre-holdout rows to fit on")

    X = fit_rows[features].to_numpy(dtype=float)
    y = fit_rows[target].to_numpy(dtype=float)
    print(f"  fit rows      {len(fit_rows):,}  "
          f"({fit_rows['date'].min()} → {fit_rows['date'].max()}, "
          f"{fit_rows['symbol'].nunique()} symbols)")

    began = time.perf_counter()
    model = spec.build()
    imputer = FoldImputer(standardise=model.requires_scaling)
    X_ready = imputer.fit_transform(X, feature_names=features)
    model.fit(X_ready, y, feature_names=features)
    elapsed = time.perf_counter() - began
    print(f"  fitted in     {elapsed:.1f}s")

    out.mkdir(parents=True, exist_ok=True)
    name = f"{model_id}@{experiment_id}"
    model_path = out / f"{name}.joblib"
    joblib.dump({"model": model, "imputer": imputer, "features": features}, model_path,
                compress=3)

    leader = next(
        r for r in metrics["labels"][target]["leaderboard"] if r["model_id"] == model_id
    )
    backtest = (metrics["labels"][target]["backtests"].get(model_id) or {}).get("metrics", {})
    attribution = (metrics["labels"][target]["factor_attribution"].get(model_id) or {})

    meta: dict[str, Any] = {
        "schema_version": 1,
        "artifact": model_path.name,
        "sha256": _sha256(model_path),
        "bytes": model_path.stat().st_size,
        "built_at": datetime.now(timezone.utc).isoformat(),

        "model_id": model_id,
        "model_version": "4.0",
        "registry_key": f"{model_id}@4.0:{target}",
        "experiment_id": experiment_id,
        "experiment_fingerprint": metrics["fingerprint"],
        "target": target,
        "horizon_sessions": 21,
        "rebalance_step_sessions": definition.step_sessions,

        "features": features,
        "feature_count": len(features),
        "feature_families": list(definition.feature_families),
        "preprocessing": "FoldImputer — median imputation, no standardisation for trees",

        "dataset_version": manifest.dataset_version,
        "dataset_content_hash": manifest.content_hash,
        "git_commit": metrics["git_commit"],
        "seed": spec.seed,
        "hyperparameters": spec.kwargs,
        "dependency_versions": metrics["dependency_versions"],
        "python": platform.python_version(),

        "fit_scope": {
            "rows": int(len(fit_rows)),
            "symbols": int(fit_rows["symbol"].nunique()),
            "start": str(fit_rows["date"].min()),
            "end": str(fit_rows["date"].max()),
            "training_cutoff": str(holdout_start),
            "note": (
                "ONE fit over the whole pre-holdout window. The EXP-006 metrics were "
                "estimated from EIGHT separate walk-forward fits and describe the "
                "SPECIFICATION, not this object."
            ),
        },

        "specification_metrics": {
            "source": f"{experiment_id} walk-forward, 8 expanding folds",
            "mean_ic": leader.get("mean_ic"),
            "ic_t_stat": leader.get("ic_t_stat"),
            "train_ic_gap": leader.get("train_ic_gap"),
            "gross_sharpe": backtest.get("gross_sharpe"),
            "net_sharpe": backtest.get("net_sharpe"),
            "alpha_t_stat": attribution.get("alpha_t_stat"),
            "annualised_turnover": backtest.get("annualised_turnover"),
            "half_spread_bps": 10.0,
            "execution_lag_periods": definition.execution_lag_periods,
            "cumulative_trials": metrics["labels"][target]["trials_used_for_correction"],
            "caveat": (
                "These describe the specification measured out-of-sample across folds. "
                "They are NOT a measurement of the artifact in this file."
            ),
        },

        "research_status": "EXPERIMENTAL",
        "promotion_status": "BLOCKED",
        "promotion_blocked_by": {
            "gate": "net_sharpe",
            "required": "> 0",
            "observed": backtest.get("net_sharpe"),
            "detail": (
                "Clears |IC t| >= 2, gross Sharpe > 0 and beats the best baseline. "
                "Fails net Sharpe at the declared 10 bp half-spread. Registry "
                "production count remains 0."
            ),
        },
        "holdout": {
            "start": metrics["holdout"]["start"],
            "end": metrics["holdout"]["end"],
            "touched": False,
            "contract_armed": False,
        },
        "usage": (
            "Research and evaluation only. This is not investment advice, not a "
            "trading signal, and not a production-promoted model. The output is a "
            "cross-sectional rank forecast, not a return and not a recommendation."
        ),
    }

    meta_path = out / f"{name}.metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    print(f"\n  artifact      {model_path}  ({meta['bytes'] / 1024:.0f} KB)")
    print(f"  sha256        {meta['sha256'][:16]}…")
    print(f"  metadata      {meta_path}")
    print(f"  status        {meta['research_status']} / promotion {meta['promotion_status']}")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="EXP-006")
    parser.add_argument("--model", default="gradient_boosting")
    parser.add_argument("--root", default="data/research", type=Path)
    parser.add_argument("--out", default=DEFAULT_OUT, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    build(args.experiment, args.model, root=args.root, out=args.out, seed=args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
