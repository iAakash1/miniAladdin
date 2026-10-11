"""EXP-013 - which columns carry the EXP-012 T1 gain? An attribution check.

Exploratory, validation folds only, holdout sealed, nothing promoted. Parent: EXP-012.

EXP-012 found that adding six point-in-time columns to the rich set raised ridge Rank IC (T1), and that the shifted placebo kept about half of the gain. The six columns are not equal: four are
cross-sectional ranks of filing-process variables (amendments in two years, latest report amended, regularity, lateness against the firm's own record), one is the count of missing fundamentals, and one is a
composite that contains two variables already in the rich set. This study asks which of them the gain depends on, with the information set otherwise fixed, and nothing else.

Everything that can be held fixed is held fixed: the panel, the label, the eight folds, ridge alpha 10, the frozen portfolio at 10 bp, and the EXP-012 code for placebos and paired inference. Arms are ridge fits
(deterministic). There is no confirmatory claim: three group contrasts are reported with a Holm adjustment as a descriptive family, every other contrast is descriptive, and the labels are attribution rules fixed
before any result. The folds have been looked at by EXP-006 to EXP-012; this is another look and is counted as one.
"""

from __future__ import annotations

import concurrent.futures as futures
import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.study import exp009a, exp009b, exp010a, exp010b, exp011, exp012, prereg
from src.quant.validation.runner import run_walk_forward

EXPERIMENT_ID = "EXP-013"
PARENT_EXPERIMENT = "EXP-012"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_013_PREREGISTRATION.md")
REGISTRATION_REF = exp012.REGISTRATION_REF
PARENT_METRICS = Path("experiments") / PARENT_EXPERIMENT / "per_arm_metrics.csv"
REPRODUCTION = {"B1": "A1", "B5": "A5"}           # arm here -> arm in EXP-012 that it must reproduce
REPRODUCTION_TOLERANCE = 1e-9
LAST_PANEL_DATE = exp012.LAST_PANEL_DATE
LABEL = exp012.LABEL
PERMUTATION_SEEDS = exp012.PERMUTATION_SEEDS
GRID_STEP = exp012.GRID_STEP

#: the six columns of the EXP-012 block, by short name
COLUMNS = {"amended": "rel_amended_730_xs", "latest": "rel_latest_amended_xs", "count": "rel_periodic_count_xs",
           "lagdet": "rel_lag_deterioration_xs", "missing": "rel_missing_xs", "u": "rel_u_xs"}
PROCESS = ("amended", "latest", "count", "lagdet")  # the four ranks of filing-process variables
#: the three groups the attribution rule speaks about
GROUPS = {"P": PROCESS, "M": ("missing",), "U": ("u",)}
GROUP_NAMES = {"P": "the four filing-process ranks", "M": "the missing-fundamentals count", "U": "the composite unreliability rank"}

A1_FEATURES = list(exp012.ARMS["A1"]["features"])
A5_FEATURES = list(exp012.ARMS["A5"]["features"])


def _cols(names) -> list[str]:
    return [COLUMNS[n] for n in names]


def _build_arms() -> dict[str, dict[str, Any]]:
    arms: dict[str, dict[str, Any]] = {
        "B1": {"features": A1_FEATURES, "note": "EXP-012 A1 (rich set), reproduction"},
        "B5": {"features": A5_FEATURES, "note": "EXP-012 A5 (rich set plus all six columns), reproduction"},
    }
    for name in COLUMNS:
        arms[f"C_{name}"] = {"features": [*A1_FEATURES, *_cols([name])], "note": f"rich set plus {COLUMNS[name]} only"}
        arms[f"D_{name}"] = {"features": [f for f in A5_FEATURES if f != COLUMNS[name]], "note": f"rich set plus all six columns except {COLUMNS[name]}"}
    arms["C_P"] = {"features": [*A1_FEATURES, *_cols(PROCESS)], "note": "rich set plus the four filing-process ranks"}
    arms["D_P"] = {"features": [f for f in A5_FEATURES if f not in _cols(PROCESS)], "note": "all six columns except the four filing-process ranks"}
    for g in GROUPS:
        base = ("C_P" if g == "P" else "C_missing" if g == "M" else "C_u")
        arms[f"X{g}perm"] = {"features": arms[base]["features"], "placebo": "permute", "columns": _cols(GROUPS[g]), "seeds": PERMUTATION_SEEDS,
                             "note": f"{base} with {GROUP_NAMES[g]} permuted across firms within each date"}
        arms[f"X{g}shift"] = {"features": arms[base]["features"], "placebo": "shift", "columns": _cols(GROUPS[g]),
                              "note": f"{base} with {GROUP_NAMES[g]} shifted {exp012.SHIFT_SESSIONS} sessions within each firm"}
    return arms


