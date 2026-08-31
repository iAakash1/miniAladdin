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
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: Resource policies. Explicit, deterministic, and opt-in above `safe`.
#:
#: `safe` is unchanged and remains the default. The two faster modes exist
#: because the conservative constants were calibrated on the 103-feature panel
#: that OOM-ed at 12 workers, and they are far too pessimistic for a 27-feature
#: run: EXP-006 recorded a peak of ~7.3 GB across 6 workers, which is ~1.1 GB
#: each, not the 2.6 GB `safe` assumes.
#:
#: Nothing here touches the research specification. A mode changes how many
#: processes fit the SAME models on the SAME folds — never which models, which
#: folds, which features or which thresholds.
@dataclass(frozen=True)
class ResourcePolicy:
    name: str
    #: Hard ceiling on the pool regardless of arithmetic.
    max_workers: Optional[int]
    #: Held back for the OS, the editor and everything else running.
    reserve_gb: float
    #: Per-worker overhead beyond the shipped frame.
    worker_overhead_gb: float
    #: Prefer performance cores only (Apple Silicon). Efficiency cores are much
    #: slower, so on a heterogeneous pool they straggle and the run finishes at
    #: the pace of its slowest worker.
    performance_cores_only: bool
    rationale: str


POLICIES: dict[str, ResourcePolicy] = {
    "safe": ResourcePolicy(
        name="safe",
        max_workers=6,
        reserve_gb=6.0,
        worker_overhead_gb=2.6,
        performance_cores_only=False,
        rationale=(
            "Unchanged default. Constants calibrated after a 12-worker OOM on the "
            "wide panel; deliberately pessimistic because the failure mode of "
            "getting it wrong is a killed run, not a slow one."
        ),
    ),
    "high": ResourcePolicy(
        name="high",
        max_workers=None,
        reserve_gb=4.0,
        worker_overhead_gb=1.6,
        performance_cores_only=True,
        rationale=(
            "Performance cores only, moderate reserve. Uses the fast half of an "
            "Apple Silicon package without letting efficiency cores straggle."
        ),
    ),
    "max": ResourcePolicy(
        name="max",
        max_workers=None,
        reserve_gb=3.0,
        worker_overhead_gb=1.15,
        performance_cores_only=False,
        rationale=(
            "Every logical core, overhead set from EXP-006's recorded peak "
            "(~7.3 GB across 6 workers). Aggressive but still memory-checked: the "
            "worker count is the minimum of cores, what RAM affords, and the "
            "number of model specs — a pool larger than the work is waste."
        ),
    ),
}

DEFAULT_POLICY = "safe"

#: Threads per worker, FIXED across every policy.
#:
#: Set to 1 on purpose. Parallelism here is process-level — `evaluate_specs`
#: hands one model spec to each worker — so intra-process BLAS threads buy
#: little and cost a lot: N workers x N threads is N² on an N-core box.
#:
#: More importantly, holding it constant is what makes a performance mode a
#: pure compute change. Multi-threaded BLAS can reorder reductions and alter the
#: last bits of a linear fit; if the thread count varied by mode, `--performance
#: max` could produce a different number from `safe`. It cannot, because this
#: does not move.
THREADS_PER_WORKER = 1

#: Retained for callers that import them. `plan_compute` reads the policy.
MAX_WORKERS = POLICIES["safe"].max_workers
RESERVE_GB = POLICIES["safe"].reserve_gb
WORKER_OVERHEAD_GB = POLICIES["safe"].worker_overhead_gb


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
    policy: str = DEFAULT_POLICY
    topology: dict[str, Any] = field(default_factory=dict)
    projected_peak_gb: float = 0.0

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
            "policy": self.policy,
            "topology": dict(self.topology),
            "projected_peak_gb": self.projected_peak_gb,
            "reasoning": list(self.reasoning),
        }


def _sysctl(key: str) -> Optional[int]:
    try:
        out = subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return int(out) if out.isdigit() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


