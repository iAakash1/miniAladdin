"""
Quant research service — the read layer over `experiments/`.

## Read-only, and never a substitute

Like `ml_service`, this never trains, never backtests and never ingests. It
reads the artifacts a study wrote and shapes them for the API. When no
experiment exists it says so and names the command that would produce one; it
does not compute a cheap approximation, because a reader cannot distinguish a
cheap approximation from a rigorous result once both are rendered as a number.

## The verdict is computed from gates, never written down

`verdict()` is the one function here doing real work, and it exists so that no
part of the product can label a model anything the evidence does not support.
It reads `CANDIDATE_THRESHOLDS` from the model registry — the same constants
`promote()` enforces — so a card reading PROMISING and a promotion refusal can
never disagree. The labels are ordered and mutually exclusive:

    REJECTED     a blocking control failed, or integrity failed
    OVERFIT      train IC exceeds validation IC by more than OVERFIT_GAP
    UNTRADEABLE  positive IC, but gross or net Sharpe is negative
    EXPERIMENTAL measured, and does not clear the candidate bars
    PROMISING    clears every candidate bar, holdout not yet spent
    ROBUST       clears the candidate bars AND the holdout thresholds

`ROBUST` is unreachable while the holdout is locked, which is correct: nothing
in development can earn that word.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("omnisignal.services.quant")

DEFAULT_ROOT = Path("experiments")
METRICS_NAME = "metrics.json"

#: Train-minus-validation IC above which a model is called overfit regardless of
#: what else it does. EXP-004's deliberately over-parameterised control sat at
#: +0.721 and every tree model between +0.18 and +0.39.
OVERFIT_GAP = 0.15

#: Models that exist to prove a diagnostic fires, not to be candidates.
#:
#: `gradient_boosting_deep` is deliberately over-parameterised. It is in the
#: ladder so the train/validation gap diagnostic can be shown to work — and it
#: does, at +0.729. Because it also tends to post the highest raw IC, a naive
#: "best model" selection picks it, and the page then presents the control as
#: the study's strongest evidence. That is backwards: the control's high IC is
#: the thing being warned about.
#:
#: It stays in every table, marked. It is only excluded from "best".
OVERFIT_CONTROL_MODELS: frozenset[str] = frozenset({"gradient_boosting_deep"})

#: Studies whose results a later audit invalidated. Never deleted — removing one
#: would erase the multiple-testing exposure it created.
VOID_EXPERIMENTS: dict[str, str] = {
    "EXP-002": (
        "VOID — invalidated by the pandas.merge_asof index-reset defect. 12 of 39 "
        "features carried other rows' values. Retained because the evaluations it "
        "consumed still count against the cumulative trial total."
    ),
}


def _read(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("quant: cannot read %s (%s)", path, error)
        return None


def _unavailable(detail: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "detail": detail,
        "remedy": "python -m src.quant.study.run --experiment EXP-005",
    }


def _experiment_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)


# ── verdict ─────────────────────────────────────────────────────────────────


def verdict(
    model: dict[str, Any],
    *,
    controls_passed: bool = True,
    integrity_clean: bool = True,
    holdout_spent: bool = False,
) -> dict[str, Any]:
    """Label a model from its measured numbers and the promotion gates.

    Returns the label, the reason, and every gate with its observed value — so
    a UI can render *why* rather than only *what*, and a reader can disagree
    with the conclusion while seeing the same evidence.
    """
    from src.quant.models.registry import CANDIDATE_THRESHOLDS

    ic = model.get("mean_ic")
    t_stat = model.get("ic_t_stat")
    gross = model.get("gross_sharpe")
    net = model.get("net_sharpe")
    train_gap = model.get("train_ic_gap")

    gates = {
        "ic_t_stat": {
            "observed": t_stat,
            "required": f">= {CANDIDATE_THRESHOLDS['ic_t_stat']['minimum']} (absolute)",
            "passed": t_stat is not None and abs(t_stat) >= CANDIDATE_THRESHOLDS["ic_t_stat"]["minimum"],
        },
        "gross_sharpe": {
            "observed": gross,
            "required": "> 0",
            "passed": gross is not None and gross > 0,
        },
        "net_sharpe": {
            "observed": net,
            "required": "> 0",
            "passed": net is not None and net > 0,
        },
        "beats_best_baseline": {
            "observed": model.get("beats_best_baseline"),
            "required": "True",
            "passed": bool(model.get("beats_best_baseline")),
        },
    }

    if not integrity_clean:
        label, reason = "REJECTED", "dataset integrity check failed; no result from this run is admissible"
    elif not controls_passed:
        label, reason = "REJECTED", "a blocking negative control found signal; the pipeline manufactures it"
    elif train_gap is not None and train_gap > OVERFIT_GAP:
        label, reason = "OVERFIT", (
            f"train IC exceeds validation IC by {train_gap:+.3f}, above the {OVERFIT_GAP} "
            "threshold — the model fits its training fold and carries almost none of it forward"
        )
    elif ic is not None and ic > 0 and (
        (gross is not None and gross <= 0) or (net is not None and net <= 0)
    ):
        label, reason = "UNTRADEABLE", (
            "the ranking carries positive information but does not survive becoming a "
            f"book: gross Sharpe {gross}, net Sharpe {net}"
        )
    elif all(g["passed"] for g in gates.values()):
        if holdout_spent:
            label, reason = "ROBUST", "clears every development gate and the holdout thresholds"
        else:
            label, reason = "PROMISING", (
                "clears every development gate. Not ROBUST: the holdout has not been "
                "spent, and nothing measured in development can earn that word"
            )
    else:
        failed = [name for name, g in gates.items() if not g["passed"]]
        label, reason = "EXPERIMENTAL", f"measured, and does not clear: {', '.join(failed)}"

    # The label names the WORST property, which can bury a more decision-relevant
    # one. EXP-006's gradient_boosting is OVERFIT at a gap of 0.162 *and* the
    # closest thing to a candidate this project has produced — it clears three of
    # four gates and fails only net Sharpe. A card reading OVERFIT with no further
    # detail would hide that, so the remaining gate state is appended rather than
    # the threshold being moved to produce a friendlier label.
    unmet = [name for name, g in gates.items() if not g["passed"]]
    cleared = [name for name, g in gates.items() if g["passed"]]
    if label in {"OVERFIT", "UNTRADEABLE"} and cleared:
        reason += (
            f". Gates cleared: {', '.join(cleared)}"
            + (f"; still failing: {', '.join(unmet)}" if unmet else "; no gate outstanding")
        )

    return {
        "label": label,
        "reason": reason,
        "gates": gates,
        "gates_cleared": cleared,
        "gates_failed": unmet,
    }


# ── endpoints ───────────────────────────────────────────────────────────────


def experiments(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """Every experiment on disk, newest first, with void ones marked."""
    root = Path(root)
    rows: list[dict[str, Any]] = []
    for directory in _experiment_dirs(root):
        metrics = _read(directory / METRICS_NAME)
        experiment_id = directory.name
        row: dict[str, Any] = {
            "experiment_id": experiment_id,
            "void": experiment_id in VOID_EXPERIMENTS,
            "void_reason": VOID_EXPERIMENTS.get(experiment_id),
        }
        if metrics is None:
            row.update({"status": "unreadable", "detail": "no metrics.json"})
            rows.append(row)
            continue
        definition = metrics.get("experiment", {})
        dataset = metrics.get("dataset", {})
        row.update({
            "status": "complete",
            "objective": definition.get("objective"),
            "fingerprint": metrics.get("fingerprint"),
            "generated_at": metrics.get("generated_at"),
            "git_commit": metrics.get("git_commit"),
            "targets": definition.get("targets", []),
            "primary_target": definition.get("primary_target"),
            "model_count": definition.get("model_count"),
            "declared_evaluations": definition.get("declared_evaluations"),
            "cumulative_evaluations": definition.get("cumulative_evaluations"),
            "execution_lag_periods": definition.get("execution_lag_periods"),
            "dataset_version": dataset.get("dataset_version"),
            "rows": dataset.get("rows"),
            "symbols": dataset.get("symbols"),
            "dates": dataset.get("dates"),
            "feature_count": len(metrics.get("features_used", [])),
            "integrity_clean": metrics.get("integrity", {}).get("clean"),
            "holdout_touched": metrics.get("holdout", {}).get("touched"),
            "runtime_seconds": metrics.get("runtime_seconds"),
        })
        rows.append(row)

    known_void = [
        {"experiment_id": eid, "void": True, "void_reason": reason, "status": "void_no_artifact"}
        for eid, reason in VOID_EXPERIMENTS.items()
        if not any(r["experiment_id"] == eid for r in rows)
    ]
    return {
        "status": "ok" if rows else "unavailable",
        "experiments": rows + known_void,
        "total": len(rows) + len(known_void),
    }


def experiment(experiment_id: str, root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """One experiment in full: leaderboard, ablation, controls, regimes."""
    root = Path(root)
    metrics = _read(root / experiment_id / METRICS_NAME)
    if metrics is None:
        return _unavailable(f"no artifact for {experiment_id}")

    definition = metrics.get("experiment", {})
    primary = definition.get("primary_target")
    label_block = (metrics.get("labels") or {}).get(primary, {})
    controls = metrics.get("negative_controls", {})
    integrity = metrics.get("integrity", {})

    controls_passed = not controls.get("blocking_failed")
    integrity_clean = bool(integrity.get("clean"))

    backtests = label_block.get("backtests", {})
    significance = label_block.get("significance", {})
    leaderboard: list[dict[str, Any]] = []
    baseline_ics = [
        r.get("mean_ic") for r in label_block.get("leaderboard", [])
        if r.get("kind") == "baseline" and r.get("mean_ic") is not None
    ]
    best_baseline = max(baseline_ics) if baseline_ics else None

    for row in label_block.get("leaderboard", []):
        backtest = (backtests.get(row["model_id"]) or {}).get("metrics", {})
        entry = {
            "model_id": row["model_id"],
            "kind": row.get("kind"),
            "mean_ic": row.get("mean_ic"),
            "ic_t_stat": row.get("ic_t_stat"),
            "train_mean_ic": row.get("train_mean_ic"),
            "train_ic_gap": row.get("train_ic_gap"),
            "fold_ic_positive_rate": row.get("fold_ic_positive_rate"),
            "gross_sharpe": backtest.get("gross_sharpe"),
            "net_sharpe": backtest.get("net_sharpe"),
            "max_drawdown": backtest.get("net_max_drawdown"),
            "annualised_turnover": backtest.get("annualised_turnover"),
            "cost_share_of_gross": backtest.get("cost_share_of_gross"),
            # Nested under `deflated_sharpe`, not flat. Reading the wrong path
            # silently yields None, which the UI renders as an em dash — an
            # absent correction looks identical to a correction that was never
            # computed, so the mistake is invisible in the rendered page.
            "deflated_sharpe_probability": (
                (significance.get(row["model_id"]) or {}).get("deflated_sharpe") or {}
            ).get("deflated_probability"),
            "deflated_sharpe_trials": (
                (significance.get(row["model_id"]) or {}).get("deflated_sharpe") or {}
            ).get("trials"),
            "beats_best_baseline": (
                None if row.get("mean_ic") is None or best_baseline is None
                else row["mean_ic"] > best_baseline
            ),
        }
        entry["is_overfit_control"] = row["model_id"] in OVERFIT_CONTROL_MODELS
        entry["verdict"] = verdict(
            entry, controls_passed=controls_passed, integrity_clean=integrity_clean,
        )
        leaderboard.append(entry)

    return {
        "status": "ok",
        "experiment_id": experiment_id,
        "void": experiment_id in VOID_EXPERIMENTS,
        "void_reason": VOID_EXPERIMENTS.get(experiment_id),
        "definition": definition,
        "fingerprint": metrics.get("fingerprint"),
        "generated_at": metrics.get("generated_at"),
        "git_commit": metrics.get("git_commit"),
        "machine": metrics.get("machine"),
        "runtime_seconds": metrics.get("runtime_seconds"),
        "dataset": metrics.get("dataset"),
        "universe": metrics.get("universe"),
        "features_used": metrics.get("features_used", []),
        "dataset_sources": (metrics.get("dataset") or {}).get("source_datasets", []),
        "integrity": integrity,
        "negative_controls": controls,
        "holdout": metrics.get("holdout"),
        "firewall": metrics.get("firewall"),
        "regimes": metrics.get("regimes"),
        "primary_target": primary,
        "leaderboard": leaderboard,
        # The strongest *candidate* evidence: best learned model excluding the
        # deliberately over-parameterised control. Computed here so every surface
        # agrees on what "best" means.
        "best_candidate": max(
            (
                r for r in leaderboard
                if r.get("kind") != "baseline"
                and not r["is_overfit_control"]
                and r.get("mean_ic") is not None
            ),
            key=lambda r: r["mean_ic"],
            default=None,
        ),
        "best_baseline": max(
            (r for r in leaderboard if r.get("kind") == "baseline" and r.get("mean_ic") is not None),
            key=lambda r: r["mean_ic"],
            default=None,
        ),
        "walk_forward_plan": label_block.get("walk_forward_plan"),
        "fold_rows": label_block.get("fold_rows"),
        "cost_sensitivity": label_block.get("cost_sensitivity"),
        # Six-factor attribution, per model. Surfaced because the alpha t-stat is
        # the number that separates "this returned something" from "this returned
        # something the factor model does not already explain" — and it is the one
        # a leaderboard sorted by Sharpe will never show you.
        "factor_attribution": label_block.get("factor_attribution"),
        "regime_performance": label_block.get("regime_performance"),
        "probability_of_backtest_overfitting": label_block.get(
            "probability_of_backtest_overfitting"
        ),
        "experiment_distribution": label_block.get("experiment_distribution"),
        "trials_used_for_correction": label_block.get("trials_used_for_correction"),
        "ablation": metrics.get("ablation"),
    }


def latest(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """The newest non-void experiment. What the landing page renders."""
    listing = experiments(root)
    live = [
        e for e in listing["experiments"]
        if not e["void"] and e.get("status") == "complete"
    ]
    if not live:
        return _unavailable("no completed experiment on disk")
    newest = max(live, key=lambda e: e.get("generated_at") or "")
    return experiment(newest["experiment_id"], root)


def production_status(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """What the product is allowed to serve. The honest empty state.

    Deliberately independent of any experiment result: it reads the registry,
    which is the only place a promotion can be recorded, so a spectacular
    leaderboard cannot make this say anything other than NO_MODEL until a model
    is actually promoted.
    """
    from src.quant.models.registry import ModelRegistry

    try:
        registry = ModelRegistry("data/research/models")
    except Exception as error:  # noqa: BLE001
        return {"deployment_status": "NO_MODEL", "detail": f"registry unreadable: {error}",
                "production": 0, "candidates": 0}

    production = registry.by_status("production")
    candidates = registry.by_status("production_candidate")
    validated = registry.by_status("validated")

    if production:
        status = "PRODUCTION"
        message = f"{len(production)} model(s) approved for production."
    elif candidates:
        status = "CANDIDATE"
        message = (
            f"{len(candidates)} candidate(s) clear the development gates. "
            "No model is approved for production."
        )
    elif validated:
        status = "EXPERIMENTAL"
        message = (
            f"{len(validated)} model(s) are validated but none clears the candidate "
            "thresholds. No production-grade predictive model is currently validated."
        )
    else:
        status = "NO_MODEL"
        message = "No production-grade predictive model currently validated."

    return {
        "deployment_status": status,
        "message": message,
        "production": len(production),
        "candidates": len(candidates),
        "validated": len(validated),
        "total_entries": len(registry.all()),
        "retired": len(registry.by_status("retired")),
        "serving_predictions": bool(production),
        "note": (
            "Only a model with status=production may be served as a production "
            "prediction. Anything else is a research signal and is labelled as one."
        ),
    }


def registry_view() -> dict[str, Any]:
    """The registry as counts and rejection reasons, for the UI.

    Deliberately does not expose the full evidence bundle: that is megabytes of
    fold detail per entry and the page needs the decision, not the derivation.
    What it does expose is *why* each entry is where it is, because a registry
    that shows a status without a reason is asking to be trusted rather than
    checked.
    """
    from src.quant.models.registry import ModelRegistry

    try:
        registry = ModelRegistry("data/research/models")
    except Exception as error:  # noqa: BLE001
        return {"status": "unavailable", "detail": str(error)}

    rows: list[dict[str, Any]] = []
    for entry in registry.all():
        payload = entry.as_dict()
        rows.append({
            "key": entry.key,
            "model_id": entry.model_id,
            "version": entry.version,
            "label": entry.label,
            "status": entry.status,
            "experiments_run": entry.experiments_run,
            "dataset_version": entry.dataset_version,
            "eligible_for": payload.get("eligible_for", []),
            "candidate_thresholds_not_met": payload.get("candidate_thresholds_not_met", {}),
            "notes": entry.notes,
            "retired_reason": next(
                (h.get("reason") for h in reversed(entry.status_history)
                 if h.get("to") == "retired"),
                None,
            ),
        })

    summary = registry.summary()
    return {
        "status": "ok",
        "entries": summary["entries"],
        "by_status": summary["by_status"],
        "models": rows,
        "promotion_note": (
            "Promotion is evaluated by ModelRegistry.promote(), which refuses a "
            "transition whose evidence is absent AND one whose numbers fail. The "
            "frontend renders this decision; it never makes it."
        ),
    }


def firewall_status() -> dict[str, Any]:
    """Whether the holdout is locked. Rendered prominently, deliberately."""
    from src.quant.study.firewall import FIREWALL

    status = FIREWALL.status()
    status["headline"] = (
        "HOLDOUT LOCKED — contract not armed" if not status["contract_armed"]
        else "HOLDOUT ARMED — the contract names a pre-registered candidate"
    )
    return status


def symbol_view(symbol: str, root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """The company-page quant panel.

    Returns NO_VALIDATED_MODEL unless a production model exists. It never
    fabricates a prediction, and it never renders a research signal in a shape
    that could be mistaken for one.
    """
    production = production_status(root)
    payload = {
        "symbol": symbol.upper(),
        "deployment_status": production["deployment_status"],
        "message": production["message"],
        "prediction": None,
        "model": None,
    }
    if production["deployment_status"] != "PRODUCTION":
        payload["disclosure"] = (
            "No production-approved model exists, so no prediction is produced for "
            "this symbol. Research findings are available on /quant, where they are "
            "labelled as research."
        )
        return payload

    # Unreachable today by design; the shape is here so promotion is a registry
    # change rather than a rewrite of the product surface.
    payload["disclosure"] = "Served from a production-approved model artifact."
    return payload
