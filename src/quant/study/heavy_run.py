"""
The staged search orchestrator — builds the panel once, runs four stages, writes
one artifact.

Separate from `heavy.py` (which holds the data structures, gates and
checkpointing) so the stage logic reads as a sequence rather than as a class
with eight responsibilities.

Everything scientific is delegated: the panel comes from `DatasetBuilder`, folds
from `build_plan`, fitting from `evaluate_specs`, backtests from `run_backtest`,
attribution and significance from their existing modules. This file decides
*what to evaluate next*, and nothing else.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.quant.study import search as space
from src.quant.study.heavy import (
    Checkpoint, ConfigResult, OVERFIT_GAP, SearchContext, _walk_forward_plan,
    competitive_families, evaluate_batch, evaluate_gates, rank_candidates,
    selection_verdict,
)

logger = logging.getLogger("omnisignal.quant.heavy_run")

#: The context every screen and tune configuration is evaluated in. Fixed so
#: Stage 1 and Stage 2 compare like with like; Stage 3 is what varies it.
REFERENCE_ARM = "C_base"
REFERENCE_TARGET = "fwd_rank_21"


class Progress:
    """Live progress with an ETA derived from measured throughput.

    The ETA comes from configurations actually completed in this run, not from
    the pre-run estimate — and it is withheld entirely until enough have
    finished to mean anything. A confident ETA computed from two samples is
    worse than no ETA.
    """

    MIN_SAMPLES_FOR_ETA = 6

    def __init__(self, total: int, monitor: Any = None) -> None:
        self.total = total
        self.done = 0
        self.failed = 0
        self.began = time.perf_counter()
        self.monitor = monitor
        self.best: Optional[ConfigResult] = None

    def record(self, result: ConfigResult) -> None:
        self.done += 1
        if not result.ok:
            self.failed += 1
        elif result.mean_ic is not None and (
            self.best is None or (self.best.mean_ic or -1e9) < result.mean_ic
        ):
            if (result.train_ic_gap or 0.0) <= OVERFIT_GAP:
                self.best = result

    def line(self, stage: str, detail: str = "") -> str:
        elapsed = time.perf_counter() - self.began
        pct = 100.0 * self.done / max(self.total, 1)
        parts = [
            f"[{self.done:>4}/{self.total}] {pct:5.1f}%  {stage:<10}",
            f"elapsed {elapsed / 3600:.2f}h",
        ]
        if self.done >= self.MIN_SAMPLES_FOR_ETA:
            rate = elapsed / self.done
            remaining = rate * (self.total - self.done)
            parts.append(f"eta {remaining / 3600:.2f}h")
        else:
            parts.append("eta —")
        if self.failed:
            parts.append(f"failed {self.failed}")
        if self.monitor is not None:
            parts.append(self.monitor.snapshot())
        if self.best is not None:
            parts.append(
                f"best {self.best.family} IC {self.best.mean_ic:+.4f} "
                f"t {self.best.ic_t_stat:+.2f}"
                if self.best.ic_t_stat is not None
                else f"best {self.best.family} IC {self.best.mean_ic:+.4f}"
            )
        if detail:
            parts.append(detail)
        return "  ·  ".join(parts)


def _pending(
    planned: list[tuple[str, str, dict[str, Any], str, str]],
    done: dict[str, ConfigResult],
) -> list[tuple[str, str, dict[str, Any], str, str]]:
    return [item for item in planned if item[0] not in done]


def run_search(
    experiment_id: str,
    *,
    budget_name: str = space.DEFAULT_BUDGET,
    root: str = "data/research",
    out_root: str = "experiments",
    workers: int = 6,
    seed: int = 0,
    resume: bool = True,
    monitor: Any = None,
) -> dict[str, Any]:
    """Run the four stages. Returns the artifact payload."""
    from src.quant.datasets.store import RawStore
    from src.quant.pit.dataset import DatasetBuilder
    from src.quant.pit.universe import UniverseHistory
    from src.quant.study.experiment import get_experiment, git_commit, git_dirty
    from src.quant.study.firewall import FIREWALL

    began = time.perf_counter()
    definition = get_experiment(experiment_id, seed)
    budget = space.BUDGETS[budget_name]
    output = Path(out_root) / experiment_id
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(output / "checkpoints" / "configs.jsonl")

    done = checkpoint.load() if resume else {}
    if done:
        print(f"resuming: {len(done)} configuration(s) already recorded\n")

    # ── panel, built once ────────────────────────────────────────────────
    print("[1/6] building the point-in-time panel (once, shared by every fit)")
    store = RawStore(root)
    universe = UniverseHistory.load(Path(root) / "universe")
    dataset = DatasetBuilder(store, universe).build(
        start=definition.start,
        end=definition.end or Date.today(),
        step_sessions=definition.step_sessions,
        workers=workers,
    )
    frame, manifest = dataset.frame, dataset.manifest
    cross = [c for c in manifest.features if c.endswith("_xs")]
    macro = [c for c in manifest.features if c.startswith(("rates_", "market_"))]
    context = SearchContext(
        frame=frame, manifest=manifest, calendar=dataset.calendar,
        available_features=cross + macro,
    )
    print(f"      {manifest.rows:,} rows · {manifest.symbols} symbols · "
          f"{manifest.dates} dates · hash {manifest.content_hash}")
    print(f"      guards {manifest.guard_report['total'] - manifest.guard_report['failed']}"
          f"/{manifest.guard_report['total']}")

    # Cut the reference plan now rather than lazily inside the first batch. It
    # reserves the holdout and arms the firewall, and doing it here means a
    # fully-resumed run — every configuration already recorded — still has the
    # fold geometry it must report in the artifact.
    reference_plan = _walk_forward_plan(context, REFERENCE_TARGET, definition)
    print(f"      folds {len(reference_plan.folds)} · holdout "
          f"{reference_plan.holdout_start} to {reference_plan.holdout_end} — SEALED")

    plan = space.build_plan(budget_name, seed=seed)
    projection = space.projected_total(budget)
    total_planned = projection["total_configs"]
    progress = Progress(total_planned, monitor=monitor)
    for result in done.values():
        progress.record(result)

    # ── stage 1: screen ──────────────────────────────────────────────────
    print(f"\n[2/6] STAGE 1 screen — {budget.screen_total} configurations, "
          f"{REFERENCE_ARM} / {REFERENCE_TARGET}")
    planned: list[tuple[str, str, dict[str, Any], str, str]] = []
    for family, configs in plan.screen.items():
        for index, params in enumerate(configs):
            cid = space.config_id(family, "screen", index, params)
            planned.append((cid, family, params, REFERENCE_ARM, REFERENCE_TARGET))

    screen_results = [done[c[0]] for c in planned if c[0] in done]
    pending = _pending(planned, done)
    if pending:
        screen_results += evaluate_batch(
            pending, context, definition, workers=workers, stage="screen",
            checkpoint=checkpoint,
            on_result=lambda r: (progress.record(r),
                                 print(progress.line("screen", r.family))),
        )
    else:
        print("      all screen configurations already recorded")

    advancing = competitive_families(screen_results, keep=budget.tune_families)
    print(f"\n      families advancing to tuning: {advancing}")

    # ── stage 2: tune ────────────────────────────────────────────────────
    tune_planned: list[tuple[str, str, dict[str, Any], str, str]] = []
    for family in advancing:
        count = budget.tune.get(family, 0)
        for index, params in enumerate(
            space.sample_configs(family, count, stage="tune", seed=seed)
        ):
            cid = space.config_id(family, "tune", index, params)
            tune_planned.append((cid, family, params, REFERENCE_ARM, REFERENCE_TARGET))

    print(f"\n[3/6] STAGE 2 tune — {len(tune_planned)} configurations across {len(advancing)} families")
    tune_results = [done[c[0]] for c in tune_planned if c[0] in done]
    pending = _pending(tune_planned, done)
    if pending:
        tune_results += evaluate_batch(
            pending, context, definition, workers=workers, stage="tune",
            checkpoint=checkpoint,
            on_result=lambda r: (progress.record(r),
                                 print(progress.line("tune", r.family))),
        )
    else:
        print("      all tuning configurations already recorded")

    ranked = rank_candidates(screen_results + tune_results)
    finalists = ranked[: budget.finalists]
    print(f"\n      finalists: " + ", ".join(
        f"{r.family}(IC {r.mean_ic:+.4f}, t {r.ic_t_stat:+.2f})" for r in finalists
        if r.ic_t_stat is not None
    ))

    # ── stage 3: context ─────────────────────────────────────────────────
    context_planned: list[tuple[str, str, dict[str, Any], str, str]] = []
    for finalist in finalists:
        for arm in space.CONTEXT_ARMS:
            for target in space.CONTEXT_TARGETS:
                if arm == REFERENCE_ARM and target == REFERENCE_TARGET:
                    continue          # already measured in stage 1/2
                cid = space.config_id(
                    finalist.family, f"context:{arm}:{target}", 0, finalist.params
                )
                context_planned.append(
                    (cid, finalist.family, finalist.params, arm, target)
                )

    print(f"\n[4/6] STAGE 3 context — {len(context_planned)} evaluations "
          f"({len(space.CONTEXT_ARMS)} arms x {len(space.CONTEXT_TARGETS)} targets)")
    context_results = [done[c[0]] for c in context_planned if c[0] in done]
    pending = _pending(context_planned, done)
    if pending:
        context_results += evaluate_batch(
            pending, context, definition, workers=workers, stage="context",
            checkpoint=checkpoint,
            on_result=lambda r: (progress.record(r),
                                 print(progress.line("context", f"{r.arm}/{r.target}"))),
        )

    # ── stage 4: robustness ──────────────────────────────────────────────
    robustness_planned: list[tuple[str, str, dict[str, Any], str, str]] = []
    for finalist in finalists:
        for index, params in enumerate(
            space.neighbours(finalist.family, finalist.params,
                             budget.neighbours_per_finalist, seed=seed)
        ):
            cid = space.config_id(finalist.family, f"neighbour:{finalist.config_id}",
                                  index, params)
            robustness_planned.append(
                (cid, finalist.family, params, REFERENCE_ARM, REFERENCE_TARGET)
            )

    print(f"\n[5/6] STAGE 4 robustness — {len(robustness_planned)} neighbour configurations")
    robustness_results = [done[c[0]] for c in robustness_planned if c[0] in done]
    pending = _pending(robustness_planned, done)
    if pending:
        robustness_results += evaluate_batch(
            pending, context, definition, workers=workers, stage="robustness",
            checkpoint=checkpoint,
            on_result=lambda r: (progress.record(r),
                                 print(progress.line("robustness", r.family))),
        )

    # ── artifact ─────────────────────────────────────────────────────────
    print("\n[6/6] writing the artifact")
    everything = screen_results + tune_results + context_results + robustness_results
    evaluated = len(everything)
    failures = [r for r in everything if not r.ok]

    mt = space.multiple_testing_cost(evaluated, prior=definition.prior_evaluations)
    payload: dict[str, Any] = {
        "experiment": definition.as_dict(),
        "fingerprint": definition.fingerprint(),
        "search": {
            "budget": budget.as_dict(),
            "projection": projection,
            "reference_context": {"arm": REFERENCE_ARM, "target": REFERENCE_TARGET},
            "families_advanced": advancing,
            "configurations_evaluated": evaluated,
            "configurations_failed": len(failures),
            "multiple_testing": mt,
        },
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workers": workers,
        "dataset": manifest.as_dict(),
        "universe": universe.summary(),
        "holdout": {
            "start": str(context.plans[REFERENCE_TARGET].holdout_start),
            "end": str(context.plans[REFERENCE_TARGET].holdout_end),
            "touched": False,
            "note": "Reserved before any fold was cut; the firewall refuses its rows.",
        },
        "firewall": FIREWALL.status(),
        "results": [r.as_dict() for r in everything],
        "runtime_seconds": round(time.perf_counter() - began, 1),
        "complete": not failures,
    }
    (output / "search.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    print(f"      wrote {output}/search.json  "
          f"({(output / 'search.json').stat().st_size / 1024:.0f} KB)")
    return payload