@dataclass
class Topology:
    """The CPU package as it actually is, not as x86 assumptions imagine it.

    Apple Silicon is heterogeneous: an M4 Pro is 8 performance + 4 efficiency
    cores. Treating all 12 as interchangeable makes a pool finish at the pace of
    its slowest member, because joblib hands one model spec to each worker and
    an E-core takes materially longer on a tree ensemble than a P-core.
    """

    logical: int
    physical: int
    performance: Optional[int]
    efficiency: Optional[int]
    brand: str

    @property
    def heterogeneous(self) -> bool:
        return bool(self.performance and self.efficiency)

    def as_dict(self) -> dict[str, Any]:
        return {
            "brand": self.brand,
            "logical": self.logical,
            "physical": self.physical,
            "performance_cores": self.performance,
            "efficiency_cores": self.efficiency,
            "heterogeneous": self.heterogeneous,
        }


def detect_topology() -> Topology:
    logical = _sysctl("hw.logicalcpu") or os.cpu_count() or 4
    physical = _sysctl("hw.physicalcpu") or logical
    performance = _sysctl("hw.perflevel0.logicalcpu")
    efficiency = _sysctl("hw.perflevel1.logicalcpu")
    brand = "unknown"
    try:
        brand = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or platform.processor() or "unknown"
    except (OSError, subprocess.SubprocessError):
        brand = platform.processor() or "unknown"
    return Topology(logical, physical, performance, efficiency, brand)


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
    """Memory actually free right now, not the size of the DIMMs.

    This matters for the aggressive policies: sizing a pool against *total* RAM
    on a machine that is also running an editor, a browser and a dev server is
    how a plan that looks fine on paper starts swapping. psutil is not a
    dependency of this project, so macOS is read directly from `vm_stat`;
    psutil is used when present.

    Returns None when neither source works, and the caller then falls back to
    total with that stated in the reasoning rather than silently assumed.
    """
    try:
        import psutil

        return psutil.virtual_memory().available / 2**30
    except Exception:  # noqa: BLE001
        pass

    if platform.system() != "Darwin":
        return None
    try:
        page_size = _sysctl("hw.pagesize") or 4096
        out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5
        ).stdout
        counts: dict[str, int] = {}
        for line in out.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            digits = value.strip().rstrip(".")
            if digits.isdigit():
                counts[key.strip()] = int(digits)
        # Free + inactive + speculative is what the kernel can hand back without
        # evicting anything a running process still wants. Wired and active are
        # deliberately excluded.
        pages = (
            counts.get("Pages free", 0)
            + counts.get("Pages inactive", 0)
            + counts.get("Pages speculative", 0)
        )
        if pages <= 0:
            return None
        return pages * page_size / 2**30
    except (OSError, subprocess.SubprocessError, ValueError):
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
    *,
    policy: str = DEFAULT_POLICY,
    requested_workers: Optional[int] = None,
    frame_gb: float = 0.25,
    spec_count: Optional[int] = None,
) -> ComputePlan:
    """Choose a worker count from measured hardware under an explicit policy.

    Three mistakes are prevented here.

    **Too many workers exhausts RAM.** The count is bounded by measured memory
    divided by the policy's per-worker overhead.

    **Too many threads per worker oversubscribes the CPU.** joblib spawning N
    processes that each spawn N BLAS threads is N² threads on an N-core box.

    **A pool larger than the work is waste.** `evaluate_specs` distributes model
    *specs*, so more workers than specs buys nothing and costs memory.

    Threads are pinned to `THREADS_PER_WORKER` in *every* policy, deliberately.
    A mode that changed thread counts could change BLAS reduction order and
    therefore the last bits of a linear model's fit — which would make the
    performance mode a scientific change. It is not allowed to be one.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; known: {sorted(POLICIES)}")
    rule = POLICIES[policy]

    topology = detect_topology()
    total = _total_ram_gb()
    available = _available_ram_gb()
    free_disk = shutil.disk_usage(".").free / 2**30
    reasoning: list[str] = [f"policy '{rule.name}': {rule.rationale}"]

    if rule.performance_cores_only and topology.performance:
        core_budget = topology.performance
        reasoning.append(
            f"cores: {core_budget} performance cores of {topology.logical} logical "
            "(efficiency cores excluded — they straggle on a per-spec pool)"
        )
    else:
        core_budget = topology.logical
        reasoning.append(f"cores: {core_budget} logical")

    per_worker = frame_gb + rule.worker_overhead_gb
    measured = available if available is not None else total
    budget = measured - rule.reserve_gb
    affordable = max(1, int(budget / max(per_worker, 0.1)))
    reasoning.append(
        f"memory: {budget:.1f} GB usable ({'measured free' if available else 'total'}) "
        f"/ {per_worker:.2f} GB per worker = {affordable} affordable"
    )

    workers = min(core_budget, affordable)
    if rule.max_workers is not None:
        workers = min(workers, rule.max_workers)
        reasoning.append(f"policy ceiling: {rule.max_workers}")
    if spec_count:
        if spec_count < workers:
            reasoning.append(
                f"work bound: {spec_count} model specs, so {spec_count} workers is the "
                "most that can be busy"
            )
        workers = min(workers, spec_count)
    workers = max(1, workers)

    if requested_workers is not None:
        if requested_workers > workers:
            reasoning.append(
                f"OVERRIDE: {requested_workers} requested, above the computed {workers}. "
                "Honoured because it was asked for explicitly — watch memory."
            )
        workers = max(1, requested_workers)

    projected = workers * per_worker + rule.reserve_gb
    if projected > measured:
        reasoning.append(
            f"WARNING: projected {projected:.1f} GB exceeds {measured:.1f} GB measured. "
            "Swap pressure is likely; lower --workers."
        )

    # Sizing on *available* memory is the safe choice, but it reflects whatever
    # else is running right now. On a busy machine that can silently halve the
    # pool, so the headroom a quiet machine would give is stated explicitly
    # rather than left for the user to discover by closing things and re-running.
    if available is not None and total - available > 2.0:
        quiet = max(1, int((total - rule.reserve_gb) / max(per_worker, 0.1)))
        quiet = min(quiet, core_budget, spec_count or core_budget)
        if rule.max_workers is not None:
            quiet = min(quiet, rule.max_workers)
        if quiet > workers:
            reasoning.append(
                f"headroom: {total - available:.1f} GB is held by other processes. "
                f"With them closed this policy would allow {quiet} workers instead "
                f"of {workers}."
            )

    reasoning.append(
        f"threads/worker pinned to {THREADS_PER_WORKER} in every policy so a mode "
        f"cannot alter BLAS reduction order; total {workers * THREADS_PER_WORKER} "
        f"vs {topology.logical} logical cores"
    )

    return ComputePlan(
        cores=topology.logical, total_ram_gb=total, available_ram_gb=available,
        free_disk_gb=free_disk, workers=workers, threads_per_worker=THREADS_PER_WORKER,
        gpu=_gpu_status(), reasoning=reasoning, policy=rule.name,
        topology=topology.as_dict(),
        projected_peak_gb=round(workers * per_worker + rule.reserve_gb, 1),
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


class ResourceMonitor:
    """Sample real CPU and RSS for this process tree during training.

    Deliberately measured, never estimated: the numbers printed here come from
    `ps` over the actual worker PIDs. If sampling fails the monitor reports that
    it could not measure rather than showing a plausible-looking figure, because
    a fabricated utilisation number is worse than none — it would be used to
    conclude the machine was busy when it was idle.
    """

    def __init__(self, interval: float = 5.0) -> None:
        self.interval = interval
        self.samples: list[dict[str, float]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None

    def _sample(self) -> Optional[dict[str, float]]:
        try:
            out = subprocess.run(
                ["ps", "-Ao", "pid,ppid,rss,pcpu,comm"],
                capture_output=True, text=True, timeout=5,
            ).stdout.splitlines()[1:]
        except (OSError, subprocess.SubprocessError):
            return None

        me = os.getpid()
        tree = {me}
        rows: list[tuple[int, int, float, float]] = []
        for line in out:
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            try:
                pid, ppid, rss, pcpu = int(parts[0]), int(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                continue
            rows.append((pid, ppid, rss, pcpu))

        # Two passes so grandchildren (joblib's loky workers) are included.
        for _ in range(3):
            for pid, ppid, _rss, _cpu in rows:
                if ppid in tree:
                    tree.add(pid)

        mine = [(rss, cpu) for pid, _ppid, rss, cpu in rows if pid in tree]
        if not mine:
            return None
        return {
            "rss_gb": sum(r for r, _ in mine) / 1024 / 1024,
            "cpu_pct": sum(c for _, c in mine),
            "processes": float(len(mine)),
        }

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            sample = self._sample()
            if sample is None:
                self.error = "ps sampling unavailable — utilisation not measured"
                return
            self.samples.append(sample)

    def start(self) -> "ResourceMonitor":
        first = self._sample()
        if first is None:
            self.error = "ps sampling unavailable — utilisation not measured"
            return self
        self.samples.append(first)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if not self.samples:
            return {"measured": False, "reason": self.error or "no samples"}
        cpu = [s["cpu_pct"] for s in self.samples]
        rss = [s["rss_gb"] for s in self.samples]
        procs = [s["processes"] for s in self.samples]
        return {
            "measured": True,
            "samples": len(self.samples),
            "cpu_pct_mean": round(sum(cpu) / len(cpu), 1),
            "cpu_pct_peak": round(max(cpu), 1),
            "cpu_cores_equivalent_peak": round(max(cpu) / 100.0, 2),
            "rss_gb_mean": round(sum(rss) / len(rss), 2),
            "rss_gb_peak": round(max(rss), 2),
            "processes_peak": int(max(procs)),
            "note": "measured from ps over this process tree; not estimated",
        }

    def snapshot(self) -> str:
        if not self.samples:
            return "utilisation not measured"
        last = self.samples[-1]
        return (
            f"{last['cpu_pct'] / 100.0:.1f} cores · {last['rss_gb']:.1f} GB RSS · "
            f"{int(last['processes'])} procs"
        )


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
    topo = c.get("topology") or {}
    cores_desc = f"{c['cores']} cores"
    if topo.get("heterogeneous"):
        cores_desc = (f"{c['cores']} cores ({topo['performance_cores']}P + "
                      f"{topo['efficiency_cores']}E)")
    print(f"  machine       {topo.get('brand', 'unknown')} · {cores_desc} · "
          f"{c['total_ram_gb']} GB RAM{free} · {c['free_disk_gb']} GB disk")
    print(f"  policy        {c['policy'].upper()}"
          f"{'  (opt-in aggressive)' if c['policy'] != 'safe' else '  (default)'}")
    print(f"  workers       {c['workers']} × {c['threads_per_worker']} thread "
          f"= {c['total_threads']} threads on {c['cores']} cores · "
          f"projected peak ~{c['projected_peak_gb']} GB")
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
                        help="Override the computed worker count. Above it is honoured but flagged.")
    parser.add_argument("--performance", choices=sorted(POLICIES), default=DEFAULT_POLICY,
                        help="Resource policy. 'safe' (default) keeps the conservative "
                             "constants; 'high' uses performance cores only; 'max' uses every "
                             "logical core with the per-worker overhead measured from EXP-006. "
                             "Changes COMPUTE ONLY — never the specification.")
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

    # Spec count bounds the pool: `evaluate_specs` distributes model specs, so a
    # pool larger than the ladder cannot be busy.
    try:
        from src.quant.study.experiment import get_experiment as _peek

        spec_count = len(_peek(args.experiment, args.seed).models)
    except Exception:  # noqa: BLE001
        spec_count = None

    plan = plan_compute(
        policy=args.performance,
        requested_workers=args.workers,
        frame_gb=args.frame_gb,
        spec_count=spec_count,
    )

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
              f"--performance {args.performance} --confirm")
        if args.performance == "safe":
            print()
            print("For heavier use of this machine:")
            print(f"    python -m src.quant.train --experiment {args.experiment} "
                  f"--performance max --confirm")
            print("  MAX changes compute parallelism only — same features, folds, seeds,")
            print("  hyperparameters, costs and thresholds. Verified to produce results")
            print("  identical to the serial path.")
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
    print(f"\nstarting — policy {plan.policy.upper()}, {plan.workers} workers × "
          f"{plan.threads_per_worker} thread\n")

    from src.quant.study.experiment import get_experiment
    from src.quant.study.run import run_experiment

    monitor = ResourceMonitor(interval=10.0).start()
    began = time.perf_counter()
    payload: Optional[dict[str, Any]] = None
    failure: Optional[BaseException] = None
    try:
        payload = run_experiment(
            get_experiment(args.experiment, args.seed),
            root=str(args.root),
            out_root=str(args.out),
            workers=plan.workers,
        )
    except BaseException as exc:  # noqa: BLE001 — reported, never swallowed
        failure = exc
    finally:
        usage = monitor.stop()

    elapsed = (time.perf_counter() - began) / 60.0
    artifact = Path(args.out) / args.experiment / "metrics.json"

    print()
    print("=" * 78)
    if usage.get("measured"):
        print(f"  utilisation   peak {usage['cpu_cores_equivalent_peak']:.1f} cores "
              f"({usage['cpu_pct_peak']:.0f}% CPU) · peak {usage['rss_gb_peak']:.1f} GB RSS "
              f"· {usage['processes_peak']} processes")
        print(f"                mean {usage['cpu_pct_mean'] / 100.0:.1f} cores over "
              f"{usage['samples']} samples — measured from ps, not estimated")
    else:
        print(f"  utilisation   NOT MEASURED ({usage.get('reason')})")
    print(f"  duration      {elapsed:.1f} min")

    # ── completion gate ──────────────────────────────────────────────────
    #
    # COMPLETE only when every model succeeded and the artifact exists.
    # `evaluate_specs` records per-model failures and continues, which is right
    # for the study runner and wrong for a training command: an artifact that
    # looks finished but was computed over a silently smaller ladder is the
    # worst possible output, because every downstream number inherits the gap.
    if failure is not None:
        print(f"  status        FAILED — {type(failure).__name__}: {failure}")
        print("=" * 78)
        print("\nNothing from this run should be trusted. Fix the cause and re-run;")
        print("the command is idempotent and the holdout was never opened.")
        return 4

    failures: list[dict[str, Any]] = []
    if payload:
        for target, block in (payload.get("labels") or {}).items():
            for item in block.get("failures") or []:
                failures.append({"target": target, **item})

    if failures:
        print(f"  status        INCOMPLETE — {len(failures)} model(s) failed")
        for item in failures[:10]:
            detail = str(item.get("error", "")).splitlines()
            print(f"                  {item.get('target')}/{item.get('model')}: "
                  f"{(detail[0] if detail else '')[:90]}")
        print("=" * 78)
        print("\nThe artifact was written but the ladder is incomplete, so this is NOT")
        print("a finished training run. Re-run after fixing the failing model(s).")
        return 5

    if not artifact.exists():
        print("  status        FAILED — no artifact was written")
        print("=" * 78)
        return 6

    print("  status        COMPLETE — every model in the ladder succeeded")
    print(f"  artifact      {artifact}")
    print("=" * 78)
    print()
    print("Register it with:")
    print(f"    python -m scripts.quant.register_experiment --experiment {args.experiment}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
