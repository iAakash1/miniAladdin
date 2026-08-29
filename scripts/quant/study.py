"""
The research study — builds the dataset, runs every model, reports everything.

This is the script whose output is the finding. It is deliberately one linear
pass with no branching on results: the set of models and labels is fixed before
it runs, every combination is evaluated, and every outcome is written down.
There is no path in it that drops a configuration because it performed badly,
which is what makes `ExperimentLog.distribution()` a valid population rather
than a survivor list.

Usage::

    python -m scripts.quant.study --label fwd_ret_21 --step 5
    python -m scripts.quant.study --all-labels --out data/research/reports
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date as Date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.backtest.attribution import attribute_returns
from src.quant.backtest.costs import SimpleCostModel, sensitivity_grid
from src.quant.backtest.engine import BacktestConfig, run_backtest
from src.quant.datasets.store import RawStore
from src.quant.models.baselines import regression_baselines
from src.quant.models.linear import (
    ElasticNetRegression, LassoRegression, OrdinaryLeastSquares, RidgeRegression,
)
from src.quant.models.factory import ModelSpec, default_specs
from src.quant.models.registry import ModelEntry, ModelRegistry, dependency_versions, git_commit
from src.quant.models.trees import (
    ExtraTrees, GradientBoostedTrees, HistGradientBoosting, RandomForest,
)
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.regime import classify_clusters, classify_rules, compare_labellers, performance_by_regime
from src.quant.validation.parallel import evaluate_specs
from src.quant.validation.runner import ExperimentLog, run_walk_forward
from src.quant.validation.significance import (
    deflated_sharpe_ratio, minimum_track_record_length, probability_of_backtest_overfitting,
)
from src.quant.validation.progress import TrainingProgress, machine_profile
from src.quant.validation.walkforward import build_plan, fold_row_counts, verify_no_overlap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("study")

#: The model set, fixed before the study runs. Adding a model after seeing
#: results and reporting only the improvement is how a research record becomes
#: fiction; the list lives here so it is diffable.
def model_factories(seed: int = 0) -> dict[str, Any]:
    return {
        **{model.model_id: (lambda m=model: type(m)(**_ctor_args(m))) for model in regression_baselines(seed)},
        "ols": lambda: OrdinaryLeastSquares(seed=seed),
        "ridge": lambda: RidgeRegression(alpha=10.0, seed=seed),
        "lasso": lambda: LassoRegression(alpha=0.0005, seed=seed),
        "elastic_net": lambda: ElasticNetRegression(alpha=0.0005, l1_ratio=0.5, seed=seed),
        "gradient_boosting": lambda: GradientBoostedTrees(seed=seed),
        "random_forest": lambda: RandomForest(seed=seed),
        "hist_gradient_boosting": lambda: HistGradientBoosting(seed=seed),
        "extra_trees": lambda: ExtraTrees(seed=seed),
        # A deliberately over-parameterised tree, included as the overfitting
        # control on the tree side exactly as OLS is on the linear side. It is
        # expected to show a large train-versus-validation IC gap, and that gap
        # is the point: it demonstrates the diagnostic works on a model built to
        # trigger it, rather than asking the reader to take the diagnostic on trust.
        "gradient_boosting_deep": lambda: GradientBoostedTrees(
            seed=seed, max_depth=8, n_estimators=500, learning_rate=0.1,
            subsample=1.0, min_samples_leaf=5,
        ),
    }


def _ctor_args(model) -> dict[str, Any]:
    """Reconstruct a baseline from its recorded params, so factories are pure."""
    args = {"seed": model.seed}
    if "feature" in model.params:
        args["feature"] = model.params["feature"]
    if "sign" in model.params:
        args["sign"] = model.params["sign"]
    return args


DEFAULT_LABELS = ("fwd_ret_21", "fwd_rank_21", "fwd_vol_21", "fwd_ret_5")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the quantitative research study")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--out", default="data/research/reports")
    parser.add_argument("--start", default="2014-04-01")
    parser.add_argument("--end", default="")
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--all-labels", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--validation-sessions", type=int, default=252)
    parser.add_argument("--min-train-sessions", type=int, default=756)
    parser.add_argument(
        "--workers", type=int, default=-1,
        help="model-level parallelism; -1 sizes the pool against cores and free memory",
    )
    args = parser.parse_args()

    began = time.perf_counter()
    store = RawStore(args.root)
    universe = UniverseHistory.load(Path(args.root) / "universe")
    start = Date.fromisoformat(args.start)
    end = Date.fromisoformat(args.end) if args.end else Date.today()
    labels = list(args.label) if args.label else list(DEFAULT_LABELS if args.all_labels else ("fwd_ret_21",))

    # ── 1. dataset ───────────────────────────────────────────────────────
    logger.info("=== building point-in-time dataset ===")
    builder = DatasetBuilder(store, universe)
    dataset = builder.build(start=start, end=end, step_sessions=args.step, workers=args.workers)
    frame = dataset.frame
    logger.info(
        "dataset %s: %d rows, %d symbols, %d dates, %d features",
        dataset.manifest.dataset_version, len(frame),
        dataset.manifest.symbols, dataset.manifest.dates, len(dataset.features),
    )

    # Cross-sectional features only for cross-sectional work: the raw levels
    # are on wildly different scales across names and eras, and a model fed
    # both the level and its rank double-counts the same information.
    # Cross-sectional ranks plus macro levels. The raw per-symbol levels are
    # excluded deliberately: a model fed both `mom_63` and `mom_63_xs` receives
    # the same information twice, once on a scale that differs by name and era.
    cross_features = [name for name in dataset.features if name.endswith("_xs")]
    macro_names = [
        name for name in dataset.features if name.startswith(("rates_", "market_"))
    ]
    feature_set = cross_features + macro_names
    logger.info(
        "using %d features (%d cross-sectional + %d macro) | groups: %s",
        len(feature_set), len(cross_features), len(macro_names),
        {
            g: sum(1 for f in cross_features if f.startswith(p))
            for g, p in (("options", "opt_"), ("earnings", "earn_"))
        },
    )

    # ── 2. regimes ───────────────────────────────────────────────────────
    logger.info("=== classifying regimes ===")
    macro_frame = (
        frame[["date", *macro_names]].drop_duplicates("date").sort_values("date").reset_index(drop=True)
    )
    rules = classify_rules(macro_frame)
    try:
        clusters = classify_clusters(macro_frame)
        agreement = compare_labellers(rules, clusters)
    except Exception as error:  # noqa: BLE001 — reported, not hidden
        logger.warning("cluster regimes unavailable: %s", error)
        clusters, agreement = None, {"error": str(error)}
    logger.info("regime distribution: %s", rules.distribution())

    reports: dict[str, Any] = {}

    for label in labels:
        if label not in frame.columns:
            logger.warning("label %s absent from the dataset — skipped", label)
            continue
        logger.info("=== label %s ===", label)
        horizon = 21 if "21" in label else (5 if "_5" in label else 63)

        plan = build_plan(
            dataset.calendar, start=start, end=end,
            label_horizon_sessions=horizon,
            validation_sessions=args.validation_sessions,
            min_train_sessions=args.min_train_sessions,
        )
        overlap = verify_no_overlap(plan, frame)
        if not overlap["ok"]:
            logger.error("walk-forward overlap check FAILED: %s", overlap["problems"][:3])

        log = ExperimentLog(notes=[
            f"dataset {dataset.manifest.dataset_version}",
            f"{len(plan)} expanding folds, {plan.label_horizon_sessions}+{plan.embargo_sessions} session gap",
        ])
        specs = [
            spec for spec in default_specs(args.seed)
            # A passthrough baseline needs its feature present. Dropping the
            # spec is right when a data source is absent — constructing it would
            # fail every fold and report a failure that is really a missing
            # dataset.
            if spec.kind != "passthrough" or spec.kwargs.get("feature") in feature_set
        ]
        dropped = len(default_specs(args.seed)) - len(specs)
        if dropped:
            logger.info("%d baseline(s) dropped — their feature is absent from this build", dropped)

        progress = TrainingProgress(total_units=len(specs), label=f"{label}")
        results, failures, timing = evaluate_specs(
            specs, frame, plan,
            features=feature_set, label=label, step_sessions=args.step,
            workers=args.workers,
            on_complete=lambda name, result, error: progress.advance(
                detail=name,
                folds=len(result.folds) if result else None,
                ic=result.pooled_ic.get("mean_ic") if result else None,
            ),
        )
        for result in results:
            log.add(result)
        for failure in failures:
            log.notes.append(f"{failure['model']}: FAILED — {failure['error'][:200]}")
        timing.update(progress.finish(f"{len(results)}/{len(specs)} models"))

        leaderboard = log.leaderboard(label=label)
        distribution = log.distribution(label=label)
        logger.info("leaderboard for %s:", label)
        for row in leaderboard:
            logger.info(
                "  %-26s IC=%s  t=%s  fold+=%s  rmse/zero=%s",
                row["model_id"], _f(row["mean_ic"]), _f(row["ic_t_stat"]),
                _f(row["fold_ic_positive_rate"]), _f(row["rmse_vs_zero"]),
            )

        # ── 3. backtest every model that produced predictions ────────────
        backtests: dict[str, Any] = {}
        attributions: dict[str, Any] = {}
        regime_breakdowns: dict[str, Any] = {}
        cost_sweeps: dict[str, Any] = {}
        configuration_returns: dict[str, pd.Series] = {}

        factors = _safe_read(store, "french_factors_daily")
        returns_panel = frame[["date", "symbol", "dollar_volume", f"fwd_ret_{args.step}"]] \
            if f"fwd_ret_{args.step}" in frame.columns else None

        for result in log.results:
            if result.predictions is None or result.predictions.empty or returns_panel is None:
                continue
            try:
                backtest = run_backtest(
                    result.predictions, returns_panel,
                    config=BacktestConfig(rebalance_step_sessions=args.step),
                    forward_return_column=f"fwd_ret_{args.step}",
                )
            except Exception as error:  # noqa: BLE001
                logger.warning("backtest %s failed: %s", result.model_id, error)
                continue
            backtests[result.model_id] = backtest.as_dict()
            configuration_returns[result.model_id] = backtest.net_returns

            cost_sweeps[result.model_id] = _cost_sweep(
                result.predictions, returns_panel, args.step
            )
            if factors is not None:
                attribution = attribute_returns(
                    backtest.net_returns, factors,
                    periods_per_year=252 / args.step,
                    holding_periods=max(1, horizon // args.step),
                )
                attributions[result.model_id] = attribution.as_dict()
            regime_breakdowns[result.model_id] = performance_by_regime(
                result.predictions, rules, label=label
            )

        # ── 4. significance, corrected for how many were tried ───────────
        trials = len(log.results)
        trial_sharpes = [
            float(series.mean() / series.std(ddof=1))
            for series in configuration_returns.values()
            if len(series) > 2 and series.std(ddof=1) > 0
        ]
        significance: dict[str, Any] = {}
        for model_id, series in configuration_returns.items():
            significance[model_id] = {
                "deflated_sharpe": deflated_sharpe_ratio(
                    series.to_numpy(), trials=trials,
                    periods_per_year=252 / args.step, trial_sharpes=trial_sharpes,
                ).as_dict(),
                "minimum_track_record": minimum_track_record_length(series.to_numpy()),
            }
        pbo = _pbo(configuration_returns)

        reports[label] = {
            "label": label,
            "horizon_sessions": horizon,
            "walk_forward_plan": plan.as_dict(),
            "fold_rows": fold_row_counts(plan, frame),
            "overlap_check": overlap,
            "leaderboard": leaderboard,
            "experiment_distribution": distribution,
            "experiments": log.as_dict(),
            "backtests": backtests,
            "cost_sensitivity": cost_sweeps,
            "factor_attribution": attributions,
            "regime_performance": regime_breakdowns,
            "significance": significance,
            "probability_of_backtest_overfitting": pbo,
            "timing": timing,
        }

    # ── 5. registry ──────────────────────────────────────────────────────
    registry = ModelRegistry(Path(args.root) / "models")
    for label, report in reports.items():
        for row in report["leaderboard"]:
            model_id = row["model_id"]
            entry = ModelEntry(
                model_id=model_id,
                version="1.0",
                task="regression",
                label=label,
                features=feature_set,
                seed=args.seed,
                dataset_version=dataset.manifest.dataset_version,
                dataset_sources=dataset.manifest.source_datasets,
                training_start=str(start),
                training_end=str(end),
                validation_methodology=(
                    f"{len(report['walk_forward_plan']['folds'])}-fold expanding "
                    f"walk-forward, {report['horizon_sessions']}-session purge plus "
                    f"{report['walk_forward_plan']['embargo_sessions']}-session embargo, "
                    "untouched final holdout"
                ),
                walk_forward={
                    "mean_ic": row["mean_ic"],
                    "t_stat": row["ic_t_stat"],
                    "fold_positive_rate": row["fold_ic_positive_rate"],
                    "folds": row["folds"],
                },
                baseline_comparison={
                    "baselines": [
                        r["model_id"] for r in report["leaderboard"]
                        if r["model_id"].startswith("baseline_")
                    ],
                    "beat_best_baseline": _beats_baselines(row, report["leaderboard"]),
                },
                backtest=report["backtests"].get(model_id, {}).get("metrics", {}),
                factor_attribution=report["factor_attribution"].get(model_id, {}),
                regime_stability={"by_regime": report["regime_performance"].get(model_id, [])},
                experiments_run=report["experiment_distribution"].get("experiments", 0),
                git_commit=git_commit(),
                dependency_versions=dependency_versions(),
            )
            registry.register(entry)
    registry.save()

    # ── 6. write ─────────────────────────────────────────────────────────
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "git_commit": git_commit(),
        "dependency_versions": dependency_versions(),
        "seed": args.seed,
        "machine": machine_profile(),
        "dataset": dataset.manifest.as_dict(),
        "universe": universe.summary(),
        "features_used": feature_set,
        "regimes": {
            "rules": rules.as_dict(),
            "clusters": clusters.as_dict() if clusters else None,
            "agreement": agreement,
        },
        "labels": reports,
        "runtime_seconds": round(time.perf_counter() - began, 1),
        "registry": registry.summary(),
    }
    target = out_dir / "study.json"
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s (%.1f KB) in %.1fs", target, target.stat().st_size / 1024, payload["runtime_seconds"])

    _print_summary(payload)
    return 0


def _cost_sweep(predictions, returns_panel, step: int) -> list[dict[str, Any]]:
    """Net Sharpe across a range of spread assumptions.

    The spread is assumed, not observed, so a single net figure is a claim about
    the assumption as much as the strategy. The sweep shows where it stops
    surviving.
    """
    rows: list[dict[str, Any]] = []
    for cost_model in sensitivity_grid():
        try:
            result = run_backtest(
                predictions, returns_panel,
                config=BacktestConfig(rebalance_step_sessions=step, cost_model=cost_model),
                forward_return_column=f"fwd_ret_{step}",
            )
        except Exception:  # noqa: BLE001
            continue
        rows.append(
            {
                "half_spread_bps": cost_model.half_spread_bps,
                "net_sharpe": result.metrics.get("net_sharpe"),
                "net_cagr": result.metrics.get("net_cagr"),
                "gross_sharpe": result.metrics.get("gross_sharpe"),
                "annualised_turnover": result.metrics.get("annualised_turnover"),
            }
        )
    return rows


def _pbo(configuration_returns: dict[str, pd.Series]) -> dict[str, Any]:
    """PBO over every configuration that produced a return series."""
    if len(configuration_returns) < 2:
        return {"pbo": None, "note": "fewer than two configurations"}
    aligned = pd.DataFrame(configuration_returns).dropna()
    if aligned.empty or len(aligned) < 32:
        return {"pbo": None, "note": f"{len(aligned)} aligned periods is too few"}
    return probability_of_backtest_overfitting(aligned.to_numpy())


def _beats_baselines(row: dict[str, Any], leaderboard: list[dict[str, Any]]) -> Optional[bool]:
    baselines = [
        r["mean_ic"] for r in leaderboard
        if r["model_id"].startswith("baseline_") and isinstance(r.get("mean_ic"), (int, float))
    ]
    if not baselines or not isinstance(row.get("mean_ic"), (int, float)):
        return None
    return bool(row["mean_ic"] > max(baselines))


def _safe_read(store: RawStore, dataset_id: str):
    try:
        return store.read(dataset_id)
    except Exception as error:  # noqa: BLE001 — absence is reported, never faked
        logger.warning("%s unavailable: %s", dataset_id, error)
        return None


def _f(value: Any) -> str:
    return "n/a" if not isinstance(value, (int, float)) else f"{value:+.4f}"


def _print_summary(payload: dict[str, Any]) -> None:
    print("\n" + "=" * 78)
    print("STUDY SUMMARY")
    print("=" * 78)
    dataset = payload["dataset"]
    print(f"dataset {dataset['dataset_version']}: {dataset['rows']:,} rows, "
          f"{dataset['symbols']} symbols, {dataset['dates']} dates, "
          f"{dataset['start']} to {dataset['end']}")
    print(f"guards: {dataset['guard_report']['total'] - dataset['guard_report']['failed']}"
          f"/{dataset['guard_report']['total']} passed")
    for label, report in payload["labels"].items():
        print(f"\n--- {label} ({report['horizon_sessions']}-session horizon, "
              f"{len(report['walk_forward_plan']['folds'])} folds) ---")
        print(f"{'model':<26}{'val IC':>9}{'train IC':>10}{'gap':>8}{'t':>7}{'fold+':>7}{'netSR':>8}{'alpha t':>9}{'DSR p':>7}")
        for row in report["leaderboard"]:
            model_id = row["model_id"]
            backtest = report["backtests"].get(model_id, {}).get("metrics", {})
            attribution = report["factor_attribution"].get(model_id, {})
            significance = report["significance"].get(model_id, {}).get("deflated_sharpe", {})
            print(
                f"{model_id:<26}{_f(row['mean_ic']):>9}{_f(row.get('train_mean_ic')):>10}"
                f"{_f(row.get('train_ic_gap')):>8}{_f(row['ic_t_stat']):>7}"
                f"{_f(row['fold_ic_positive_rate']):>7}{_f(backtest.get('net_sharpe')):>8}"
                f"{_f(attribution.get('alpha_t_stat')):>9}"
                f"{_f(significance.get('deflated_probability')):>7}"
            )
        dist = report["experiment_distribution"]
        print(f"  experiments: {dist.get('experiments')}, best {_f(dist.get('best'))}, "
              f"median {_f(dist.get('median'))}, above zero {dist.get('above_zero')}")
        pbo = report["probability_of_backtest_overfitting"].get("pbo")
        print(f"  PBO: {_f(pbo)}")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
