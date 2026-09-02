"""
Read layer for staged searches (EXP-007 and EXP-007-WIN-GPU).

Two states, and the difference matters to anyone reading the page:

**RUNNING** — `search.json` does not exist yet, but the append-only checkpoint
does. Everything here is then a partial view of a search still in flight, and it
is labelled that way. A leaderboard from a partial search is not a result; it is
progress.

**COMPLETE** — `search.json` exists. The numbers are final and the selection
step can run against them.

Nothing in this module computes a verdict, ranks a production candidate, or
touches the holdout. It reads two files and counts. Selection happens in
`scripts/quant/select_candidate.py`, behind the predeclared gates, and its
output is `final_selection.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

DEFAULT_ROOT = Path("experiments")

#: Train-minus-validation IC above which a configuration is OVERFIT. The same
#: constant as `study.heavy.OVERFIT_GAP` and `quant_service.OVERFIT_GAP`;
#: duplicated as a literal here so the read layer does not import the research
#: package, which the minimal inference runtime does not ship.
OVERFIT_GAP = 0.15

#: Stages in declaration order, so the UI renders them as a sequence rather than
#: in whatever order a dict happens to iterate.
STAGES = ("screen", "tune", "context", "robustness")


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_checkpoint(path: Path) -> list[dict[str, Any]]:
    """Every recorded configuration. Torn final lines are skipped, not guessed."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a crash mid-write; the last line only
    return rows


def _classify(row: dict[str, Any]) -> str:
    """UNDERFIT / HEALTHY / OVERFIT / UNSTABLE / FAILED — never a number alone.

    The order is deliberate. A configuration with a large generalisation gap is
    OVERFIT whatever its validation IC, because the gap is the thing that
    predicts what happens next. Fold instability is checked before strength, so
    a model that is right on average and wrong half the time is not called
    healthy.
    """
    if not row.get("ok"):
        return "FAILED"
    gap = row.get("train_ic_gap")
    ic = row.get("mean_ic")
    positive_rate = row.get("fold_ic_positive_rate")
    if gap is not None and gap > OVERFIT_GAP:
        return "OVERFIT"
    if positive_rate is not None and positive_rate < 0.5:
        return "UNSTABLE"
    if ic is None or abs(ic) < 0.005:
        return "UNDERFIT"
    return "HEALTHY"


def _expected_max_abs_t(trials: int) -> Optional[float]:
    """E[max |t|] over `trials` zero-skill configurations.

    Returned as None rather than a fallback constant when scipy is absent: a
    made-up threshold on a page about multiple testing would be worse than an
    empty cell.
    """
    if trials < 1:
        return None
    try:
        import math

        from scipy import stats

        return round(float(stats.norm.ppf(1.0 - 1.0 / (trials * math.e))), 2)
    except Exception:  # noqa: BLE001
        return None


def _declared_total(experiment_id: str) -> Optional[int]:
    """The configuration count the study declared, if the research package is here.

    Read from the declared budget rather than guessed, and None when the package
    is absent — the minimal inference runtime does not ship it, and a fabricated
    denominator on a progress bar is still a fabricated number.
    """
    try:
        from src.quant.study.experiment import get_experiment
        from src.quant.study.search import BUDGETS, projected_total

        budget_name = get_experiment(experiment_id).search_budget
        if not budget_name:
            return None
        return int(projected_total(BUDGETS[budget_name])["total_configs"])
    except Exception:  # noqa: BLE001
        return None


