"""
Training entry point — user-triggered, never automatic.

    python -m src.quant.train --experiment EXP-007 --dry-run
    python -m src.quant.train --experiment EXP-007 --confirm

## Why `--confirm` is mandatory

A training run on this machine is 30-100 minutes of saturated CPU and ~7 GB of
resident memory. Nothing should be able to start one as a side effect — not a
page load, not an import, not a stray CLI invocation. So the default is
`--dry-run`: the command prints the full configuration, the measured compute
plan and the integrity status, then **stops**. `--confirm` is the only thing
that starts a fit, and it has to be typed.

## Why this wraps `study.run` rather than replacing it

`src/quant/study/run.py` already owns the scientific path: integrity probes,
negative controls, walk-forward, backtest, attribution, significance, artifact.
Reimplementing any of that here would create a second answer to questions that
already have one. This module is a *front end*: it resolves compute, prints what
is about to happen, and delegates.

## Oversubscription

joblib workers each running a multi-threaded scikit-learn estimator is how a
12-core machine ends up running 144 threads and thrashing. `plan_compute`
allocates cores explicitly and pins BLAS/OMP thread counts in the environment
before any worker starts, so the product of the two never exceeds the core count.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: Hard ceiling on the worker pool regardless of arithmetic.
#:
#: A previous run with 12 workers OOM-ed this machine. The memory estimate is an
#: estimate, and the failure mode of getting it wrong is a killed run rather
#: than a slow one, so a ceiling sits on top of the calculation.
MAX_WORKERS = 6

#: Reserved for the OS, the editor and everything else the user is doing.
RESERVE_GB = 6.0

#: Measured per-worker overhead beyond the shipped frame.
WORKER_OVERHEAD_GB = 2.6


@dataclass
class ComputePlan:
    """What the machine can actually afford, measured rather than assumed."""

    cores: int
    total_ram_gb: float
    available_ram_gb: Optional[float]
    free_disk_gb: float
    workers: int
    threads_per_worker: int
    gpu: str
    reasoning: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cores": self.cores,
            "total_ram_gb": round(self.total_ram_gb, 1),
            "available_ram_gb": None if self.available_ram_gb is None
            else round(self.available_ram_gb, 1),
            "free_disk_gb": round(self.free_disk_gb, 1),
            "workers": self.workers,
            "threads_per_worker": self.threads_per_worker,
            "total_threads": self.workers * self.threads_per_worker,
            "gpu": self.gpu,
            "reasoning": list(self.reasoning),
        }


def _total_ram_gb() -> float:
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if out.isdigit():
            return int(out) / 2**30
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        import psutil

        return psutil.virtual_memory().total / 2**30
    except Exception:  # noqa: BLE001
        return 16.0


def _available_ram_gb() -> Optional[float]:
    try:
        import psutil

        return psutil.virtual_memory().available / 2**30
    except Exception:  # noqa: BLE001
        return None


def _gpu_status() -> str:
    """Whether acceleration exists, and whether it is any use here.

    Apple Silicon has Metal, and it is irrelevant to this workload: the model
    ladder is scikit-learn tree ensembles and linear models on tabular data.
    Neither uses Metal, and reporting "GPU available" without that caveat
    invites someone to go looking for a speedup that does not exist.
    """
    if platform.machine() == "arm64" and platform.system() == "Darwin":
        try:
            import torch  # noqa: F401

            return "Apple Metal present (torch installed) — UNUSED: the ladder is sklearn/CPU"
        except ImportError:
            return "Apple Metal present — UNUSED: no torch, and the ladder is sklearn/CPU"
    return "none detected — the ladder is sklearn/CPU"


def plan_compute(
    *, requested_workers: Optional[int] = None, frame_gb: float = 0.25
) -> ComputePlan:
    """Choose a worker count from measured memory, and pin thread counts.

    Two separate mistakes are prevented here. Too many *workers* exhausts RAM.
    Too many *threads per worker* oversubscribes the CPU — joblib spawning N
    processes that each spawn N BLAS threads is N² threads on an N-core box.
    """
    cores = os.cpu_count() or 4
    total = _total_ram_gb()
    available = _available_ram_gb()
    free_disk = shutil.disk_usage(".").free / 2**30
    reasoning: list[str] = []

    per_worker = frame_gb + WORKER_OVERHEAD_GB
    budget = (available if available is not None else total) - RESERVE_GB
    affordable = max(1, int(budget / max(per_worker, 0.1)))
    reasoning.append(
        f"memory: {budget:.1f} GB usable / {per_worker:.2f} GB per worker = {affordable} affordable"
    )

    workers = min(cores, affordable, MAX_WORKERS)
    reasoning.append(f"capped by min(cores={cores}, affordable={affordable}, ceiling={MAX_WORKERS})")

    if requested_workers is not None:
        if requested_workers > workers:
            reasoning.append(
                f"OVERRIDE: {requested_workers} requested, above the safe {workers}. "
                "Honoured because it was asked for explicitly — watch memory."
            )
        workers = max(1, requested_workers)

    threads = max(1, cores // max(workers, 1))
    reasoning.append(
        f"threads/worker = {threads} so workers x threads = {workers * threads} <= {cores} cores"
    )

    return ComputePlan(
        cores=cores, total_ram_gb=total, available_ram_gb=available,
        free_disk_gb=free_disk, workers=workers, threads_per_worker=threads,
        gpu=_gpu_status(), reasoning=reasoning,
    )


def pin_threads(plan: ComputePlan) -> None:
    """Set BLAS/OMP thread counts BEFORE numpy or sklearn is imported.

    These are read at import time by the underlying libraries, so setting them
    afterwards does nothing — which is the usual reason an oversubscription fix
    appears not to work.
    """
    for key in (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
    ):
        os.environ[key] = str(plan.threads_per_worker)


def describe(experiment_id: str, plan: ComputePlan, *, seed: int, root: Path) -> dict[str, Any]:
    """Everything the run will do, resolved before it does any of it."""
    from src.quant.study.experiment import get_experiment, git_commit, git_dirty

    definition = get_experiment(experiment_id, seed)
    payload: dict[str, Any] = {
        "experiment_id": definition.experiment_id,
        "fingerprint": definition.fingerprint(),
        "objective": definition.objective,
        "targets": list(definition.targets),
        "primary_target": definition.primary_target,
        "models": [m.name for m in definition.models],
        "model_count": len(definition.models),
        "feature_families": list(definition.feature_families) or ["(all available)"],
        "seed": definition.seed,
        "execution_lag_periods": definition.execution_lag_periods,
        "cost_half_spreads_bps": list(definition.cost_half_spreads_bps),
        "primary_half_spread_bps": definition.primary_half_spread_bps,
        "validation": (
            f"expanding walk-forward, {definition.validation_sessions}-session validation, "
            f"min train {definition.min_train_sessions}, embargo {definition.embargo_sessions}"
        ),
        "holdout_sessions": definition.holdout_sessions,
        "declared_evaluations": definition.declared_evaluations,
        "prior_evaluations": definition.prior_evaluations,
        "cumulative_evaluations": definition.cumulative_evaluations,
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "output": str(Path("experiments") / definition.experiment_id),
        "compute": plan.as_dict(),
    }

    from src.quant.study.firewall import HoldoutFirewall

    payload["integrity"] = {
        "holdout_contract_armed": HoldoutFirewall().contract_armed(),
        "firewall": "assert_clear runs per fold immediately before every fit",
        "holdout_note": "The holdout stays sealed. This command cannot open it.",
    }
    return payload


def _print_plan(payload: dict[str, Any]) -> None:
    width = 78
    print("=" * width)
    print(f"TRAIN {payload['experiment_id']}   fingerprint {payload['fingerprint']}")
    print("=" * width)
    print(f"  objective     {payload['objective'][:100]}")
    print(f"  models        {payload['model_count']}: {', '.join(payload['models'][:6])}"
          f"{' …' if payload['model_count'] > 6 else ''}")
    print(f"  targets       {payload['targets']}  primary={payload['primary_target']}")
    print(f"  features      {payload['feature_families']}")
    print(f"  seed          {payload['seed']}")
    print(f"  execution lag {payload['execution_lag_periods']} rebalance period(s)")
    print(f"  cost sweep    {payload['cost_half_spreads_bps']} bp "
          f"(primary {payload['primary_half_spread_bps']})")
    print(f"  validation    {payload['validation']}")
    print(f"  evaluations   {payload['declared_evaluations']} declared, "
          f"{payload['prior_evaluations']} prior, "
          f"{payload['cumulative_evaluations']} cumulative")
    print(f"  git           {payload['git_commit'][:12]}"
          f"{' (DIRTY)' if payload['git_dirty'] else ''}")
    print(f"  output        {payload['output']}/")
    print("-" * width)
    c = payload["compute"]
    free = f" ({c['available_ram_gb']} GB free)" if c["available_ram_gb"] else ""
    print(f"  machine       {c['cores']} cores · {c['total_ram_gb']} GB RAM{free}"
          f" · {c['free_disk_gb']} GB disk")
    print(f"  workers       {c['workers']} × {c['threads_per_worker']} threads "
          f"= {c['total_threads']} (cores {c['cores']})")
    print(f"  gpu           {c['gpu']}")
    for line in c["reasoning"]:
        print(f"                {line}")
    print("-" * width)
    i = payload["integrity"]
    print(f"  holdout       {'ARMED' if i['holdout_contract_armed'] else 'SEALED'} — "
          f"{i['holdout_note']}")
    print(f"  firewall      {i['firewall']}")
    print("=" * width)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.quant.train",
        description="Run a declared quant experiment. Requires --confirm to fit anything.",
    )
    parser.add_argument("--experiment", required=True,
                        help="Experiment id declared in src/quant/study/experiment.py")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=None,
                        help="Override the measured worker count. Above the safe value is honoured "
                             "but flagged.")
    parser.add_argument("--root", default="data/research", type=Path)
    parser.add_argument("--out", default="experiments", type=Path)
    parser.add_argument("--frame-gb", type=float, default=0.25,
                        help="Estimated per-worker frame size, for the memory plan.")
    parser.add_argument("--confirm", action="store_true",
                        help="Actually run. Without it this prints the plan and exits.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicit no-op. The default behaviour anyway.")
    parser.add_argument("--json", action="store_true", help="Emit the plan as JSON and exit.")
    args = parser.parse_args(argv)

    plan = plan_compute(requested_workers=args.workers, frame_gb=args.frame_gb)

    try:
        payload = describe(args.experiment, plan, seed=args.seed, root=args.root)
    except KeyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    _print_plan(payload)

    if not args.confirm or args.dry_run:
        print()
        print("DRY RUN — nothing was fitted.")
        print("To run it:")
        print(f"    python -m src.quant.train --experiment {args.experiment} "
              f"--workers {plan.workers} --confirm")
        print()
        print("Expect 30-100 minutes on this machine and sustained CPU. The holdout")
        print("stays sealed either way; this command has no path that opens it.")
        return 0

    if payload["integrity"]["holdout_contract_armed"]:
        print("\nREFUSED: docs/HOLDOUT_CONTRACT.md is ARMED.")
        print("Training against an armed contract risks spending the holdout.")
        print("Use `python -m src.quant.study.holdout` for a pre-registered holdout run.")
        return 3

    pin_threads(plan)
    print(f"\nstarting — threads pinned to {plan.threads_per_worker} per worker\n")

    from src.quant.study.run import run_experiment

    began = time.perf_counter()
    from src.quant.study.experiment import get_experiment

    run_experiment(
        get_experiment(args.experiment, args.seed),
        root=str(args.root),
        out_root=str(args.out),
        workers=plan.workers,
    )
    print(f"\ncompleted in {(time.perf_counter() - began) / 60:.1f} min")
    print(f"register it with:")
    print(f"    python -m scripts.quant.register_experiment --experiment {args.experiment}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