ARMS: dict[str, dict[str, Any]] = _build_arms()
#: descriptive family adjusted together (Holm): what each group adds to the rich set
FAMILY = {"G_P": ("C_P", "B1"), "G_M": ("C_missing", "B1"), "G_U": ("C_u", "B1")}
#: group -> (add arm, drop arm, permuted placebo, shifted placebo)
GROUP_ARMS = {"P": ("C_P", "D_P", "XPperm", "XPshift"), "M": ("C_missing", "D_missing", "XMperm", "XMshift"), "U": ("C_u", "D_u", "XUperm", "XUshift")}

ATTRIBUTION_RULE = {
    "gain": "the EXP-012 T1 gain, IC(B5) - IC(B1); if it is not positive nothing is attributed and every group is labelled NO_GAIN",
    "add_share": "(IC(add arm) - IC(B1)) / gain",
    "drop_share": "(IC(B5) - IC(drop arm)) / gain",
    "resolvable": "the add contrast (add arm - B1) is positive with one-sided Newey-West p < 0.10; without it nothing is claimed for the group, because a share of a small, noisy gain is not interpretable",
    "CARRIES": "resolvable, add_share >= 0.5, drop_share >= 0.5, both placebos beaten (positive mean difference), the permuted-placebo difference has one-sided p < 0.10, and the add arm beats B1 in at least 6 of 8 folds",
    "SHARES": "resolvable and not CARRIES, with add_share >= 0.25 or drop_share >= 0.25",
    "NOT_CARRYING": "otherwise (including groups whose contribution is too small to resolve; low power is a possible reason and is not distinguished from absence)",
    "note": "descriptive labels; the groups overlap through collinearity, so shares need not sum to one; no confirmatory claim is made",
}


def _definition() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID, "parent_experiment": PARENT_EXPERIMENT,
        "status": "EXPLORATORY - VALIDATION FOLDS ONLY - HOLDOUT SEALED - PROMOTION NOT ASSESSED",
        "question": "Which of the six columns added in EXP-012 does the T1 gain depend on?",
        "fixed": {"panel": exp011.RICH_DATASET_ID, "panel_content_hash": exp011.RICH_CONTENT_HASH, "label": LABEL, "folds": "the eight recorded EXP-006 folds, unchanged",
                  "ridge": exp012.RIDGE_PARAMS, "portfolio": "the frozen EXP-010B 21-session implementation (B1) at the 10 bp half-spread, unchanged",
                  "reliability_table": exp012.rel.VERSION, "code": "EXP-012 placebo and paired-inference code, unchanged"},
        "columns": COLUMNS, "groups": {g: list(_cols(cols)) for g, cols in GROUPS.items()},
        "arms": {k: {"features": v["features"], "placebo": v.get("placebo"), "columns": v.get("columns"), "seeds": list(v.get("seeds", (0,))), "note": v["note"]} for k, v in ARMS.items()},
        "descriptive_family": {k: list(v) for k, v in FAMILY.items()}, "attribution_rule": ATTRIBUTION_RULE,
        "inference": {"statistic": "mean over dates of the per-date Spearman Rank IC; paired differences on identical dates", "hac": "Newey-West with 4 lags, as in EXP-012",
                      "bootstrap": {"type": "moving block over dates", "block": exp012.BOOTSTRAP_BLOCK, "draws": exp012.BOOTSTRAP_DRAWS, "seed": exp012.BOOTSTRAP_SEED},
                      "adjustment": "Holm across G_P, G_M and G_U only; every other contrast descriptive and unadjusted"},
        "trial_ledger": {"cumulative_before": 1029, "note": "EXP-009 to EXP-012 added looks at the same folds; this study adds 3 adjusted contrasts, 22 descriptive contrasts and 34 ridge fits (16 arms and 18 placebo fits)"},
        "acceptance_gates": {"reproduction": {"arms": REPRODUCTION, "statistic": "mean Rank IC", "tolerance": REPRODUCTION_TOLERANCE, "source": str(PARENT_METRICS), "on_failure": "abort before any contrast is computed"},
                             "panel_end": str(LAST_PANEL_DATE.date()), "predictions": "every out-of-sample prediction finite", "reliability_table": "sha256 equals its manifest"},
        "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
        "outputs": ["definition.json", "config.json", "per_arm_metrics.csv", "fold_metrics.csv", "paired_tests.csv", "attribution.json", "manifest.json", "checkpoints/*"],
    }


