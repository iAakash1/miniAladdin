"""Fold a completed experiment's evidence into the model registry.

## Registration is additive, never destructive

`ModelEntry.key` is ``model_id@version:label``, so re-registering the same model
after a second study would silently *replace* the first study's record. That is
exactly the failure the research ledger exists to prevent: a registry that shows
only the most recent numbers cannot be used to audit how many times a model was
measured, and a void result that has been overwritten is a void result nobody
can find.

So each study registers under its own ``version``, and the entries belonging to
a superseded study are retired with a reason rather than removed. EXP-002's
records stay in the file permanently, marked VOID, next to EXP-004's.

## Nothing here promotes anything

`register()` writes evidence. Promotion is `ModelRegistry.promote()`, which
evaluates the gates independently. This script deliberately does not call it:
EXP-004 produced no candidate that clears them, and the correct outcome of a
negative study is that the production count stays at zero.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from src.quant.models.registry import ModelEntry, ModelRegistry

logger = logging.getLogger("omnisignal.quant.scripts.register")

#: Registry ``version`` per study. A study's entries are addressable forever.
STUDY_VERSIONS: dict[str, str] = {"EXP-002": "1.0", "EXP-004": "2.0", "EXP-005": "3.0"}

#: Validation dates a regime needs before its metrics are quoted as evidence.
#:
#: Labels span 21 sessions and rebalances are 5 apart, so a regime's independent
#: block count is roughly ``dates * 5 / 21``. At 200 dates that is ~48 blocks —
#: thin, but enough for a t-statistic to mean something. Below it a regime
#: reports its count and the string INSUFFICIENT EVIDENCE, because a +2.0
#: t-statistic computed on nine dates is the single most cherry-pickable number
#: this pipeline produces.
REGIME_MIN_DATES = 200

VOID_REASON = (
    "VOID — study invalidated by the pandas.merge_asof index-reset defect "
    "(docs/PRE_HOLDOUT_AUDIT.md section 2). 12 of 39 features carried other "
    "rows' values. Retained, not deleted: the evaluations it consumed still "
    "count against the cumulative multiple-testing total."
)


def _flatten_backtest(raw: dict[str, Any]) -> dict[str, Any]:
    """Lift the backtest metrics to the top level of the stored block.

    The study nests them under ``metrics``; `CANDIDATE_THRESHOLDS` reads
    ``backtest["net_sharpe"]``. A nested value the threshold cannot find reads
    as "not recorded", which refuses promotion for the right reason by accident
    — and would just as happily let a bad number through if the default ever
    flipped. The detail blocks are kept alongside.
    """
    if not raw:
        return {}
    metrics = raw.get("metrics") or {}
    return {
        **metrics,
        "config": raw.get("config"),
        "periods": raw.get("periods"),
        "warnings": raw.get("warnings"),
    }


def _regime_stability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-regime metrics, keyed, with thin regimes refusing to report a number."""
    out: dict[str, Any] = {}
    for row in rows:
        dates = row.get("dates", 0)
        if dates < REGIME_MIN_DATES:
            out[row["regime"]] = {
                "dates": dates,
                "observations": row.get("observations"),
                "share": row.get("share"),
                "evidence": "INSUFFICIENT EVIDENCE",
                "why": f"{dates} validation dates is below the {REGIME_MIN_DATES} "
                       "required for a regime metric to be quoted.",
            }
            continue
        out[row["regime"]] = {**row, "evidence": "sufficient"}
    out["_floor_dates"] = REGIME_MIN_DATES
    return out


def _methodology(metrics: dict[str, Any], label: str) -> str:
    plan = metrics["labels"][label]["walk_forward_plan"]
    return (
        f"{plan['scheme']} walk-forward, {plan['fold_count']} folds, "
        f"{plan['train_sessions']} training / {plan['validation_sessions']} validation "
        f"sessions, purged by the {plan['label_horizon_sessions']}-session label horizon "
        f"and embargoed a further {plan['embargo_sessions']}. Execution lag "
        f"{metrics['experiment']['execution_lag_periods']} rebalance period(s). "
        f"Holdout {plan['holdout_start']} to {plan['holdout_end']} untouched."
    )


