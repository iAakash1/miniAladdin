"""
Experiment runner — one command, a frozen definition, and a persisted artifact.

    python -m src.quant.study.run --experiment EXP-004

Everything the run needs is in the `ExperimentDefinition`; nothing is passed on
the command line that could change the science. `--workers` and `--out` are
operational, and the fingerprint deliberately does not include them.

## The order of operations is the argument

1. Build the point-in-time matrix.
2. **Verify integrity** — truncation invariance against the real builder. A
   failure aborts before a single model is fitted, because a result from a
   contaminated matrix is not worth producing.
3. Run the **negative controls** on the primary target. A control that finds
   signal aborts the run for the same reason.
4. Only then evaluate the declared models.
5. Backtest with the declared execution lag, sweep the declared spreads,
   attribute against the factor model, break out by regime.
6. Apply the multiple-testing correction against the **cumulative** ledger
   count, not this study's own.

Steps 2 and 3 come before step 4 on purpose. Running them afterwards would mean
discovering that the numbers are meaningless only after they exist, at which
point somebody has already read them.
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

from src.quant.audit.contamination import compare_overlapping, summarise as summarise_contamination
from src.quant.backtest.attribution import attribute_returns
from src.quant.backtest.costs import SimpleCostModel
from src.quant.backtest.engine import BacktestConfig, run_backtest
from src.quant.datasets.store import RawStore
from src.quant.models.registry import dependency_versions
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.labels.geometry import LabelGeometry
from src.quant.regime import classify_rules, performance_by_regime
from src.quant.study.firewall import FIREWALL
from src.quant.study.families import FeatureArm, arm_features, family_members
from src.quant.study.experiment import ExperimentDefinition, get_experiment, git_commit, git_dirty
from src.quant.validation import controls as negative_controls
from src.quant.validation.parallel import evaluate_specs
from src.quant.validation.progress import TrainingProgress, machine_profile
from src.quant.validation.runner import ExperimentLog
from src.quant.validation.significance import (
    deflated_sharpe_ratio, minimum_track_record_length, probability_of_backtest_overfitting,
)
from src.quant.validation.walkforward import build_plan, fold_row_counts, verify_no_overlap

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", stream=sys.stdout,
)
logger = logging.getLogger("study.run")


class ExperimentAborted(RuntimeError):
    """Raised when an integrity gate fails. The run stops before fitting."""


def _horizon(label: str) -> int:
    from src.quant.labels import get as get_label

    return get_label(label).horizon_sessions


def run_experiment(
    definition: ExperimentDefinition,
    *,
    root: str = "data/research",
    out_root: str = "experiments",
    workers: int = 6,
    skip_integrity: bool = False,
) -> dict[str, Any]:
    began = time.perf_counter()
    output = Path(out_root) / definition.experiment_id
    output.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"{definition.experiment_id}  fingerprint {definition.fingerprint()}")
    print("=" * 78)
    print(f"  objective     {definition.objective[:100]}...")
    print(f"  git           {git_commit()[:12]}{' (DIRTY)' if git_dirty() else ''}")
    print(f"  targets       {definition.targets}  primary={definition.primary_target}")
    print(f"  models        {len(definition.models)}")
    print(f"  evaluations   {definition.declared_evaluations} declared, "
          f"{definition.prior_evaluations} prior, {definition.cumulative_evaluations} cumulative")
    print(f"  execution lag {definition.execution_lag_periods} rebalance period(s)")
    print(f"  cost sweep    {definition.cost_half_spreads_bps} bp, primary "
          f"{definition.primary_half_spread_bps} bp")
    print(f"  seed          {definition.seed}")
    machine = machine_profile()
    print(f"  machine       {machine.get('cpu_brand') or machine.get('machine')} · "
          f"{machine.get('logical_cpus')} cores · {workers} workers")
    print("=" * 78)

    store = RawStore(root)
    universe = UniverseHistory.load(Path(root) / "universe")
    end = definition.end or Date.today()

    # ── 1. dataset ───────────────────────────────────────────────────────
    print("\n[1/6] building point-in-time dataset")
    builder = DatasetBuilder(store, universe)
    dataset = builder.build(
        start=definition.start, end=end,
        step_sessions=definition.step_sessions, workers=workers,
    )
    frame, manifest = dataset.frame, dataset.manifest
    print(f"      {manifest.rows:,} rows · {manifest.symbols} symbols · {manifest.dates} dates")
    print(f"      dataset {manifest.dataset_version}  hash {manifest.content_hash}")
    print(f"      guards {manifest.guard_report['total'] - manifest.guard_report['failed']}"
          f"/{manifest.guard_report['total']}")

    cross = [n for n in manifest.features if n.endswith("_xs")]
    macro = [n for n in manifest.features if n.startswith(("rates_", "market_"))]
    features = cross + macro

    # A definition may freeze the feature set to named families. This is how a
    # follow-up study re-tests a specification an earlier ablation surfaced,
    # without the families being re-chosen after seeing results — they are named
    # in the frozen definition and hashed into the fingerprint.
    if definition.feature_families:
        restricted = arm_features(
            FeatureArm("declared", definition.feature_families, "frozen in the definition"),
            features,
        )
        if not restricted:
            raise ValueError(
                f"feature_families {definition.feature_families} matched no column in "
                "the built matrix; refusing to run on an empty feature set"
            )
        print(f"      feature families {definition.feature_families} -> "
              f"{len(restricted)} of {len(features)} columns")
        features = restricted
    print(f"      features {len(features)} used ({len(cross)} cross-sectional + {len(macro)} macro)")

    # ── 2. integrity ─────────────────────────────────────────────────────
    # ── holdout isolation, asserted before anything else ─────────────────
    #
    # The holdout rows exist in `frame` -- they must, or `build_plan` could not
    # carve the period out of the calendar. What matters is that no fold, no
    # fit and no metric ever reaches them. That is asserted here rather than
    # assumed, and the assertion runs before a single model is constructed.
    holdout_probe = build_plan(
        dataset.calendar, start=definition.start, end=end,
        label_horizon_sessions=_horizon(definition.primary_target),
        validation_sessions=definition.validation_sessions,
        min_train_sessions=definition.min_train_sessions,
        embargo_sessions=definition.embargo_sessions,
        holdout_sessions=definition.holdout_sessions,
    )
    holdout_start = holdout_probe.holdout_start
    reaching = [
        fold.index for fold in holdout_probe.folds
        if holdout_start and fold.validation_end >= holdout_start
    ]
    if reaching:
        raise ExperimentAborted(
            f"fold(s) {reaching} validate into the holdout beginning {holdout_start}"
        )
    print(f"      holdout {holdout_start} -> {holdout_probe.holdout_end} "
          f"({definition.holdout_sessions} sessions) LOCKED; "
          f"last fold ends {holdout_probe.folds[-1].validation_end}")

    integrity: dict[str, Any] = {"skipped": skip_integrity}
    if not skip_integrity:
        print("\n[2/6] verifying truncation invariance against the real builder")
        span = (end - definition.start).days
        cutoffs = [definition.start + pd.Timedelta(days=int(span * f)).to_pytimedelta()
                   for f in (0.55, 0.75, 0.90)]
        # Never build a matrix that extends into the holdout, even though doing
        # so would fit nothing and score nothing. The cheapest way to guarantee
        # the holdout is untouched is not to read it.
        if holdout_start:
            cutoffs = [c for c in cutoffs if c < holdout_start]
            if not cutoffs:
                raise ExperimentAborted("no integrity cutoff falls before the holdout")
        comparisons = []
        for cutoff in cutoffs:
            truncated = builder.build(
                start=definition.start, end=cutoff,
                step_sessions=definition.step_sessions, workers=workers,
            )
            result = compare_overlapping(
                frame[frame["date"] <= cutoff],
                truncated.frame[truncated.frame["date"] <= cutoff],
                manifest.features, label=f"truncate@{cutoff}",
            )
            print(f"      {cutoff}: {result.rows_compared:,} rows x {result.columns_compared} "
                  f"features -> {'CLEAN' if result.clean else 'CONTAMINATED'}")
            comparisons.append(result)
        integrity = summarise_contamination(comparisons)
        integrity["cutoffs"] = [str(c) for c in cutoffs]
        if not integrity["clean"]:
            raise ExperimentAborted(
                "dataset failed truncation invariance; refusing to fit any model. "
                f"{integrity['failed'][:2]}"
            )
    else:
        print("\n[2/6] integrity check SKIPPED (operational flag; not valid for a reported run)")

    # ── 3. regimes ───────────────────────────────────────────────────────
    macro_frame = frame[["date", *macro]].drop_duplicates("date").sort_values("date").reset_index(drop=True)
    regimes = classify_rules(macro_frame)
    print(f"\n[3/6] regimes {regimes.distribution()}")

    # ── 4. negative controls, on the primary target ──────────────────────
    control_report: dict[str, Any] = {"skipped": not definition.run_negative_controls}
    if definition.run_negative_controls:
        print(f"\n[4/6] negative controls on {definition.primary_target}")
        control_report = _run_controls(definition, frame, features, workers, dataset.calendar)
        for entry in control_report["controls"]:
            role = "blocking" if entry["blocking"] else "diagnostic"
            if entry["passed"]:
                verdict = "PASS"
            else:
                verdict = "FAIL" if entry["blocking"] else "FINDING"
            print(f"      {entry['control']:<26} IC {_f(entry['mean_ic'])}  t {_f(entry['t_stat'])}"
                  f"  ({role}) -> {verdict}")
        if control_report.get("diagnostic_findings"):
            print(f"      note: {control_report['interpretation']}")
        if not control_report["all_passed"]:
            raise ExperimentAborted(
                "a BLOCKING negative control produced signal on a target it cannot "
                f"predict; the pipeline manufactures skill. Failed: "
                f"{control_report['blocking_failed']}"
            )
    else:
        print("\n[4/6] negative controls SKIPPED")

    # ── 5. the declared models ───────────────────────────────────────────
    print(f"\n[5/6] evaluating {len(definition.models)} models x {len(definition.targets)} targets")
    labels_report: dict[str, Any] = {}
    for target in definition.targets:
        labels_report[target] = _evaluate_target(
            definition, target, frame, features, dataset, regimes, store, workers, output,
        )

    # ── 5b. ablation arms ────────────────────────────────────────────────
    ablation = _run_ablation(
        definition, frame, features, dataset, regimes, store, workers, output,
    )

    # ── 6. artifact ──────────────────────────────────────────────────────
    payload = {
        "experiment": definition.as_dict(),
        "fingerprint": definition.fingerprint(),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "machine": machine,
        "workers": workers,
        "dependency_versions": dependency_versions(),
        "dataset": manifest.as_dict(),
        "universe": universe.summary(),
        "features_used": features,
        "integrity": integrity,
        "holdout": {
            "start": str(holdout_start) if holdout_start else None,
            "end": str(holdout_probe.holdout_end) if holdout_probe.holdout_end else None,
            "sessions": definition.holdout_sessions,
            "touched": False,
            "last_fold_validation_end": str(holdout_probe.folds[-1].validation_end),
            "note": (
                "Holdout rows exist in the built matrix because the calendar must "
                "contain them for the period to be reserved. No fold, fit, metric or "
                "integrity cutoff reaches them; asserted before any model is constructed."
            ),
        },
        "negative_controls": control_report,
        "regimes": regimes.as_dict(),
        "labels": labels_report,
        "ablation": ablation,
        "firewall": FIREWALL.status(),
        "runtime_seconds": round(time.perf_counter() - began, 1),
    }
    (output / "metrics.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (output / "config.json").write_text(
        json.dumps(definition.as_dict(), indent=2, default=str), encoding="utf-8")
    (output / "dataset_manifest.json").write_text(
        json.dumps(manifest.as_dict(), indent=2, default=str), encoding="utf-8")

    print(f"\n[6/6] wrote {output}/metrics.json  ({(output / 'metrics.json').stat().st_size / 1024:.0f} KB)")
    _print_summary(payload)
    return payload


def _run_controls(
    definition: ExperimentDefinition,
    frame: pd.DataFrame,
    features: list[str],
    workers: int,
    calendar: Any,
) -> dict[str, Any]:
    """Run the ladder's most flexible model against randomised targets.

    The most flexible model, not the simplest: a control is meant to expose a
    pipeline that can manufacture signal, and the model most able to do that is
    the one that should be asked.
    """
    # The calendar is passed in, not rebuilt from `frame`. `frame` is STRIDED --
    # every fifth session -- so a calendar derived from it has 625 dates rather
    # than the ~3,100 the fold geometry is defined over, and `build_plan` would
    # either refuse or, worse, silently produce different folds for the controls
    # than for the models. A control evaluated on different folds is not a
    # control for anything.
    target = definition.primary_target
    horizon = _horizon(target)
    plan = build_plan(
        calendar, start=definition.start, end=max(frame["date"]),
        label_horizon_sessions=horizon,
        validation_sessions=definition.validation_sessions,
        min_train_sessions=definition.min_train_sessions,
        embargo_sessions=definition.embargo_sessions,
        holdout_sessions=definition.holdout_sessions,
    )
    probe = [s for s in definition.models if s.kind == "gradient_boosting"][:1]
    if not probe:
        probe = [definition.models[-1]]

    variants = [
        ("shuffled_within_date",
         "target permuted within each date; features and per-date margins intact",
         negative_controls.shuffle_within_date(frame, target, seed=definition.seed)),
        ("shifted_forward",
         "target replaced by one further ahead than the label horizon",
         negative_controls.shift_target_forward(frame, target, periods=4)),
        ("permuted_symbols",
         "targets reassigned between symbols on the same date",
         negative_controls.permute_symbols_within_date(frame, target, seed=definition.seed)),
    ]

    outcomes = []
    for name, description, mutated in variants:
        results, failures, _ = evaluate_specs(
            probe, mutated, plan, features=features, label=target,
            step_sessions=definition.step_sessions, workers=min(workers, 2),
        )
        if not results:
            outcomes.append(negative_controls.ControlOutcome(
                name=name, description=description, mean_ic=None, t_stat=None,
                observations=0, notes=[f"control failed to run: {failures}"],
            ))
            continue
        outcomes.append(negative_controls.assess(name, description, results[0]))
    return negative_controls.summarise(outcomes)


def _evaluate_target(
    definition: ExperimentDefinition,
    target: str,
    frame: pd.DataFrame,
    features: list[str],
    dataset: Any,
    regimes: Any,
    store: RawStore,
    workers: int,
    output: Path,
) -> dict[str, Any]:
    horizon = _horizon(target)
    plan = build_plan(
        dataset.calendar, start=definition.start, end=max(frame["date"]),
        label_horizon_sessions=horizon,
        validation_sessions=definition.validation_sessions,
        min_train_sessions=definition.min_train_sessions,
        embargo_sessions=definition.embargo_sessions,
        holdout_sessions=definition.holdout_sessions,
    )
    overlap = verify_no_overlap(plan, frame)
    print(f"\n  --- {target} ({horizon}d, {len(plan)} folds, gap "
          f"{horizon + definition.embargo_sessions}) ---")

    specs = [
        spec for spec in definition.models
        if spec.kind != "passthrough" or spec.kwargs.get("feature") in features
    ]
    progress = TrainingProgress(total_units=len(specs), label=target)
    results, failures, timing = evaluate_specs(
        specs, frame, plan, features=features, label=target,
        step_sessions=definition.step_sessions, workers=workers,
        on_complete=lambda name, result, error: progress.advance(
            detail=name,
            folds=len(result.folds) if result else None,
            ic=result.pooled_ic.get("mean_ic") if result else None,
        ),
    )
    timing.update(progress.finish(f"{len(results)}/{len(specs)}"))

    log = ExperimentLog()
    for result in results:
        log.add(result)

    forward_column = f"fwd_ret_{definition.step_sessions}"
    returns_panel = (
        frame[["date", "symbol", "dollar_volume", forward_column]]
        if forward_column in frame.columns else None
    )
    factors = _safe_read(store, "french_factors_daily")

    backtests, sweeps, attributions, regime_rows, series = {}, {}, {}, {}, {}
    for result in results:
        if result.predictions is None or result.predictions.empty or returns_panel is None:
            continue
        primary = _backtest(
            result.predictions, returns_panel, definition,
            definition.primary_half_spread_bps, forward_column,
        )
        if primary is None:
            continue
        backtests[result.model_id] = primary.as_dict()
        series[result.model_id] = primary.net_returns
        sweeps[result.model_id] = [
            {
                "half_spread_bps": bps,
                **{k: swept.metrics.get(k) for k in
                   ("gross_sharpe", "net_sharpe", "net_cagr", "annualised_turnover",
                    "cost_share_of_gross", "net_max_drawdown", "hit_rate")},
            }
            for bps in definition.cost_half_spreads_bps
            if (swept := _backtest(result.predictions, returns_panel, definition, bps, forward_column))
        ]
        if factors is not None:
            attributions[result.model_id] = attribute_returns(
                primary.net_returns, factors,
                periods_per_year=252 / definition.step_sessions,
                # Ceiling. `horizon // step` leaves one overlapping observation
                # uncorrected, and the residual dependence inflates the alpha
                # t-statistic. LabelGeometry.block_length is the same arithmetic
                # `ic_summary` already uses for its own lag count.
                holding_periods=LabelGeometry(
                    target=target, horizon_sessions=horizon,
                    step_sessions=definition.step_sessions, embargo_sessions=0,
                ).block_length,
            ).as_dict()
        regime_rows[result.model_id] = performance_by_regime(
            result.predictions, regimes, label=target,
            horizon_sessions=horizon, step_sessions=definition.step_sessions,
        )

    trials = definition.cumulative_evaluations
    trial_sharpes = [
        float(s.mean() / s.std(ddof=1)) for s in series.values()
        if len(s) > 2 and s.std(ddof=1) > 0
    ]
    significance = {
        model_id: {
            "deflated_sharpe": deflated_sharpe_ratio(
                s.to_numpy(), trials=trials,
                periods_per_year=252 / definition.step_sessions,
                trial_sharpes=trial_sharpes,
            ).as_dict(),
            "minimum_track_record": minimum_track_record_length(s.to_numpy()),
        }
        for model_id, s in series.items()
    }
    pbo = _pbo(series)

    leaderboard = log.leaderboard(label=target)
    for row in leaderboard:
        row["kind"] = "baseline" if row["model_id"].startswith("baseline_") else "learned"

    if results and results[0].predictions is not None:
        pd.concat(
            [r.predictions.assign(model=r.model_id) for r in results if r.predictions is not None],
            ignore_index=True,
        ).to_parquet(output / f"predictions_{target}.parquet", compression="zstd")
    if backtests:
        pd.DataFrame([
            {"model": m, **{k: v for k, v in b["metrics"].items() if not isinstance(v, (dict, list))}}
            for m, b in backtests.items()
        ]).to_parquet(output / f"portfolio_{target}.parquet", compression="zstd")
    pd.DataFrame(fold_row_counts(plan, frame)).to_parquet(
        output / f"folds_{target}.parquet", compression="zstd")

    return {
        "label": target,
        "horizon_sessions": horizon,
        "walk_forward_plan": plan.as_dict(),
        "fold_rows": fold_row_counts(plan, frame),
        "overlap_check": overlap,
        "leaderboard": leaderboard,
        "experiment_distribution": log.distribution(label=target),
        "experiments": log.as_dict(),
        "failures": failures,
        "backtests": backtests,
        "cost_sensitivity": sweeps,
        "factor_attribution": attributions,
        "regime_performance": regime_rows,
        "significance": significance,
        "probability_of_backtest_overfitting": pbo,
        "trials_used_for_correction": trials,
        "timing": timing,
    }


#: A configuration must trade at least this many periods to enter the PBO
#: matrix. Constant-prediction baselines form a quantile book on only a handful
#: of dates, and inner-joining them against the rest collapses the matrix to
#: nothing — which is how PBO silently became "not computed" rather than a
#: number. They are excluded and named instead.
MIN_PBO_PERIODS = 60


def _run_ablation(
    definition: ExperimentDefinition,
    frame: pd.DataFrame,
    features: list[str],
    dataset: Any,
    regimes: Any,
    store: RawStore,
    workers: int,
    output: Path,
) -> dict[str, Any]:
    """Refit a reduced model ladder once per pre-registered feature arm.

    The contrast that matters is arm-minus-base, so every arm runs on the same
    folds, the same seed and the same models. Only the feature columns change.

    An arm whose families are entirely absent from the built matrix — options
    before 2019, say, or fundamentals if the calendar failed to load — is
    SKIPPED and reported as skipped. Running it on a silently-empty column set
    would produce a number that looks like evidence of nothing when it is
    actually evidence of nothing having been measured.
    """
    if not definition.arms or not definition.arm_models:
        return {"ran": False, "reason": "no arms declared", "arms": []}

    target = definition.primary_target
    horizon = _horizon(target)
    plan = build_plan(
        dataset.calendar, start=definition.start, end=max(frame["date"]),
        label_horizon_sessions=horizon,
        validation_sessions=definition.validation_sessions,
        min_train_sessions=definition.min_train_sessions,
        embargo_sessions=definition.embargo_sessions,
        holdout_sessions=definition.holdout_sessions,
    )

    print(f"\n[5b] ablation: {len(definition.arms)} arms x "
          f"{len(definition.arm_models)} models on {target}")

    rows: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}

    for arm in definition.arms:
        columns = arm_features(arm, features)
        missing = [f for f in arm.families if not family_members(f, features)]
        coverage[arm.name] = {
            "features": len(columns),
            "families": list(arm.families),
            "families_absent": missing,
        }
        if not columns:
            print(f"  {arm.name:22s} SKIPPED — no features present")
            rows.append({
                "arm": arm.name, "families": list(arm.families),
                "hypothesis": arm.hypothesis, "skipped": True,
                "reason": "no features present in the built matrix",
                "feature_count": 0, "models": [],
            })
            continue

        progress = TrainingProgress(
            total_units=len(definition.arm_models), label=f"{arm.name}",
        )
        results, failures, timing = evaluate_specs(
            list(definition.arm_models), frame, plan,
            features=columns, label=target,
            step_sessions=definition.step_sessions, workers=workers,
            on_complete=lambda name, result, error: progress.advance(
                detail=name,
                folds=len(result.folds) if result else None,
                ic=result.pooled_ic.get("mean_ic") if result else None,
            ),
        )
        timing.update(progress.finish(f"{len(results)}/{len(definition.arm_models)}"))

        # These key names are NOT interchangeable with the ones on `pooled_ic`.
        # `ExperimentLog.leaderboard` reads `t_stat` (not `ic_t_stat`) and pulls
        # the train IC and fold rate from `result.stability(...)`. Reading the
        # leaderboard's names off `pooled_ic` silently yields None for all four,
        # which is how EXP-005's first pass recorded arm ICs with no significance
        # beside them — a mistake that is invisible unless someone looks.
        model_rows = [
            {
                "model_id": r.model_id,
                "mean_ic": r.pooled_ic.get("mean_ic"),
                "ic_t_stat": r.pooled_ic.get("t_stat"),
                "ic_ir": r.pooled_ic.get("ic_ir"),
                "train_mean_ic": r.stability("train_mean_ic").get("mean"),
                "train_ic_gap": _gap_of(r),
                "fold_ic_positive_rate": r.stability("spearman").get("fold_positive_rate"),
                "folds": len(r.folds),
            }
            for r in results
        ]
        best = max(
            (m for m in model_rows if m["mean_ic"] is not None),
            key=lambda m: m["mean_ic"], default=None,
        )
        rows.append({
            "arm": arm.name,
            "families": list(arm.families),
            "hypothesis": arm.hypothesis,
            "skipped": False,
            "feature_count": len(columns),
            "models": model_rows,
            "best_model": best["model_id"] if best else None,
            "best_ic": best["mean_ic"] if best else None,
            "best_t": best["ic_t_stat"] if best else None,
            "failures": failures,
            "timing": timing,
        })

    # ── the contrast ────────────────────────────────────────────────────
    #
    # Every arm is compared to C_base, the arm containing everything derivable
    # from price. A family "adds information" only if its arm beats that, and
    # the delta is reported per model as well as on the best, because a single
    # best-of comparison is a maximum of six draws and is biased upward.
    by_arm = {r["arm"]: r for r in rows if not r["skipped"]}
    base = by_arm.get("C_base")
    contrasts: list[dict[str, Any]] = []
    if base is not None:
        base_by_model = {m["model_id"]: m["mean_ic"] for m in base["models"]}
        for row in rows:
            if row["skipped"] or row["arm"] == "C_base":
                continue
            deltas = [
                {
                    "model_id": m["model_id"],
                    "arm_ic": m["mean_ic"],
                    "base_ic": base_by_model.get(m["model_id"]),
                    "delta": (
                        None if m["mean_ic"] is None
                        or base_by_model.get(m["model_id"]) is None
                        else m["mean_ic"] - base_by_model[m["model_id"]]
                    ),
                }
                for m in row["models"]
            ]
            usable = [d["delta"] for d in deltas if d["delta"] is not None]
            contrasts.append({
                "arm": row["arm"],
                "families_added": [
                    f for f in row["families"] if f not in set(base["families"])
                ],
                "per_model": deltas,
                "mean_delta": float(np.mean(usable)) if usable else None,
                "median_delta": float(np.median(usable)) if usable else None,
                "models_improved": sum(1 for d in usable if d > 0),
                "models_compared": len(usable),
            })

    return {
        "ran": True,
        "target": target,
        "base_arm": "C_base",
        "arms": rows,
        "coverage": coverage,
        "contrasts": contrasts,
        "interpretation": (
            "A family adds information only if its arm beats C_base on the same "
            "folds with the same models and seed. `models_improved` out of "
            "`models_compared` is the honest headline: one model improving out of "
            "six is noise, not a source."
        ),
    }


def _gap_of(result: Any) -> Optional[float]:
    """Train-minus-validation IC, from the same source the leaderboard uses."""
    train = result.stability("train_mean_ic").get("mean")
    validation = result.pooled_ic.get("mean_ic")
    if train is None or validation is None:
        return None
    return train - validation


def _pbo(series: dict[str, pd.Series]) -> dict[str, Any]:
    """Probability of backtest overfitting across configurations.

    Degenerate configurations are dropped BEFORE the inner join. A model that
    trades 12 periods is not a competitor in the selection process PBO measures,
    and letting it truncate every other model's history answers a different
    question than the one asked.
    """
    usable = {name: values for name, values in series.items() if len(values) >= MIN_PBO_PERIODS}
    excluded = sorted(set(series) - set(usable))
    if len(usable) < 2:
        return {
            "pbo": None, "configurations": len(usable), "excluded": excluded,
            "note": f"fewer than two configurations with >= {MIN_PBO_PERIODS} periods",
        }

    aligned = pd.DataFrame(usable).dropna()
    if len(aligned) < 32:
        return {
            "pbo": None, "configurations": len(usable), "excluded": excluded,
            "aligned_periods": int(len(aligned)),
            "note": f"{len(aligned)} aligned periods is below the 32 CSCV needs",
        }
    report = probability_of_backtest_overfitting(aligned.to_numpy())
    report["excluded"] = excluded
    report["excluded_reason"] = (
        f"traded fewer than {MIN_PBO_PERIODS} periods; a degenerate configuration is "
        "not a competitor in the selection process PBO measures"
    )
    report["aligned_periods"] = int(len(aligned))
    return report


def _backtest(predictions, returns_panel, definition, half_spread_bps, forward_column):
    try:
        return run_backtest(
            predictions, returns_panel,
            config=BacktestConfig(
                rebalance_step_sessions=definition.step_sessions,
                execution_lag_periods=definition.execution_lag_periods,
                cost_model=SimpleCostModel(half_spread_bps=half_spread_bps),
            ),
            forward_return_column=forward_column,
        )
    except Exception as error:  # noqa: BLE001 — a failed backtest is a recorded result
        logger.debug("backtest failed at %s bp: %s", half_spread_bps, error)
        return None


def _safe_read(store: RawStore, dataset_id: str):
    try:
        return store.read(dataset_id)
    except Exception as error:  # noqa: BLE001
        logger.warning("%s unavailable: %s", dataset_id, error)
        return None


def _f(value: Any) -> str:
    return "n/a" if not isinstance(value, (int, float)) else f"{value:+.4f}"


def _n(value: Any, digits: int = 1) -> str:
    return "n/a" if not isinstance(value, (int, float)) else f"{value:.{digits}f}"


def _pct(value: Any) -> str:
    """Cost share as a whole-number percentage of gross return."""
    return "n/a" if not isinstance(value, (int, float)) else f"{value * 100:.0f}"


def _print_summary(payload: dict[str, Any]) -> None:
    definition = payload["experiment"]
    print("\n" + "=" * 100)
    print(f"{definition['experiment_id']} SUMMARY   (holdout NOT touched)")
    print("=" * 100)
    dataset = payload["dataset"]
    print(f"dataset {dataset['dataset_version']}  {dataset['rows']:,} rows  "
          f"{dataset['symbols']} symbols  {dataset['dates']} dates  "
          f"{dataset['start']} -> {dataset['end']}")
    print(f"integrity: {'CLEAN' if payload['integrity'].get('clean') else payload['integrity']}")
    controls = payload["negative_controls"]
    print(f"negative controls: {'ALL PASS' if controls.get('all_passed') else controls.get('failed')}")
    print(f"multiple testing: {definition['cumulative_evaluations']} cumulative evaluations "
          f"({definition['prior_evaluations']} prior + {definition['declared_evaluations']} here)")

    for target, report in payload["labels"].items():
        primary = " [PRIMARY]" if target == definition["primary_target"] else ""
        print(f"\n--- {target}{primary}  ({report['horizon_sessions']}d, "
              f"{len(report['walk_forward_plan']['folds'])} folds, "
              f"exec lag {definition['execution_lag_periods']}) ---")
        print(f"{'model':<27}{'valIC':>9}{'trIC':>9}{'gap':>8}{'t':>7}{'fold+':>7}"
              f"{'grossSR':>9}{'netSR':>8}{'turn':>7}{'cost%':>7}{'alphaT':>8}{'DSRp':>7}")
        for row in report["leaderboard"]:
            model_id = row["model_id"]
            backtest = report["backtests"].get(model_id, {}).get("metrics", {})
            attribution = report["factor_attribution"].get(model_id, {})
            dsr = report["significance"].get(model_id, {}).get("deflated_sharpe", {})
            print(
                f"{model_id:<27}{_f(row['mean_ic']):>9}{_f(row.get('train_mean_ic')):>9}"
                f"{_f(row.get('train_ic_gap')):>8}{_f(row['ic_t_stat']):>7}"
                f"{_f(row['fold_ic_positive_rate']):>7}{_f(backtest.get('gross_sharpe')):>9}"
                f"{_f(backtest.get('net_sharpe')):>8}"
                f"{_n(backtest.get('annualised_turnover'), 1):>7}"
                f"{_pct(backtest.get('cost_share_of_gross')):>7}"
                f"{_f(attribution.get('alpha_t_stat')):>8}"
                f"{_f(dsr.get('deflated_probability')):>7}"
            )
        distribution = report["experiment_distribution"]
        print(f"  population: {distribution.get('experiments')} scored, best "
              f"{_f(distribution.get('best'))}, median {_f(distribution.get('median'))}, "
              f"above zero {distribution.get('above_zero')}")
        print(f"  PBO {_f(report['probability_of_backtest_overfitting'].get('pbo'))} | "
              f"deflated against {report['trials_used_for_correction']} cumulative trials")
    print("=" * 100 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a declared experiment")
    parser.add_argument("--experiment", default="EXP-004")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--out", default="experiments")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--skip-integrity", action="store_true",
                        help="operational only; a run reported as evidence must not use it")
    args = parser.parse_args()

    definition = get_experiment(args.experiment, args.seed)
    try:
        run_experiment(
            definition, root=args.root, out_root=args.out,
            workers=args.workers, skip_integrity=args.skip_integrity,
        )
    except ExperimentAborted as error:
        print(f"\nEXPERIMENT ABORTED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