DEFINITION: dict[str, Any] = _definition()
METHOD_SOURCES = (*exp012.METHOD_SOURCES, "src/quant/study/exp013.py")


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    """Refuse unless the EXP-013 preregistration is committed, embeds this fingerprint and is an ancestor of the pushed research branch."""
    root = Path(root)
    doc = root / PREREG_DOC
    expected = definition_fingerprint(root)
    if not doc.exists():
        raise prereg.PreregistrationError(f"{PREREG_DOC} does not exist")
    if f"Definition fingerprint: `{expected}`" not in doc.read_text(encoding="utf-8"):
        raise prereg.PreregistrationError("the preregistration does not embed this definition's fingerprint; nothing is run")
    tracked = [str(PREREG_DOC), *METHOD_SOURCES]
    if exp012._git(root, "status", "--porcelain", "--", *tracked).stdout.strip():
        raise prereg.PreregistrationError("registered files have uncommitted changes")
    commit = exp012._git(root, "log", "-1", "--format=%H", "--", *tracked).stdout.strip()
    if fetch:
        exp012._git(root, "fetch", "origin", "research/market-signal-review-2026-10-11", "--quiet")
    if exp012._git(root, "merge-base", "--is-ancestor", commit, REGISTRATION_REF).returncode != 0:
        raise prereg.PreregistrationError(f"registration commit {commit[:12]} is not on {REGISTRATION_REF}: push it before running")
    return {"preregistration_document": str(PREREG_DOC), "preregistration_sha256": prereg.sha256_file(doc), "registration_commit": commit, "pushed_to": REGISTRATION_REF,
            "definition_fingerprint": expected}


# ── fitting ─────────────────────────────────────────────────────────────────

def arm_frame(frame: pd.DataFrame, arm: str, seed: int) -> pd.DataFrame:
    """The frame with the arm's placebo columns replaced (permuted within date, or shifted within firm); the frame itself otherwise."""
    spec = ARMS[arm]
    kind = spec.get("placebo")
    if not kind:
        return frame
    columns = list(spec["columns"])
    replaced = exp012.permute_within_date(frame, columns, seed) if kind == "permute" else exp012.shift_within_security(frame, columns)
    out = frame.copy()
    out[columns] = replaced[columns]
    return out


def tasks() -> list[tuple[str, int]]:
    return [(arm, seed) for arm, spec in ARMS.items() for seed in spec.get("seeds", (0,))]


def fit_arm_seed(arm: str, seed: int, frame: pd.DataFrame, plan: Any):
    spec = ModelSpec(f"ridge_{arm}_seed_{seed}", "ridge", tuple(exp012.RIDGE_PARAMS.items()), 0)
    return run_walk_forward(spec.build, arm_frame(frame, arm, seed), plan, features=list(ARMS[arm]["features"]), label=LABEL, step_sessions=GRID_STEP)


_WORKER: dict[str, Any] = {}


def _init_worker(root: str, rehearsal: bool = False) -> None:
    _WORKER["frame"] = exp012.load_frame(Path(root), rehearsal)
    _WORKER["plan"] = exp009b.recorded_plan(Path(root))


