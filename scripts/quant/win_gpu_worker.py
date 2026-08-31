"""
EXP-007-WIN-GPU — the Windows CUDA worker.

Runs the GPU-capable model families over the *same* folds, features, target,
execution lag and cost assumptions as EXP-007, on a machine EXP-007 cannot use.
Writes to its own experiment namespace and never touches the Mac's state.

    python -m scripts.quant.win_gpu_worker --confirm

Without `--confirm` it prints the plan, the detected GPU, the trial cost and the
projected configuration count, and fits nothing.

## What this does NOT do

It does not read the holdout. `build_plan` reserves it and
`HoldoutFirewall.assert_clear` runs on both frames of every fold before every
fit, exactly as on the Mac. There is no flag here that changes that.

It does not merge results into EXP-007. The artifact lands in
`experiments/EXP-007-WIN-GPU/` with the machine's own provenance, and the
aggregation step is a human reading two ledger rows — not a script picking the
better number off two machines, which is selection dressed as engineering.

## Why the stage loop is written out here rather than reusing `heavy.evaluate_batch`

`evaluate_batch` builds specs through `search.to_spec`, which resolves the CPU
families only. Threading a spec factory through it is the right fix and is a
two-line change — but that module is loaded by a long-running search on the
other machine, and editing a module live workers may re-import is how a
ten-hour run dies at hour six. The batching is restated; the *science* is not:
`evaluate_specs`, the walk-forward plan, the firewall and the metrics are the
same objects EXP-007 calls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.quant.datasets.store import RawStore
from src.quant.models.gpu import GpuModelSpec, cuda_report
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.study import gpu_search as gpu
from src.quant.study.experiment import git_commit, git_dirty
from src.quant.study.firewall import FIREWALL
from src.quant.study.heavy import (
    Checkpoint, ConfigResult, OVERFIT_GAP, SearchContext, _gap,
    _walk_forward_plan, competitive_families, rank_candidates,
)
from src.quant.study.search import config_id, multiple_testing_cost
from src.quant.validation.parallel import evaluate_specs

#: Same reference context as EXP-007's screen and tune stages, so the two
#: searches' leaderboards are directly comparable.
REFERENCE_ARM = "C_base"
REFERENCE_TARGET = "fwd_rank_21"


def _sample(family: str, count: int, *, stage: str, seed: int) -> list[dict[str, Any]]:
    """Deterministic configurations for a GPU family.

    Same construction as `search.sample_configs`: the generator is seeded from
    (family, stage, seed) so a resumed run continues the same search rather than
    drawing a fresh correlated one.
    """
    import hashlib

    axes = gpu.GPU_SPACES[family]
    digest = hashlib.sha256(f"{family}|{stage}|{seed}".encode()).hexdigest()[:16]
    generator = np.random.default_rng(int(digest, 16) % (2**32))
    configs: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts = 0
    while len(configs) < count and attempts < count * 40:
        attempts += 1
        candidate = {axis.name: axis.draw(generator) for axis in axes}
        key = json.dumps(candidate, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        configs.append(candidate)
    return configs


def _neighbours(family: str, params: dict[str, Any], count: int, *,
                seed: int) -> list[dict[str, Any]]:
    """Small perturbations around a finalist — is it a point or a region?"""
    import hashlib

    axes = {axis.name: axis for axis in gpu.GPU_SPACES[family]}
    fingerprint = f"{family}|neighbour|{json.dumps(params, sort_keys=True, default=str)}|{seed}"
    generator = np.random.default_rng(
        int(hashlib.sha256(fingerprint.encode()).hexdigest()[:16], 16) % (2**32)
    )
    out: list[dict[str, Any]] = []
    names = sorted(axes)
    for index in range(count):
        variant = dict(params)
        # Perturb one axis at a time, cycling. Moving everything at once
        # measures a random point in the space, not a neighbour.
        axis = axes[names[index % len(names)]]
        variant[axis.name] = axis.draw(generator)
        if variant != params:
            out.append(variant)
    return out


def _run_batch(
    planned: list[tuple[str, str, dict[str, Any]]],
    context: SearchContext,
    definition: Any,
    *,
    stage: str,
    workers: int,
    checkpoint: Checkpoint,
    done: dict[str, ConfigResult],
    device: dict[str, str],
) -> list[ConfigResult]:
    pending = [item for item in planned if item[0] not in done]
    results = [done[item[0]] for item in planned if item[0] in done]
    if not pending:
        print(f"      all {stage} configurations already recorded")
        return results

    features = context.features_for(REFERENCE_ARM)
    plan = _walk_forward_plan(context, REFERENCE_TARGET, definition)
    specs = [
        GpuModelSpec(
            name=cid, kind=family,
            params=tuple(sorted({**params, "device": device[family]}.items())),
            seed=definition.seed,
        )
        for cid, family, params in pending
    ]
    lookup = {cid: (family, params) for cid, family, params in pending}

    began = time.perf_counter()
    outcomes, failures, _ = evaluate_specs(
        specs, context.frame, plan, features=features, label=REFERENCE_TARGET,
        step_sessions=definition.step_sessions, workers=workers,
    )
    per_config = (time.perf_counter() - began) / max(len(pending), 1)

    for outcome in outcomes:
        family, params = lookup[outcome.model_id]
        result = ConfigResult(
            config_id=outcome.model_id, stage=stage, family=family, params=params,
            arm=REFERENCE_ARM, target=REFERENCE_TARGET, feature_count=len(features),
            ok=True,
            mean_ic=outcome.pooled_ic.get("mean_ic"),
            ic_t_stat=outcome.pooled_ic.get("t_stat"),
            ic_ir=outcome.pooled_ic.get("ic_ir"),
            train_mean_ic=outcome.stability("train_mean_ic").get("mean"),
            train_ic_gap=_gap(outcome),
            fold_ic_positive_rate=outcome.stability("spearman").get("fold_positive_rate"),
            folds=len(outcome.folds),
            seconds=round(outcome.seconds or per_config, 2),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        checkpoint.append(result)
        results.append(result)
        print(f"      {stage:<11}{family:<12}IC {result.mean_ic:+.4f}  "
              f"t {result.ic_t_stat:+.2f}" if result.ic_t_stat is not None
              else f"      {stage:<11}{family:<12}IC {result.mean_ic:+.4f}")

    # A failure is recorded, never dropped. A configuration that OOMed on the
    # GPU still consumed a trial, and omitting it would understate the budget.
    for failure in failures:
        name = failure.get("model")
        if name not in lookup:
            continue
        family, params = lookup[name]
        result = ConfigResult(
            config_id=name, stage=stage, family=family, params=params,
            arm=REFERENCE_ARM, target=REFERENCE_TARGET, feature_count=len(features),
            ok=False, error=str(failure.get("error", ""))[:500],
            seconds=per_config, completed_at=datetime.now(timezone.utc).isoformat(),
        )
        checkpoint.append(result)
        results.append(result)
        print(f"      {stage:<11}{family:<12}FAILED — {result.error[:90]}")
    return results


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.quant.win_gpu_worker",
        description="EXP-007-WIN-GPU — GPU model families on the EXP-007 folds.",
    )
    parser.add_argument("--root", default="data/research", type=Path)
    parser.add_argument("--out", default="experiments", type=Path)
    parser.add_argument("--workers", type=int, default=2,
                        help="Processes sharing the GPU. Keep this small: each "
                             "holds its own CUDA context and its own copy of the "
                             "panel, and four boosters contending for one device "
                             "is slower than two.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--families", default=",".join(sorted(gpu.GPU_SPACES)),
                        help="Comma-separated subset to run.")
    parser.add_argument("--cpu-fallback", action="store_true",
                        help="Run the boosters on CPU. Recorded in the artifact "
                             "as device=cpu; results stay valid, the point of "
                             "the machine does not.")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    definition = gpu.gpu_experiment(args.seed)
    machine = cuda_report()
    families = [f.strip() for f in args.families.split(",") if f.strip()]
    unknown = [f for f in families if f not in gpu.GPU_SPACES]
    if unknown:
        print(f"error: unknown families {unknown}; known: {sorted(gpu.GPU_SPACES)}",
              file=sys.stderr)
        return 2

    total = gpu.total_configurations()
    mt = multiple_testing_cost(total, prior=definition.prior_evaluations)

    print("=" * 78)
    print(f"  {definition.experiment_id}   fingerprint {definition.fingerprint()}")
    print("=" * 78)
    print(f"  machine       {machine['os']} · {machine['machine']} · python {machine['python']}")
    vram = f" · {machine['vram_gb']} GB VRAM" if machine["vram_gb"] else ""
    print(f"  gpu           {machine['gpu_name'] or 'NOT DETECTED'}{vram}")
    print(f"  detection     {machine['detection']}")
    print(f"  families      {', '.join(families)}")
    print(f"  configs       {total} (upper bound)")
    print(f"  folds         inherited from EXP-007 — same geometry, embargo, purge")
    print(f"  costs         {definition.primary_half_spread_bps} bp half-spread, "
          f"execution lag {definition.execution_lag_periods}")
    print(f"  trials        {mt['prior_trials']} prior + {mt['new_trials']} here "
          f"= {mt['cumulative_trials']}")
    print(f"                a finding must clear |t| > {mt['expected_max_abs_t_under_null']}")
    print(f"  holdout       SEALED — this worker cannot open it")
    print("=" * 78)

    device = {
        "xgboost": "cpu" if args.cpu_fallback else "cuda",
        "lightgbm": "cpu" if args.cpu_fallback else "gpu",
        "catboost": "CPU" if args.cpu_fallback else "GPU",
        "torch_mlp": "cpu" if args.cpu_fallback else "cuda",
    }
    no_gpu = machine["cuda_available"] is not True

    # The dry run always completes. Someone checking the plan on a laptop should
    # get the plan, not a refusal about hardware they were not proposing to use.
    if not args.confirm:
        print("\nDRY RUN — nothing was fitted.")
        if no_gpu and not args.cpu_fallback:
            print("\n  NOTE: no CUDA device is visible from here. --confirm would refuse.")
            print("  On the Windows machine this line should name the RTX PRO 4500.")
        print("\nTo run it:")
        print("    python -m scripts.quant.win_gpu_worker --confirm")
        print("\nAfter an interruption, add --resume. Completed configurations are")
        print("on disk and are skipped.")
        return 0

    if no_gpu and not args.cpu_fallback:
        print("\nREFUSED: no CUDA device detected.")
        print("This worker exists to use a GPU. Running it on CPU by accident would")
        print("produce results labelled GPU that never touched one.")
        print("  install a CUDA build of torch/xgboost/lightgbm  — see")
        print("  docs/HEAVY_TRAINING_WINDOWS.md")
        print("  or pass --cpu-fallback to run on CPU deliberately.")
        return 6

    # One thread per process. Same rule as the Mac: the thread count must not
    # vary, or a run at a different worker count could return different numbers.
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[variable] = "1"

    began = time.perf_counter()
    output = args.out / definition.experiment_id
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(output / "checkpoints" / "configs.jsonl")
    done = checkpoint.load() if args.resume else {}
    if done:
        print(f"\nresuming: {len(done)} configuration(s) already recorded")

    print("\n[1/5] building the point-in-time panel")
    store = RawStore(str(args.root))
    universe = UniverseHistory.load(args.root / "universe")
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start, end=definition.end or Date.today(),
        step_sessions=definition.step_sessions, workers=args.workers,
    )
    frame, manifest = dataset.frame, dataset.manifest
    cross = [c for c in manifest.features if c.endswith("_xs")]
    macro = [c for c in manifest.features if c.startswith(("rates_", "market_"))]
    context = SearchContext(frame=frame, manifest=manifest, calendar=dataset.calendar,
                            available_features=cross + macro)
    print(f"      {manifest.rows:,} rows · hash {manifest.content_hash}")
    print("      This hash must match the Mac's EXP-007 artifact. If it does not,")
    print("      the two machines are not looking at the same data.")

    plan = _walk_forward_plan(context, REFERENCE_TARGET, definition)
    print(f"      folds {len(plan.folds)} · holdout {plan.holdout_start} to "
          f"{plan.holdout_end} — SEALED")

    print(f"\n[2/5] STAGE 1 screen")
    screen_planned = [
        (config_id(family, "gpu_screen", index, params), family, params)
        for family in families
        for index, params in enumerate(
            _sample(family, gpu.GPU_SCREEN[family], stage="gpu_screen", seed=args.seed))
    ]
    screen = _run_batch(screen_planned, context, definition, stage="screen",
                        workers=args.workers, checkpoint=checkpoint, done=done,
                        device=device)

    advancing = competitive_families(screen, keep=gpu.GPU_TUNE_FAMILIES)
    print("\n      advancing to tuning: " + (
        ", ".join(advancing) if advancing
        else "NONE — no family produced a non-overfit configuration"))

    print(f"\n[3/5] STAGE 2 tune")
    tune_planned = [
        (config_id(family, "gpu_tune", index, params), family, params)
        for family in advancing
        for index, params in enumerate(
            _sample(family, gpu.GPU_TUNE[family], stage="gpu_tune", seed=args.seed))
    ]
    tune = _run_batch(tune_planned, context, definition, stage="tune",
                      workers=args.workers, checkpoint=checkpoint, done=done,
                      device=device)

    finalists = rank_candidates(screen + tune)[:gpu.GPU_FINALISTS]
    print(f"\n[4/5] STAGE 3 robustness around {len(finalists)} finalist(s)")
    robust_planned = [
        (config_id(f.family, f"gpu_neighbour:{f.config_id}", index, params),
         f.family, params)
        for f in finalists
        for index, params in enumerate(
            _neighbours(f.family, f.params, gpu.GPU_NEIGHBOURS, seed=args.seed))
    ]
    robustness = _run_batch(robust_planned, context, definition, stage="robustness",
                            workers=args.workers, checkpoint=checkpoint, done=done,
                            device=device)

    print("\n[5/5] writing the artifact")
    everything = screen + tune + robustness
    failures = [r for r in everything if not r.ok]
    actual_mt = multiple_testing_cost(len(everything), prior=definition.prior_evaluations)
    payload = {
        "experiment": definition.as_dict(),
        "fingerprint": definition.fingerprint(),
        "search": {
            "budget": gpu.as_dict(),
            "families_requested": families,
            "families_advanced": advancing,
            "device": device if not args.cpu_fallback else {k: "cpu" for k in device},
            "cpu_fallback": args.cpu_fallback,
            "configurations_evaluated": len(everything),
            "configurations_failed": len(failures),
            "multiple_testing": actual_mt,
            "reference_context": {"arm": REFERENCE_ARM, "target": REFERENCE_TARGET},
        },
        "machine": machine,
        "package_versions": _versions(),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workers": args.workers,
        "dataset": manifest.as_dict(),
        "universe": universe.summary(),
        "holdout": {
            "start": str(plan.holdout_start), "end": str(plan.holdout_end),
            "touched": False,
            "note": "Reserved before any fold was cut; the firewall refuses its rows.",
        },
        "firewall": FIREWALL.status(),
        "results": [r.as_dict() for r in everything],
        "runtime_seconds": round(time.perf_counter() - began, 1),
        "complete": not failures,
        "merge_policy": (
            "NOT merged into EXP-007. Different machine, different floating-point "
            "association, different model families. This is a separate ledger row; "
            "picking the better number off two machines is selection, not "
            "aggregation."
        ),
    }
    (output / "search.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"      wrote {output / 'search.json'}")
    print(f"      {len(everything)} configurations, {len(failures)} failed, "
          f"{payload['runtime_seconds'] / 3600:.2f} h")
    print("\nSend back the whole `experiments/EXP-007-WIN-GPU/` directory.")
    print("Do not copy it over anything under `experiments/EXP-007/`.")
    return 0 if not failures else 5


def _versions() -> dict[str, Optional[str]]:
    """Exact versions of everything that can change a number."""
    out: dict[str, Optional[str]] = {}
    for package in ("numpy", "pandas", "scikit-learn", "scipy", "xgboost",
                    "lightgbm", "catboost", "torch", "joblib"):
        try:
            from importlib.metadata import version

            out[package] = version(package)
        except Exception:  # noqa: BLE001
            out[package] = None
    return out


if __name__ == "__main__":
    sys.exit(main())