def _leaderboard(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    """Best configurations by validation IC, with overfit ones pushed down.

    Rejected configurations are NOT removed. A leaderboard that hides what
    failed is a sales page; the overfit rows are the evidence that the
    diagnostic is doing work.
    """
    usable = [r for r in rows if r.get("ok") and r.get("mean_ic") is not None]
    ranked = sorted(
        usable,
        key=lambda r: ((r.get("train_ic_gap") or 0.0) > OVERFIT_GAP,
                       -(r.get("mean_ic") or 0.0)),
    )
    return [
        {
            "config_id": r.get("config_id"),
            "family": r.get("family"),
            "stage": r.get("stage"),
            "arm": r.get("arm"),
            "target": r.get("target"),
            "params": r.get("params"),
            "feature_count": r.get("feature_count"),
            "mean_ic": r.get("mean_ic"),
            "ic_t_stat": r.get("ic_t_stat"),
            "ic_ir": r.get("ic_ir"),
            "train_mean_ic": r.get("train_mean_ic"),
            "train_ic_gap": r.get("train_ic_gap"),
            "fold_ic_positive_rate": r.get("fold_ic_positive_rate"),
            "folds": r.get("folds"),
            "seconds": r.get("seconds"),
            "diagnosis": _classify(r),
        }
        for r in ranked[:limit]
    ]


def _families(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-family summary: best non-overfit configuration, and how many overfit."""
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        family = row.get("family")
        if not family:
            continue
        entry = summary.setdefault(family, {
            "family": family, "evaluated": 0, "failed": 0, "overfit": 0,
            "best_ic": None, "best_t": None, "best_gap": None,
            "worst_gap": None, "seconds": 0.0,
        })
        entry["evaluated"] += 1
        entry["seconds"] += float(row.get("seconds") or 0.0)
        if not row.get("ok"):
            entry["failed"] += 1
            continue
        gap = row.get("train_ic_gap")
        if gap is not None:
            entry["worst_gap"] = max(entry["worst_gap"] or gap, gap)
            if gap > OVERFIT_GAP:
                entry["overfit"] += 1
                continue        # an overfit config cannot be a family's best
        ic = row.get("mean_ic")
        if ic is not None and (entry["best_ic"] is None or ic > entry["best_ic"]):
            entry["best_ic"] = ic
            entry["best_t"] = row.get("ic_t_stat")
            entry["best_gap"] = gap
    for entry in summary.values():
        entry["seconds"] = round(entry["seconds"], 1)
    return sorted(summary.values(),
                  key=lambda e: -(e["best_ic"] if e["best_ic"] is not None else -1e9))


def search(experiment_id: str, root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """The state of a staged search: RUNNING, COMPLETE, or NOT STARTED."""
    root = Path(root)
    directory = root / experiment_id
    artifact = _read_json(directory / "search.json")
    rows = _read_checkpoint(directory / "checkpoints" / "configs.jsonl")

    if artifact is None and not rows:
        return {
            "available": False,
            "experiment_id": experiment_id,
            "state": "NOT STARTED",
            "detail": (
                f"No search has been run for {experiment_id}. Nothing is inferred "
                "from its absence."
            ),
        }

    # A completed artifact is the authority on its own results. The checkpoint is
    # only consulted for live progress, and only while the artifact is missing.
    if artifact is not None:
        rows = artifact.get("results", rows)
    block = artifact.get("search", {}) if artifact else {}
    projection = block.get("projection") or {}
    planned = projection.get("total_configs") or _declared_total(experiment_id)

    evaluated = len(rows)
    failed = sum(1 for r in rows if not r.get("ok"))
    diagnoses: dict[str, int] = {}
    for row in rows:
        label = _classify(row)
        diagnoses[label] = diagnoses.get(label, 0) + 1

    stages: list[dict[str, Any]] = []
    for stage in STAGES:
        members = [r for r in rows if r.get("stage") == stage]
        if not members:
            continue
        stages.append({
            "stage": stage,
            "evaluated": len(members),
            "failed": sum(1 for r in members if not r.get("ok")),
            "worker_seconds": round(sum(float(r.get("seconds") or 0.0) for r in members), 1),
        })

    observed = [abs(r["ic_t_stat"]) for r in rows
                if r.get("ok") and isinstance(r.get("ic_t_stat"), (int, float))]
    multiple_testing = dict(block.get("multiple_testing") or {})
    if not multiple_testing:
        # Still running: the artifact has not written the correction yet.
        #
        # The bar is computed at the DECLARED total, not the count reached so
        # far. Using the running count would show a threshold that rises under
        # the reader all night and — worse — would let a mid-run configuration
        # look like it clears a bar it will not face. The declared total is the
        # bar this search actually has to beat.
        prior = 156
        budgeted = planned if planned else evaluated
        cumulative = prior + budgeted
        multiple_testing = {
            "prior_trials": prior,
            "new_trials": budgeted,
            "cumulative_trials": cumulative,
            "expected_max_abs_t_under_null": _expected_max_abs_t(cumulative),
            "provisional": True,
            "basis": (
                "declared budget" if planned else "configurations recorded so far"
            ),
        }
    multiple_testing["observed_max_abs_t"] = round(max(observed), 2) if observed else None
    threshold = multiple_testing.get("expected_max_abs_t_under_null")
    multiple_testing["observed_clears_threshold"] = (
        None if threshold is None or not observed else max(observed) > threshold
    )
    # Clearing the IC t-stat bar is necessary, never sufficient. EXP-006 posted
    # t = +2.66 and still failed on net Sharpe. The UI must not render this as a
    # verdict, so the caveat travels with the number.
    multiple_testing["caveat"] = (
        "Clearing this threshold is necessary, not sufficient. It is one of eight "
        "gates; EXP-006 cleared three and failed on net Sharpe."
    )

    state = "COMPLETE" if artifact is not None else "RUNNING"
    return {
        "available": True,
        "experiment_id": experiment_id,
        "state": state,
        "complete": bool(artifact and artifact.get("complete")),
        "configurations_evaluated": evaluated,
        "configurations_planned": planned,
        "configurations_failed": failed,
        "progress_pct": (
            round(100.0 * evaluated / planned, 1)
            if planned and planned > 0 else None
        ),
        "stages": stages,
        "families": _families(rows),
        "diagnoses": diagnoses,
        "leaderboard": _leaderboard(rows),
        "multiple_testing": multiple_testing,
        "budget": block.get("budget"),
        "families_advanced": block.get("families_advanced"),
        "reference_context": block.get("reference_context"),
        "dataset": (artifact or {}).get("dataset"),
        "machine": (artifact or {}).get("machine"),
        "package_versions": (artifact or {}).get("package_versions"),
        "git_commit": (artifact or {}).get("git_commit"),
        "git_dirty": (artifact or {}).get("git_dirty"),
        "workers": (artifact or {}).get("workers"),
        "runtime_seconds": (artifact or {}).get("runtime_seconds"),
        "generated_at": (artifact or {}).get("generated_at"),
        "holdout": (artifact or {}).get("holdout", {
            "touched": False,
            "note": "Reserved before any fold was cut; the firewall refuses its rows.",
        }),
        "note": (
            "PARTIAL — this search is still running. These are the configurations "
            "recorded so far, not a result. The multiple-testing correction is "
            "provisional because the final trial count is not yet known."
            if state == "RUNNING" else
            "Complete. Selection runs separately, behind the predeclared gates."
        ),
    }


#: Gates added to the standard on 2026-09-01, after EXP-007 was already
#: selected. An artifact written before that date records eight gates; the
#: current standard has ten.
_STANDARD_ADDED_2026_09_01 = ("deflated_sharpe", "selection_carries_information")


def _restate_under_current_standard(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Re-evaluate a recorded selection against the gate standard in force today.

    This does not refit anything and does not alter the artifact. It reads the
    numbers the run recorded — the deflated-Sharpe probability and the PBO were
    already computed and stored — and applies the two gates that were added
    afterwards.

    The reason this exists rather than being left to a re-run: an artifact
    written under the eight-gate standard says "failed 1 of 8" while carrying a
    deflated-Sharpe probability of 0.06 and a PBO of 0.93 in the same file. A
    reader seeing both is entitled to a straight answer about which standard
    applies. Re-running selection to regenerate the artifact would cost an hour
    of compute to change a count, so the count is derived instead and labelled.

    Returns None when the artifact already carries the current gates, or when
    the inputs needed are absent.
    """
    verdict = payload.get("verdict") or {}
    recorded = [g.get("gate") for g in verdict.get("gates", [])]
    if not recorded or all(g in recorded for g in _STANDARD_ADDED_2026_09_01):
        return None

    selected = (payload.get("selected") or {}).get("config_id")
    significance = (payload.get("significance") or {}).get(selected) or {}
    deflated = (significance.get("deflated_sharpe") or {}).get("deflated_probability")
    pbo = (payload.get("probability_of_backtest_overfitting") or {}).get("pbo")
    if deflated is None and pbo is None:
        return None

    added = [
        {
            "gate": "deflated_sharpe",
            "passed": deflated is not None and deflated > 0.95,
            "observed": deflated,
            "required": "> 0.95 — the probability the Sharpe survives deflation "
                        "against the trial count, their dispersion, and the return "
                        "distribution's skew and kurtosis",
        },
        {
            "gate": "selection_carries_information",
            "passed": pbo is not None and pbo <= 0.20,
            "observed": pbo,
            "required": "PBO <= 0.2 — the in-sample winner must not land in the "
                        "bottom half out-of-sample",
        },
    ]
    gates = list(verdict.get("gates", [])) + added
    failed = [g["gate"] for g in gates if not g["passed"]]
    return {
        "gates": gates,
        "failed": failed,
        "passed": not failed,
        "status": "DEVELOPMENT CANDIDATE" if not failed else "NO PRODUCTION CANDIDATE",
        "restated": True,
        "note": (
            "The artifact was written under the eight-gate standard. Two gates were "
            "added on 2026-09-01 and are applied here to the numbers the run already "
            "recorded — nothing was refit. The added gates make promotion strictly "
            "harder; they cannot turn a refusal into a pass."
        ),
    }


def _decision_envelopes(payload: dict[str, Any]) -> dict[str, Any]:
    """The decision-bearing numbers, each with its own provenance.

    These six are the ones a reader acts on, and each carries a methodology that
    changes what the number means. A net Sharpe without its cost assumption and
    a PBO without its estimator are both unfalsifiable, so the methodology
    travels with the value rather than sitting in a caption somewhere.

    Everything here is `recorded`: read from a committed artifact, where age is
    provenance rather than decay.
    """
    from src.services.envelope import DataEnvelope, envelope_dict

    selected = (payload.get("selected") or {}).get("config_id")
    economics = (payload.get("economics") or {}).get(selected) or {}
    significance = (payload.get("significance") or {}).get(selected) or {}
    deflated = significance.get("deflated_sharpe") or {}
    pbo = payload.get("probability_of_backtest_overfitting") or {}
    mt = payload.get("multiple_testing") or {}
    source = payload.get("search_artifact") or "artifacts/experiments/.../final_selection.json"

    def recorded(value: Any, method: str, unit: Optional[str] = None) -> Any:
        if value is None:
            return DataEnvelope.unavailable(source, f"not recorded: {method}")
        return DataEnvelope.recorded(value, source, method=method, unit=unit)

    return envelope_dict(
        net_sharpe=recorded(
            economics.get("net_sharpe"),
            "annualised, after commission, the declared 10 bp half-spread, "
            "slippage and square-root impact; 8 expanding walk-forward folds",
            "Sharpe",
        ),
        gross_sharpe=recorded(
            economics.get("gross_sharpe"),
            "annualised, before any cost is charged; same folds",
            "Sharpe",
        ),
        ic_t_stat=recorded(
            economics.get("ic_t_stat"),
            "Newey-West with a Bartlett kernel, correcting for the 21-session "
            "label overlap",
            "t",
        ),
        alpha_t_stat=recorded(
            economics.get("alpha_t_stat"),
            "intercept of a six-factor regression (Fama-French 5 plus momentum) "
            "on the net return series",
            "t",
        ),
        deflated_sharpe_probability=recorded(
            deflated.get("deflated_probability"),
            f"Bailey & Lopez de Prado, deflated against "
            f"{mt.get('cumulative_trials', 'the cumulative')} trials, their "
            "dispersion, and the return distribution's skew and kurtosis",
        ),
        pbo=recorded(
            pbo.get("pbo"),
            f"combinatorially symmetric cross-validation over "
            f"{pbo.get('splits_evaluated', 'n')} splits of "
            f"{pbo.get('blocks', 'n')} blocks",
        ),
    )


def selection(experiment_id: str,
              artifacts_root: Path | str = Path("artifacts/experiments")) -> dict[str, Any]:
    """The gate verdict, if `select_candidate` has been run."""
    payload = _read_json(Path(artifacts_root) / experiment_id / "final_selection.json")
    if payload is None:
        return {
            "available": False,
            "experiment_id": experiment_id,
            "detail": (
                "No selection has been run. A search produces configurations; the "
                "verdict comes from scripts/quant/select_candidate.py, which "
                "applies the predeclared gates."
            ),
        }
    restated = _restate_under_current_standard(payload)
    return {
        "available": True,
        **payload,
        # `verdict` stays exactly as recorded — the artifact is the record.
        # `current_standard` is the derivation, clearly named as one.
        **({"current_standard": restated} if restated else {}),
        # Each decision-bearing number with its own source, status and method.
        # Additive: existing consumers are untouched.
        "envelopes": _decision_envelopes(payload),
    }