def _task(task: tuple[str, int]):
    arm, seed = task
    result = fit_arm_seed(arm, seed, _WORKER["frame"], _WORKER["plan"])
    if result.errors or result.predictions is None or len(result.folds) != 8:
        return arm, seed, pd.DataFrame(), 0.0, list(result.errors) or ["incomplete folds"]
    return arm, seed, result.predictions, float(result.seconds), []


def checkpoint_path(output: Path, arm: str, seed: int) -> Path:
    return Path(output) / "checkpoints" / f"{arm}_{seed}.parquet"


def load_checkpoint(output: Path, arm: str, seed: int, fingerprint: str) -> Optional[pd.DataFrame]:
    path = checkpoint_path(output, arm, seed)
    receipt = path.with_suffix(".json")
    if not path.exists() or not receipt.exists():
        return None
    meta = json.loads(receipt.read_text())
    frame = pd.read_parquet(path)
    if meta.get("definition_fingerprint") != fingerprint or meta.get("prediction_sha256") != exp010a._prediction_hash(frame):
        return None
    return frame


# ── gates and attribution ───────────────────────────────────────────────────

def acceptance_checks(root: Path, frame: pd.DataFrame, predictions: dict, reports: dict, *, rehearsal: bool = False) -> dict[str, Any]:
    """Raises before any contrast is computed. A rehearsal uses a shuffled label, so reproduction is skipped there."""
    last = pd.Timestamp(frame["date"].max())
    if last > LAST_PANEL_DATE:
        raise RuntimeError(f"the panel runs to {last.date()}, after the registered end {LAST_PANEL_DATE.date()}")
    bad = sorted(f"{arm}:{seed}" for (arm, seed), pred in predictions.items() if not np.isfinite(pred["prediction"].to_numpy(dtype=float)).all())
    if bad:
        raise RuntimeError(f"non-finite predictions in {bad}")
    checks: dict[str, Any] = {"panel_end": str(last.date()), "predictions_finite": True}
    if rehearsal:
        checks["reproduction"] = "skipped: shuffled label"
        return checks
    parent = pd.read_csv(Path(root) / PARENT_METRICS)
    differences = {}
    for arm, parent_arm in REPRODUCTION.items():
        recorded = parent[(parent["arm"] == parent_arm) & (parent["seed"] == 0)]["mean_rank_ic"]
        if len(recorded) != 1:
            raise RuntimeError(f"{PARENT_METRICS} holds {len(recorded)} rows for {parent_arm} seed 0")
        differences[arm] = abs(float(reports[(arm, 0)]["mean_rank_ic"]) - float(recorded.iloc[0]))
    if max(differences.values()) > REPRODUCTION_TOLERANCE:
        raise RuntimeError(f"{EXPERIMENT_ID} arms do not reproduce {PARENT_EXPERIMENT}: absolute differences {differences}, tolerance {REPRODUCTION_TOLERANCE}")
    checks["reproduction_abs_difference"] = differences
    return checks