def _entry(
    metrics: dict[str, Any],
    label: str,
    row: dict[str, Any],
    *,
    experiment_id: str,
    version: str,
    artifact_root: Path,
) -> ModelEntry:
    model_id = row["model_id"]
    block = metrics["labels"][label]
    backtest = _flatten_backtest(block["backtests"].get(model_id, {}))
    significance = block["significance"].get(model_id, {})
    attribution = block["factor_attribution"].get(model_id, {})
    regimes = _regime_stability(block["regime_performance"].get(model_id, []))
    distribution = block["experiment_distribution"]
    spec = next(
        (m for m in metrics["experiment"]["models"] if m["name"] == model_id), {}
    )

    baselines = sorted(
        r["model_id"] for r in block["leaderboard"] if r["kind"] == "baseline"
    )
    # A constant predictor (`baseline_zero`) has no cross-sectional dispersion, so
    # its IC is undefined rather than zero. Treating an undefined IC as 0.0 would
    # invent a baseline to beat; it is excluded from the comparison instead.
    baseline_ics = [
        r["mean_ic"]
        for r in block["leaderboard"]
        if r["kind"] == "baseline" and r["mean_ic"] is not None
    ]
    best_baseline = max(baseline_ics) if baseline_ics else None
    own_ic = row["mean_ic"]
    beat_best = (
        None
        if own_ic is None or best_baseline is None
        else bool(own_ic > best_baseline)
    )

    return ModelEntry(
        model_id=model_id,
        version=version,
        task="cross_sectional_ranking" if label.startswith("fwd_rank") else "return_forecast",
        label=label,
        status="experimental",
        features=list(metrics["features_used"]),
        hyperparameters=dict(spec.get("params", {})),
        seed=int(spec.get("seed", metrics["experiment"]["seed"])),
        fingerprint=metrics["fingerprint"],
        dataset_version=metrics["dataset"]["dataset_version"],
        dataset_sources=list(metrics["dataset"]["source_datasets"]),
        training_start=metrics["dataset"]["start"],
        training_end=block["walk_forward_plan"]["folds"][-1]["validation_end"],
        validation_methodology=_methodology(metrics, label),
        walk_forward={
            "mean_ic": row["mean_ic"],
            "ic_t_stat": row["ic_t_stat"],
            "ic_ir": row["ic_ir"],
            "fold_ic_positive_rate": row["fold_ic_positive_rate"],
            "train_mean_ic": row["train_mean_ic"],
            "train_ic_gap": row["train_ic_gap"],
            "spearman": row["spearman"],
            "directional_edge": row["directional_edge"],
            "folds": row["folds"],
        },
        baseline_comparison={
            "baselines": baselines,
            "best_baseline_ic": best_baseline,
            "beat_best_baseline": beat_best,
        },
        backtest=backtest,
        factor_attribution=attribution,
        # Deliberately empty. The holdout is locked; an empty dict is what blocks
        # `promote(..., "production")`, and populating it would be a lie.
        holdout_metrics={},
        regime_stability=regimes,
        multiple_testing={
            "cumulative_trials": block["trials_used_for_correction"],
            "deflated_sharpe_probability": significance.get("deflated_sharpe_probability"),
            "probability_of_backtest_overfitting": block[
                "probability_of_backtest_overfitting"
            ].get("pbo"),
            "population_best_ic": distribution["best"],
            "population_median_ic": distribution["median"],
            "population_size": distribution["experiments"],
        },
        leakage_evidence={
            "truncation_invariance": "CLEAN" if metrics["integrity"]["clean"] else "FAILED",
            "rows_compared": metrics["integrity"]["rows_compared"],
            "columns_compared": metrics["integrity"]["columns_compared"],
            "cutoffs": metrics["integrity"]["cutoffs"],
            "blocking_controls_passed": not metrics["negative_controls"]["blocking_failed"],
            "controls": {
                c["control"]: {"mean_ic": c["mean_ic"], "t_stat": c["t_stat"],
                               "blocking": c["blocking"], "passed": c["passed"]}
                for c in metrics["negative_controls"]["controls"]
            },
        },
        stability_evidence={
            "fold_ic_positive_rate": row["fold_ic_positive_rate"],
            "train_ic_gap": row["train_ic_gap"],
            "fold_count": len(block["fold_rows"]),
        },
        turnover_evidence={
            "annualised_turnover": backtest.get("annualised_turnover"),
            "cost_share_of_gross": backtest.get("cost_share_of_gross"),
            "cost_sensitivity": block["cost_sensitivity"].get(model_id, {}),
        },
        reproducibility={
            "seed": metrics["experiment"]["seed"],
            "dataset_content_hash": metrics["dataset"]["content_hash"],
            "git_commit": metrics["git_commit"],
            "git_dirty": metrics["git_dirty"],
            "dependency_versions": metrics["dependency_versions"],
            "experiment_fingerprint": metrics["fingerprint"],
            "command": f"python -m src.quant.study.run --experiment {experiment_id}",
        },
        experiments_run=distribution["experiments"],
        git_commit=metrics["git_commit"],
        dependency_versions=metrics["dependency_versions"],
        artifact_path=str(artifact_root),
        notes=[f"{experiment_id}: {metrics['experiment']['objective']}"],
    )


