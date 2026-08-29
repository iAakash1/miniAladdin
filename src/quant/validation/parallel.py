"""
Parallel model evaluation — one process per model, each single-threaded.

## The arrangement, and why this one

Walk-forward runs for different models are independent, so they parallelise
cleanly. The choice is *where* to put the parallelism:

| Arrangement | Cores used | Deterministic |
|---|---|---|
| 1 model x N threads | N | **no** — threaded accumulation reorders floats |
| N models x 1 thread | N | yes |

The second is chosen. Reproducibility outranks per-model speed: a result that
cannot be reproduced cannot anchor a research record, and
`tests/quant/test_models.py::test_same_seed_gives_identical_predictions` would
fail under the first.

## Memory is the real constraint

Each worker receives a copy of the training frame. A 500,000-row x 60-column
float64 frame is ~240 MB, so twelve workers is ~3 GB of duplication on top of
the parent. `recommended_workers` sizes the pool against available memory
rather than core count alone, because swapping is far slower than the
serialisation it would be avoiding.

## Failure is a result

A model that raises is recorded with its traceback and the run continues. A
failed configuration is data about the configuration; losing the other eleven
because one blew up is not.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Optional, Sequence

import pandas as pd

from src.quant.models.factory import ModelSpec
from src.quant.validation.runner import ExperimentResult, run_walk_forward
from src.quant.validation.walkforward import WalkForwardPlan

logger = logging.getLogger("omnisignal.quant.validation.parallel")

#: Resident memory a worker needs beyond its copy of the frame.
#:
#: Raised from 0.9 to 2.6 after a 12-worker run was killed by the OS with no
#: traceback — the signature of SIGKILL under memory pressure. The original
#: figure counted only the fold matrices and missed where tree ensembles
#: actually spend memory: a 300-tree forest at depth 8 over ~400,000 training
#: rows holds its whole node structure resident, and five such models fitting
#: concurrently is several times the frame copies.
#:
#: 2.6 GB gives 6 workers on a 24 GB machine with 6 GB reserved, which is the
#: configuration that completes. The cost is wall clock; the alternative is a
#: run that dies two-thirds of the way through and reports nothing.
WORKER_OVERHEAD_GB = 2.6

#: Hard ceiling regardless of arithmetic. The memory estimate is exactly that —
#: an estimate — and the failure mode of getting it wrong is not a slow run but
#: a killed one.
MAX_WORKERS = 6


def recommended_workers(
    frame_bytes: int, *, requested: Optional[int] = None, reserve_gb: float = 6.0
) -> int:
    """Pool size that fits in memory, not just in cores.

    `reserve_gb` is left for the parent process, the OS and whatever else the
    machine is doing — a research run that makes the laptop unusable is not a
    good research run.
    """
    cores = os.cpu_count() or 4
    ceiling = requested if requested and requested > 0 else cores
    try:
        import subprocess

        total_gb = int(
            subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                           text=True, timeout=5).stdout.strip()
        ) / 1024**3
    except Exception:  # noqa: BLE001 — an unknown memory size falls back to the ceiling
        return max(1, min(ceiling, cores, MAX_WORKERS))

    per_worker = frame_bytes / 1024**3 + WORKER_OVERHEAD_GB
    affordable = int(max(1.0, (total_gb - reserve_gb) / max(per_worker, 0.1)))
    workers = max(1, min(ceiling, cores, affordable, MAX_WORKERS))
    logger.info(
        "parallel: %d worker(s) — %d cores, %.1f GB total, %.2f GB/worker, %.1f GB reserved",
        workers, cores, total_gb, per_worker, reserve_gb,
    )
    return workers


def _evaluate(
    spec: ModelSpec,
    frame: pd.DataFrame,
    plan: WalkForwardPlan,
    features: Sequence[str],
    label: str,
    step_sessions: int,
) -> tuple[str, Optional[ExperimentResult], Optional[str]]:
    """Run one model's walk-forward inside a worker."""
    try:
        result = run_walk_forward(
            spec.build, frame, plan,
            features=features, label=label, step_sessions=step_sessions,
        )
        return spec.name, result, None
    except Exception as error:  # noqa: BLE001 — recorded and returned, never raised
        import traceback

        return spec.name, None, f"{type(error).__name__}: {error}\n{traceback.format_exc()[:1500]}"


def evaluate_specs(
    specs: Sequence[ModelSpec],
    frame: pd.DataFrame,
    plan: WalkForwardPlan,
    *,
    features: Sequence[str],
    label: str,
    step_sessions: int,
    workers: Optional[int] = None,
    on_complete: Optional[Callable[[str, Optional[ExperimentResult], Optional[str]], None]] = None,
) -> tuple[list[ExperimentResult], list[dict[str, Any]], dict[str, Any]]:
    """Evaluate every spec, returning results, failures and timing.

    Falls back to serial execution when joblib is unavailable or a pool cannot
    be created — with a logged reason, because a silent fallback would make a
    twelve-minute run look like a one-minute one for no visible cause.
    """
    began = time.perf_counter()
    # Only the columns the run needs. On a wide panel this is the difference
    # between shipping 240 MB and 900 MB to each worker.
    needed = [
        c for c in dict.fromkeys(
            ["date", "symbol", "in_universe", label, *features]
        )
        if c in frame.columns
    ]
    slim = frame[needed]
    pool_size = recommended_workers(int(slim.memory_usage(deep=False).sum()), requested=workers)

    outcomes: list[tuple[str, Optional[ExperimentResult], Optional[str]]] = []
    mode = "serial"
    if pool_size > 1 and len(specs) > 1:
        try:
            from joblib import Parallel, delayed

            # `return_as="generator_unordered"` yields each model as it finishes
            # rather than collecting the whole list at the end. That matters for
            # more than tidiness: with the default the progress display sits at
            # 0/17 for the entire run and then jumps to 17/17, which is not a
            # progress display. Unordered because a slow tree model must not
            # hold back the eleven baselines that finished in seconds.
            stream = Parallel(
                n_jobs=pool_size, prefer="processes", batch_size=1,
                return_as="generator_unordered",
            )(
                delayed(_evaluate)(spec, slim, plan, list(features), label, step_sessions)
                for spec in specs
            )
            outcomes = []
            for outcome in stream:
                outcomes.append(outcome)
                if on_complete is not None:
                    on_complete(*outcome)
            mode = f"parallel:{pool_size}"
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "parallel evaluation unavailable (%s); running serially. Results are "
                "identical — only the wall clock differs.", error,
            )
            outcomes = []

    if not outcomes:
        mode = "serial"
        outcomes = [
            _evaluate(spec, slim, plan, list(features), label, step_sessions)
            for spec in specs
        ]

    results: list[ExperimentResult] = []
    failures: list[dict[str, Any]] = []
    already_reported = mode.startswith("parallel")
    for name, result, error in outcomes:
        if on_complete is not None and not already_reported:
            on_complete(name, result, error)
        if result is not None:
            results.append(result)
        else:
            failures.append({"model": name, "error": error})
            logger.warning("model %s failed: %s", name, (error or "").splitlines()[0])

    timing = {
        "mode": mode,
        "specs": len(specs),
        "succeeded": len(results),
        "failed": len(failures),
        "elapsed_s": round(time.perf_counter() - began, 2),
        "frame_mb": round(int(slim.memory_usage(deep=False).sum()) / 1024**2, 1),
        "columns_shipped": len(needed),
    }
    logger.info("parallel: %s", timing)
    return results, failures, timing