def attribute(group: str, ic: dict[str, float], contrasts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the preregistered attribution rule to one group. `ic` maps arm to mean Rank IC; `contrasts` holds the paired tests by name."""
    add, drop, perm, shift = GROUP_ARMS[group]
    gain = ic["B5"] - ic["B1"]
    perm_c, shift_c, add_c = contrasts[f"{group}_vs_perm"], contrasts[f"{group}_vs_shift"], contrasts[f"G_{group}"]
    if not gain > 0:
        return {"group": group, "what": GROUP_NAMES[group], "gain": gain, "add_share": float("nan"), "drop_share": float("nan"), "resolvable": False, "placebos_beaten": False,
                "permuted_placebo_p": perm_c["p_one_sided"], "add_positive_folds": add_c["positive_folds"], "label": "NO_GAIN"}
    add_share = (ic[add] - ic["B1"]) / gain
    drop_share = (ic["B5"] - ic[drop]) / gain
    resolvable = bool(add_c["mean_diff"] > 0 and add_c["p_one_sided"] is not None and add_c["p_one_sided"] < 0.10)
    placebos_beaten = bool(perm_c["mean_diff"] > 0 and shift_c["mean_diff"] > 0)
    perm_clear = perm_c["p_one_sided"] is not None and perm_c["p_one_sided"] < 0.10
    carries = resolvable and add_share >= 0.5 and drop_share >= 0.5 and placebos_beaten and perm_clear and add_c["positive_folds"] >= 6
    shares = resolvable and (add_share >= 0.25 or drop_share >= 0.25)
    label = "CARRIES" if carries else "SHARES" if shares else "NOT_CARRYING"
    return {"group": group, "what": GROUP_NAMES[group], "gain": gain, "add_share": add_share, "drop_share": drop_share, "resolvable": resolvable, "placebos_beaten": placebos_beaten,
            "permuted_placebo_p": perm_c["p_one_sided"], "add_positive_folds": add_c["positive_folds"], "label": label}


def run_study(root: Path = Path("."), *, output: Optional[Path] = None, workers: int = 6, rehearsal: bool = False) -> dict[str, Any]:
    """The registered attribution study. `rehearsal=True` runs every path on a label shuffled within each date and writes outside the experiment directory."""
    began = time.perf_counter()
    root = Path(root)
    output = Path(output) if output else root / OUTPUT_DIR
    if rehearsal:
        if (root / OUTPUT_DIR).resolve() in (output.resolve(), *output.resolve().parents):
            raise RuntimeError("a rehearsal must not write into the experiment directory")
        gate = {"rehearsal": True, "note": "label shuffled within date; no result about the hypotheses"}
    else:
        gate = prereg_gate(root)
    git_state = exp009a._git_state(root)
    guard = exp010b.holdout_guard(root)
    parent = exp010b.verify_parent_artifacts(root)
    if not parent["passed"]:
        raise RuntimeError(f"parent artifacts differ from those registered: {parent['checks']}")
    fingerprint = definition_fingerprint(root) + ("-rehearsal" if rehearsal else "")
    frame = exp012.load_frame(root, rehearsal)
    plan = exp009b.recorded_plan(root)
    (output / "checkpoints").mkdir(parents=True, exist_ok=True)
    pending = [t for t in tasks() if load_checkpoint(output, *t, fingerprint) is None]
    if pending:
        with futures.ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(str(root), rehearsal)) as pool:
            for arm, seed, predictions, seconds, errors in pool.map(_task, pending):
                if errors:
                    raise RuntimeError(f"{arm} seed {seed} failed: {errors}")
                path = checkpoint_path(output, arm, seed)
                predictions.to_parquet(path, index=False)
                path.with_suffix(".json").write_text(json.dumps({
                    "experiment_id": EXPERIMENT_ID, "arm": arm, "seed": seed, "definition_fingerprint": fingerprint, "prediction_sha256": exp010a._prediction_hash(predictions),
                    "rows": int(len(predictions)), "fit_seconds": seconds, "git_commit": git_state["git_commit"], "python": platform.python_version(),
                    "dependency_versions": dependency_versions()}, indent=1))
                print(f"fitted {arm} seed {seed}: {len(predictions):,} rows in {seconds:.1f}s", flush=True)
    predictions = {(a, s): load_checkpoint(output, a, s, fingerprint) for a, s in tasks()}
    daily, calendar = exp010b.build_daily_panel(root)
    universe = daily[daily["in_universe"]]
    schedule = exp010b.rebalance_schedule(calendar, exp010b.ARMS[exp011.ECONOMICS_ARM]["step_sessions"])
    reports = {key: exp011.arm_seed_report(key[0], key[1], pred, frame, universe, calendar, schedule) for key, pred in predictions.items()}
    acceptance = acceptance_checks(root, frame, predictions, reports, rehearsal=rehearsal)
    series = {key: exp012.ic_series(pred) for key, pred in predictions.items()}

    def arm_series(arm: str) -> pd.Series:
        return exp012.mean_series([series[(arm, s)] for s in ARMS[arm].get("seeds", (0,))])

    def arm_folds(arm: str) -> list[float]:
        return [float(v) for v in np.mean([reports[(arm, s)]["fold_ic"] for s in ARMS[arm].get("seeds", (0,))], axis=0)]

    def arm_ic(arm: str) -> float:
        return float(np.mean([reports[(arm, s)]["mean_rank_ic"] for s in ARMS[arm].get("seeds", (0,))]))

    def pair(left: str, right: str) -> dict[str, Any]:
        return exp012.paired(arm_series(left), arm_series(right), arm_folds(left), arm_folds(right))

    contrasts: dict[str, dict[str, Any]] = {}
    for name, (l, r) in FAMILY.items():
        contrasts[name] = {"left": l, "right": r, **pair(l, r)}
    adjusted = exp012.holm({k: contrasts[k]["p_one_sided"] for k in FAMILY})
    for g, (add, drop, perm, shift) in GROUP_ARMS.items():
        contrasts[f"{g}_vs_perm"] = {"left": add, "right": perm, **pair(add, perm)}
        contrasts[f"{g}_vs_shift"] = {"left": add, "right": shift, **pair(add, shift)}
        contrasts[f"{g}_drop"] = {"left": "B5", "right": drop, **pair("B5", drop)}
    for name in COLUMNS:
        contrasts[f"add_{name}"] = {"left": f"C_{name}", "right": "B1", **pair(f"C_{name}", "B1")}
        contrasts[f"drop_{name}"] = {"left": "B5", "right": f"D_{name}", **pair("B5", f"D_{name}")}
    contrasts["total"] = {"left": "B5", "right": "B1", **pair("B5", "B1")}
    ic = {arm: arm_ic(arm) for arm in ARMS}
    attribution = {g: attribute(g, ic, contrasts) for g in GROUPS}
    output.mkdir(parents=True, exist_ok=True)
    exp010a._atomic_json(output / "definition.json", DEFINITION)
    exp010a._atomic_json(output / "config.json", {"arms": {k: {"features": v["features"], "placebo": v.get("placebo"), "columns": v.get("columns")} for k, v in ARMS.items()},
                                                  "folds": [fo.as_dict() for fo in plan.folds], "costs": list(exp010b.COSTS)})
    pd.DataFrame([{k: v for k, v in r.items() if k not in ("costs", "fold_ic")} for r in reports.values()]).to_csv(output / "per_arm_metrics.csv", index=False)
    pd.DataFrame([{"arm": r["arm"], "seed": r["seed"], "fold": i, "mean_rank_ic": v} for r in reports.values() for i, v in enumerate(r["fold_ic"])]).to_csv(output / "fold_metrics.csv", index=False)
    pd.DataFrame([{"contrast": k, **{kk: vv for kk, vv in v.items() if kk != "fold_diffs"}, "holm_adjusted_p": adjusted.get(k), "fold_diffs": json.dumps(v["fold_diffs"])}
                  for k, v in contrasts.items()]).to_csv(output / "paired_tests.csv", index=False)
    exp010a._atomic_json(output / "attribution.json", {"rule": ATTRIBUTION_RULE, "mean_rank_ic": ic, "groups": attribution})
    manifest = {"experiment_id": EXPERIMENT_ID, "status": DEFINITION["status"], **gate, **git_state, "holdout": guard, "parent_artifacts_verified": parent["passed"], "acceptance": acceptance,
                "reliability_manifest": json.loads((root / exp012.rel.MANIFEST).read_text()), "dependency_versions": dependency_versions(),
                "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(), "workers": workers, "platform": platform.platform(), "python": platform.python_version()},
                "attribution": {g: a["label"] for g, a in attribution.items()}, "completion": "REHEARSAL" if rehearsal else "COMPLETE", "promotion": "NOT ASSESSED"}
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*")) if p.is_file() and p.name != "manifest.json"}
    exp010a._atomic_json(output / "manifest.json", manifest)
    print(f"{EXPERIMENT_ID} {'REHEARSAL' if rehearsal else 'COMPLETE'}: {manifest['attribution']}", flush=True)
    return {"manifest": manifest, "contrasts": contrasts, "attribution": attribution}