def register_experiment(experiment_id: str, *, root: Path, registry_root: Path) -> dict[str, Any]:
    artifact_root = root / experiment_id
    metrics = json.loads((artifact_root / "metrics.json").read_text(encoding="utf-8"))
    version = STUDY_VERSIONS.get(experiment_id)
    if version is None:
        raise SystemExit(
            f"{experiment_id} has no assigned registry version. Add one to "
            "STUDY_VERSIONS rather than reusing another study's."
        )

    registry = ModelRegistry(registry_root)

    # Retire superseded studies first, so the void records carry their reason
    # before the replacement lands beside them.
    #
    # Only EXP-002's entries are retired, and only once. EXP-004 is a completed,
    # valid study whose negative result stands on its own; a later study does not
    # supersede it, and retiring it would misrepresent the register as showing one
    # current answer rather than a sequence of them.
    retired: list[str] = []
    if experiment_id != "EXP-002":
        for entry in registry.all():
            if entry.version != STUDY_VERSIONS["EXP-002"] or entry.status == "retired":
                continue
            if entry.dataset_version != "ds-e691b48ca49deb16":
                continue  # EXP-001, a different dataset; not in scope.
            registry.promote(entry.key, "retired", reason=VOID_REASON)
            retired.append(entry.key)

    written: list[str] = []
    for label, block in metrics["labels"].items():
        for row in block["leaderboard"]:
            if row.get("errors"):
                continue
            entry = _entry(
                metrics, label, row,
                experiment_id=experiment_id, version=version, artifact_root=artifact_root,
            )
            registry.register(entry)
            written.append(entry.key)

    registry.save()

    production = registry.by_status("production")
    if production:
        raise SystemExit(
            "production models present after registration: "
            f"{[e.key for e in production]}. Registration writes evidence and "
            "must never promote."
        )

    return {
        "experiment": experiment_id,
        "version": version,
        "registered": len(written),
        "retired_as_void": len(retired),
        "total_entries": len(registry.all()),
        "production": 0,
        "by_status": registry.summary(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", default="EXP-004")
    parser.add_argument("--root", default="experiments", type=Path)
    parser.add_argument("--registry-root", default="data/research/models", type=Path)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = register_experiment(
        args.experiment, root=args.root, registry_root=args.registry_root
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
