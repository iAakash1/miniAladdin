"""EXP-012 - disclosure-process reliability and the value of company information.

Exploratory, validation folds only, holdout sealed, nothing promoted. Parent: EXP-011.

The question. Does the reliability of the filings a fundamentals-based signal is computed from - how stale they are, how
late they were filed, whether they have been amended, whether the firm files regularly and on its usual schedule - carry
incremental information about cross-sectional returns, either directly or as a moderator of the fundamentals signals?

Everything that can be held fixed is held fixed: the rich point-in-time panel `ds-richpit-ff3d3f556488b7da`, the label
`fwd_rank_21`, the eight recorded folds, Ridge alpha 10 (the pre-existing configuration, no search), the frozen
EXP-010B 21-session portfolio at 10 bp. The only thing that changes between arms is the information set.

Three confirmatory contrasts are predeclared (Holm-adjusted together): T1 the new reliability block adds to the rich
set; T2 letting reliability moderate the fundamentals adds to the main effects; T3 the two reliability variables already
inside the rich set (`filing_lag_days`, `days_since_report`) contribute within it. Every contrast has a placebo: the same
block permuted across firms within each date, and the same block shifted 252 sessions within each firm. A real effect
must beat both. A nonlinear learner (gradient boosting, three seeds, frozen EXP-010A settings) is a secondary check that
needs no hand-built interactions.

These eight folds have been looked at by EXP-006/007/009/010/011. That is disclosed, counted in the trial ledger, and the
result is labelled exploratory whatever it says.
"""

from __future__ import annotations

import concurrent.futures as futures
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Optional, Sequence

import joblib
import numpy as np
import pandas as pd

from src.quant.features import cross_section as xs
from src.quant.models.base import FoldImputer
from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.study.firewall import FIREWALL
from src.quant.pit import reliability as rel
from src.quant.study import exp009a, exp009b, exp010a, exp010b, exp011, prereg
from src.quant.validation.metrics import ic_summary, per_date_ic
from src.quant.validation.runner import run_walk_forward

EXPERIMENT_ID = "EXP-012"
PARENT_EXPERIMENT = "EXP-011"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_012_PREREGISTRATION.md")
REGISTRATION_REF = "origin/research/market-signal-review-2026-10-11"
LABEL = exp011.LABEL
RIDGE_PARAMS = dict(exp011.RIDGE_PARAMS)
GBR_PARAMS = dict(exp011.GBR_PARAMS)
GB_SEEDS = (0, 1, 2)
PERMUTATION_SEEDS = (0, 1, 2, 3, 4)
SHIFT_SESSIONS = 252
GRID_STEP = 5                                   # panel rows are every 5 sessions
SHIFT_ROWS = SHIFT_SESSIONS // GRID_STEP        # 50 grid rows
BOOTSTRAP_BLOCK = 6                             # dates; > the 4 overlapping label windows
BOOTSTRAP_DRAWS = 4000
BOOTSTRAP_SEED = 20261012
PARENT_METRICS = Path("experiments") / PARENT_EXPERIMENT / "per_arm_metrics.csv"
REPRODUCTION = {"A0": "E0", "A1": "E1"}         # arm here -> arm in the parent that it must reproduce
REPRODUCTION_TOLERANCE = 1e-9
LAST_PANEL_DATE = pd.Timestamp("2025-05-09")    # last decision date of the panel; the sealed holdout starts 2025-08-26

BASELINE = list(exp011.feature_list("baseline"))
RICH = list(exp011.feature_list("rich"))
EXISTING_RELIABILITY = ["filing_lag_days_xs", "days_since_report_xs"]
FUNDAMENTALS = [f for f in exp011.RICH_FEATURES if f not in EXISTING_RELIABILITY]
RAW_NEW = list(rel.VARIABLES)
NEW_BLOCK = ["rel_amended_730_xs", "rel_latest_amended_xs", "rel_periodic_count_xs", "rel_lag_deterioration_xs", "rel_missing_xs", "rel_u_xs"]
INTERACTIONS = [f"int_{f}" for f in FUNDAMENTALS]
#: oriented so that a higher component means less reliable evidence
U_COMPONENTS = (("days_since_report_xs", +1), ("filing_lag_days_xs", +1), ("rel_amended_730_xs", +1),
                ("rel_lag_deterioration_xs", +1), ("rel_periodic_count_xs", -1))
U_MIN_COMPONENTS = 3

ARMS: dict[str, dict[str, Any]] = {
    "A0": {"model": "ridge", "features": BASELINE, "note": "EXP-011 E0 reproduction"},
    "A1": {"model": "ridge", "features": [*BASELINE, *FUNDAMENTALS, *EXISTING_RELIABILITY], "note": "EXP-011 E1 reproduction (rich)"},
    "A2": {"model": "ridge", "features": [*BASELINE, *FUNDAMENTALS], "note": "rich minus its two reliability variables"},
    "A3": {"model": "ridge", "features": [*BASELINE, *EXISTING_RELIABILITY], "note": "baseline plus the two existing reliability variables only"},
    "A4": {"model": "ridge", "features": [*BASELINE, *NEW_BLOCK], "note": "baseline plus the new reliability block only"},
    "A5": {"model": "ridge", "features": [*BASELINE, *FUNDAMENTALS, *EXISTING_RELIABILITY, *NEW_BLOCK], "note": "rich plus the new block (main effects)"},
    "A6": {"model": "ridge", "features": [*BASELINE, *FUNDAMENTALS, *EXISTING_RELIABILITY, *NEW_BLOCK, *INTERACTIONS],
           "note": "A5 plus fundamentals x unreliability interactions"},
    "P0": {"model": "ridge", "features": "A5", "placebo": "permute", "columns": "new", "seeds": PERMUTATION_SEEDS,
           "note": "A5 with the new block permuted across firms within each date"},
    "P0s": {"model": "ridge", "features": "A5", "placebo": "shift", "columns": "new",
            "note": "A5 with the new block shifted 252 sessions within each firm"},
    "P1": {"model": "ridge", "features": "A6", "placebo": "permute", "columns": "new", "seeds": PERMUTATION_SEEDS,
           "note": "A6 with the new block (and so the interactions) permuted across firms within each date"},
    "P2": {"model": "ridge", "features": "A6", "placebo": "shift", "columns": "new",
           "note": "A6 with the new block (and so the interactions) shifted 252 sessions within each firm"},
    "P3": {"model": "ridge", "features": "A1", "placebo": "permute", "columns": "existing", "seeds": PERMUTATION_SEEDS,
           "note": "A1 with filing_lag_days and days_since_report permuted across firms within each date"},
    "G1": {"model": "gradient_boosting", "features": [*BASELINE, *FUNDAMENTALS, *EXISTING_RELIABILITY], "seeds": GB_SEEDS,
           "note": "secondary: boosted rich arm (EXP-011 E3 settings)"},
    "G2": {"model": "gradient_boosting", "features": [*BASELINE, *FUNDAMENTALS, *EXISTING_RELIABILITY, *NEW_BLOCK], "seeds": GB_SEEDS,
           "note": "secondary: boosted rich arm plus the new block"},
}

CONFIRMATORY = {
    "T1": ("A5", "A1", "the new reliability block adds to the rich information set"),
    "T2": ("A6", "A5", "reliability moderation of the fundamentals adds to the main effects"),
    "T3": ("A1", "A2", "the two existing reliability variables contribute within the rich set"),
}
CONTROLS = {"C1": ("A5", "P0", "A5 beats the permuted-block placebo (mean of five permutations)"),
            "C2": ("A5", "P0s", "A5 beats the time-shifted placebo"),
            "C3": ("A6", "P1", "A6 beats the permuted-block placebo (mean of five permutations)"),
            "C4": ("A6", "P2", "A6 beats the time-shifted placebo"),
            "C5": ("A1", "P3", "A1 beats the placebo for its two existing reliability variables (mean of five permutations)")}
#: which controls bound which confirmatory contrast
PLACEBO_OF = {"T1": ("C1", "C2"), "T2": ("C3", "C4"), "T3": ("C5",)}
SECONDARY = {"S1": ("A4", "A0", "the new block alone adds to the baseline"), "S2": ("A3", "A0", "the two existing variables alone add to the baseline"),
             "S3": ("G2", "G1", "a boosted learner gains from the new block (mean over three seeds)")}

SUPPORT_RULE = {
    "alpha": 0.05, "adjustment": "Holm across T1-T3 on one-sided Newey-West p-values of the paired mean Rank IC difference",
    "positive_folds_required": 6, "placebo": "every control mapped to the contrast (PLACEBO_OF) must have a positive mean difference: the real information set beats the placebo",
    "labels": {"SUPPORTED": "mean difference > 0, Holm p < 0.05, >= 6 of 8 folds positive, placebo does not match it",
               "NOT_SUPPORTED": "mean difference <= 0, or Holm p >= 0.05",
               "FRAGILE": "Holm p < 0.05 but fewer than 6 folds positive, or a placebo reproduces it"},
}


def _definition() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID, "parent_experiment": PARENT_EXPERIMENT,
        "status": "EXPLORATORY - VALIDATION FOLDS ONLY - HOLDOUT SEALED - PROMOTION NOT ASSESSED",
        "question": ("Does the reliability of the filings behind a fundamentals-based signal carry incremental information about "
                     "cross-sectional returns, directly or as a moderator, after the information set is otherwise held fixed?"),
        "fixed": {"panel": exp011.RICH_DATASET_ID, "panel_content_hash": exp011.RICH_CONTENT_HASH, "label": LABEL,
                  "folds": "the eight recorded EXP-006 folds, unchanged", "ridge": RIDGE_PARAMS, "gradient_boosting": GBR_PARAMS,
                  "portfolio": "the frozen EXP-010B 21-session implementation (B1) at the 10 bp half-spread, unchanged"},
        "reliability_variables": {"source": "data/curated/sec_v3/filings.parquet (SEC Financial Statement Data Sets registry)", "version": rel.VERSION,
                                  "variables": list(rel.VARIABLES), "availability": "first session whose close-based decision may use the filing",
                                  "never_used": "prevrpt (describes the future of a filing)", "missing": "NaN, never zero"},
        "composite_u": {"components": [[c, s] for c, s in U_COMPONENTS], "minimum_components": U_MIN_COMPONENTS,
                        "construction": "mean of the oriented cross-sectional ranks, then ranked again within the date"},
        "arms": {k: {"model": v["model"], "features": v["features"], "placebo": v.get("placebo"), "columns": v.get("columns"), "seeds": list(v.get("seeds", (0,))), "note": v["note"]}
                 for k, v in ARMS.items()},
        "interactions": "int_<f> = f_xs * rel_u_xs for the 48 fundamentals features",
        "confirmatory": {k: list(v) for k, v in CONFIRMATORY.items()}, "controls": {k: list(v) for k, v in CONTROLS.items()},
        "secondary": {k: list(v) for k, v in SECONDARY.items()}, "support_rule": SUPPORT_RULE,
        "inference": {"statistic": "mean over dates of the per-date Spearman rank IC; paired differences on identical dates",
                      "hac": "Newey-West with 4 lags (ceil(21/5) - 1), as in ic_summary",
                      "bootstrap": {"type": "moving block over dates", "block": BOOTSTRAP_BLOCK, "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED},
                      "placebos": {"permute_seeds": list(PERMUTATION_SEEDS), "shift_sessions": SHIFT_SESSIONS}},
        "trial_ledger": {"cumulative_before": 1029, "source": "EXP-007 final_selection.json multiple_testing.cumulative_trials",
                         "note": "EXP-009 to EXP-011 added looks at the same folds; this study adds 3 confirmatory tests, 5 controls, 3 secondary contrasts "
                                 "and 30 model fits (24 ridge, of which 17 are placebo fits, and 6 boosted)"},
        "acceptance_gates": {
            "reproduction": {"arms": REPRODUCTION, "statistic": "mean Rank IC", "tolerance": REPRODUCTION_TOLERANCE, "source": str(PARENT_METRICS),
                             "on_failure": "abort before any contrast is computed"},
            "panel_end": str(LAST_PANEL_DATE.date()), "predictions": "every out-of-sample prediction finite",
            "reliability_table": "sha256 equals its manifest", "on_failure": "RuntimeError; no result is written"},
        "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
        "outputs": ["definition.json", "config.json", "per_arm_metrics.csv", "fold_metrics.csv", "paired_tests.csv", "metrics.json", "manifest.json",
                    "checkpoints/*", "model/*"],
    }


DEFINITION: dict[str, Any] = _definition()
METHOD_SOURCES = (
    "src/quant/pit/reliability.py", "src/quant/study/exp012.py", "src/quant/validation/runner.py", "src/quant/models/linear.py",
    "src/quant/models/trees.py", "src/quant/models/base.py", "src/quant/pit/rich_panel.py", "src/quant/backtest/engine.py",
    "src/quant/backtest/rules.py", "src/quant/study/exp010a.py", "src/quant/study/exp010b.py", "src/quant/study/exp011.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    """Refuse unless the preregistration is committed, unchanged and already on the remote research branch.

    The repository's generic gate demands an ancestor of origin/main. This study must not be merged to main, so the
    immutability guarantee is the same one aimed at the pushed research branch: the commit that holds the document
    and the method files is an ancestor of `REGISTRATION_REF` before anything is fit.
    """
    root = Path(root)
    doc = root / PREREG_DOC
    expected = definition_fingerprint(root)
    if not doc.exists():
        raise prereg.PreregistrationError(f"{PREREG_DOC} does not exist")
    if f"Definition fingerprint: `{expected}`" not in doc.read_text(encoding="utf-8"):
        raise prereg.PreregistrationError("the preregistration does not embed this definition's fingerprint; nothing is run")
    tracked = [str(PREREG_DOC), *METHOD_SOURCES]
    if _git(root, "status", "--porcelain", "--", *tracked).stdout.strip():
        raise prereg.PreregistrationError("registered files have uncommitted changes")
    commit = _git(root, "log", "-1", "--format=%H", "--", *tracked).stdout.strip()
    if fetch:
        _git(root, "fetch", "origin", "research/market-signal-review-2026-10-11", "--quiet")
    if _git(root, "merge-base", "--is-ancestor", commit, REGISTRATION_REF).returncode != 0:
        raise prereg.PreregistrationError(f"registration commit {commit[:12]} is not on {REGISTRATION_REF}: push it before running")
    return {"preregistration_document": str(PREREG_DOC), "preregistration_sha256": prereg.sha256_file(doc),
            "registration_commit": commit, "pushed_to": REGISTRATION_REF, "definition_fingerprint": expected}


# ── data ─────────────────────────────────────────────────────────────────────

def permute_within_date(frame: pd.DataFrame, columns: Sequence[str], seed: int) -> pd.DataFrame:
    """Shuffle the rows of `columns` across firms within each date, with one permutation shared by all columns."""
    rng = np.random.default_rng(seed)
    out = frame[list(columns)].copy()
    for _, idx in frame.groupby("date", sort=False).indices.items():
        order = rng.permutation(len(idx))
        out.iloc[idx, :] = frame[list(columns)].iloc[idx[order], :].to_numpy()
    return out


def shift_within_security(frame: pd.DataFrame, columns: Sequence[str], rows: int = SHIFT_ROWS) -> pd.DataFrame:
    """Each firm's `columns` taken from `rows` grid steps earlier (NaN where there is no such earlier row)."""
    ordered = frame.sort_values(["symbol", "date"], kind="mergesort")
    shifted = ordered.groupby("symbol", sort=False)[list(columns)].shift(rows)
    return shifted.reindex(frame.index)


def attach_reliability(frame: pd.DataFrame, root: Path = Path(".")) -> pd.DataFrame:
    """Add the reliability block, the composite and the interactions to the validated rich panel (in memory only)."""
    root = Path(root)
    manifest = json.loads((root / rel.MANIFEST).read_text())
    path = root / rel.OUTPUT
    if rel.sha256_file(path) != manifest["output"]["sha256"]:
        raise RuntimeError("reliability table differs from its manifest; rebuild with `python -m src.quant.pit.reliability build`")
    table = pd.read_parquet(path)
    out = frame.merge(table, on=["date", "symbol"], how="left", validate="one_to_one")
    if len(out) != len(frame):
        raise RuntimeError("reliability merge changed the row count")
    out = out.set_index(frame.index)
    out["rel_n_missing"] = out[FUNDAMENTALS].isna().sum(axis=1).astype(float)
    members = {day: set(group["symbol"]) for day, group in out.groupby("date")}
    base = ["rel_n_missing", "periodic_count_400", "amended_730", "lag_deterioration", "latest_report_amended"]
    ranked = xs.cross_sectional_frame(out[["date", "symbol", *base]], base, universe_for=members, method="rank")
    out["rel_missing_xs"] = ranked["rel_n_missing_xs"]
    out["rel_periodic_count_xs"] = ranked["periodic_count_400_xs"]
    out["rel_amended_730_xs"] = ranked["amended_730_xs"]
    out["rel_lag_deterioration_xs"] = ranked["lag_deterioration_xs"]
    out["rel_latest_amended_xs"] = ranked["latest_report_amended_xs"]
    oriented = pd.concat([out[c] * s for c, s in U_COMPONENTS], axis=1)
    raw_u = oriented.mean(axis=1).where(oriented.notna().sum(axis=1) >= U_MIN_COMPONENTS)
    tmp = pd.concat([out[["date", "symbol"]], raw_u.rename("rel_u")], axis=1)
    out["rel_u_xs"] = xs.cross_sectional_frame(tmp, ["rel_u"], universe_for=members, method="rank")["rel_u_xs"]
    for f in FUNDAMENTALS:
        out[f"int_{f}"] = out[f] * out["rel_u_xs"]
    return out.drop(columns=[c for c in table.columns if c not in ("date", "symbol")])


def placebo_frame(frame: pd.DataFrame, kind: str, seed: int, columns: str) -> pd.DataFrame:
    """A copy of `frame` in which one block of reliability columns is a placebo.

    `columns` is "new" (the new block; the interactions, which are built from it, are rebuilt from the placebo) or
    "existing" (the two reliability variables already in the rich set)."""
    block = list(NEW_BLOCK) if columns == "new" else list(EXISTING_RELIABILITY)
    if kind == "permute":
        replaced = permute_within_date(frame, block, seed)
    elif kind == "shift":
        replaced = shift_within_security(frame, block)
    else:
        raise ValueError(kind)
    out = frame.copy()
    out[block] = replaced[block]
    if columns == "new":
        for f in FUNDAMENTALS:
            out[f"int_{f}"] = out[f] * out["rel_u_xs"]
    return out


def arm_features(arm: str) -> list[str]:
    features = ARMS[arm]["features"]
    return arm_features(features) if isinstance(features, str) else list(features)


def arm_frame(frame: pd.DataFrame, arm: str, seed: int) -> pd.DataFrame:
    kind = ARMS[arm].get("placebo")
    return placebo_frame(frame, kind, seed, ARMS[arm]["columns"]) if kind else frame


def fit_arm_seed(arm: str, seed: int, frame: pd.DataFrame, plan: Any):
    spec_arm = ARMS[arm]
    params = RIDGE_PARAMS if spec_arm["model"] == "ridge" else GBR_PARAMS
    spec = ModelSpec(f"{spec_arm['model']}_{arm}_seed_{seed}", spec_arm["model"], tuple(params.items()), seed if spec_arm["model"] != "ridge" else 0)
    return run_walk_forward(spec.build, arm_frame(frame, arm, seed), plan, features=arm_features(arm), label=LABEL, step_sessions=GRID_STEP)


def tasks() -> list[tuple[str, int]]:
    return [(arm, seed) for arm, spec in ARMS.items() for seed in spec.get("seeds", (0,))]


# ── statistics ───────────────────────────────────────────────────────────────

def ic_series(predictions: pd.DataFrame) -> pd.Series:
    return per_date_ic(predictions, prediction_column="prediction", target_column=LABEL)


def block_bootstrap_ci(diff: np.ndarray, *, block: int = BOOTSTRAP_BLOCK, draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """95% interval of the mean of a dependent series by the moving-block bootstrap."""
    n = len(diff)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(draws, int(np.ceil(n / block))))
    means = np.empty(draws)
    for i, s in enumerate(starts):
        means[i] = np.concatenate([diff[j:j + block] for j in s])[:n].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values."""
    order = sorted(p_values, key=p_values.get)
    adjusted, running = {}, 0.0
    for rank, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - rank) * p_values[key]))
        adjusted[key] = running
    return adjusted


def one_sided_p(t_stat: float) -> float:
    from math import erf, sqrt
    return float(0.5 * (1.0 - erf(t_stat / sqrt(2.0))))


def paired(left: pd.Series, right: pd.Series, left_folds: Sequence[float], right_folds: Sequence[float]) -> dict[str, Any]:
    both = pd.concat([left.rename("l"), right.rename("r")], axis=1).dropna()
    diff = (both["l"] - both["r"])
    summary = ic_summary(diff, horizon_sessions=21, step_sessions=GRID_STEP)
    lo, hi = block_bootstrap_ci(diff.to_numpy())
    fold = np.array(left_folds) - np.array(right_folds)
    return {"dates": int(len(diff)), "mean_diff": float(diff.mean()), "hac_t": summary.get("t_stat"), "p_one_sided": one_sided_p(summary["t_stat"]) if summary.get("t_stat") is not None else None,
            "boot95_low": lo, "boot95_high": hi, "positive_folds": int((fold > 0).sum()), "fold_diffs": [float(v) for v in fold]}


def mean_series(series: Sequence[pd.Series]) -> pd.Series:
    return pd.concat(series, axis=1).mean(axis=1)


def classify(contrast: dict[str, Any], adjusted_p: float, placebo_margin: Optional[float]) -> str:
    significant = contrast["mean_diff"] > 0 and adjusted_p < SUPPORT_RULE["alpha"]
    robust = contrast["positive_folds"] >= SUPPORT_RULE["positive_folds_required"]
    placebo_clear = placebo_margin is None or placebo_margin > 0
    if not significant:
        return "NOT_SUPPORTED"
    return "SUPPORTED" if (robust and placebo_clear) else "FRAGILE"


# ── artifacts ────────────────────────────────────────────────────────────────

def train_artifact(frame: pd.DataFrame, arm: str, output: Path, *, fingerprint: str) -> Path:
    """Fit one arm on every pre-holdout row with a label and save a self-describing artifact (research use only)."""
    features = arm_features(arm)
    usable = frame[frame["in_universe"]].dropna(subset=[LABEL])
    FIREWALL.assert_clear(usable, context=f"{EXPERIMENT_ID} final artifact training rows")
    spec = ModelSpec(f"ridge_{arm}_final", "ridge", tuple(RIDGE_PARAMS.items()), 0)
    model = spec.build()
    imputer = FoldImputer(standardise=model.requires_scaling)
    X = imputer.fit_transform(usable[features].to_numpy(dtype=float), feature_names=features)
    model.fit(X, usable[LABEL].to_numpy(dtype=float), feature_names=features)
    path = Path(output) / "model" / f"{arm}.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"experiment": EXPERIMENT_ID, "arm": arm, "features": features, "label": LABEL, "imputer": imputer, "model": model,
                 "trained_rows": int(len(usable)), "trained_through": str(max(usable["date"])), "definition_fingerprint": fingerprint,
                 "reliability_version": rel.VERSION, "status": "RESEARCH ARTIFACT - NOT FOR PRODUCTION - PROMOTION NOT ASSESSED",
                 "dependency_versions": dependency_versions()}, path)
    return path


def load_artifact(path: Path) -> dict[str, Any]:
    bundle = joblib.load(path)
    for key in ("features", "imputer", "model", "label", "experiment", "status"):
        if key not in bundle:
            raise ValueError(f"artifact is missing {key!r}")
    return bundle


def predict_with_artifact(bundle: dict[str, Any], frame: pd.DataFrame) -> pd.Series:
    """Score rows with a saved artifact. Refuses missing columns and non-finite inputs; NaN is imputed as in training."""
    features = bundle["features"]
    missing = [f for f in features if f not in frame.columns]
    if missing:
        raise ValueError(f"input is missing {len(missing)} feature columns, first: {missing[:3]}")
    X = frame[features].to_numpy(dtype=float)
    if np.isinf(X).any():
        raise ValueError("input contains infinite values")
    scores = bundle["model"].predict(bundle["imputer"].transform(X))
    scores = np.asarray(scores, dtype=float)
    if not np.isfinite(scores).all():
        raise ValueError("model produced non-finite scores")
    return pd.Series(scores, index=frame.index, name="score")


# ── run ──────────────────────────────────────────────────────────────────────

_WORKER: dict[str, Any] = {}


def load_frame(root: Path, rehearsal: bool = False) -> pd.DataFrame:
    """The validated rich panel plus the reliability block. A rehearsal shuffles the label across firms within each date, so
    every code path runs on real features and folds while the results carry no information about the hypotheses."""
    frame, _ = exp011.load_rich_panel(root)
    frame = attach_reliability(frame, root)
    if rehearsal:
        frame[LABEL] = permute_within_date(frame, [LABEL], seed=20261012)[LABEL]
    return frame


def _init_worker(root: str, rehearsal: bool = False) -> None:
    _WORKER["frame"] = load_frame(Path(root), rehearsal)
    _WORKER["plan"] = exp009b.recorded_plan(Path(root))


def _task(task: tuple[str, int]) -> tuple[str, int, pd.DataFrame, float, list[str]]:
    arm, seed = task
    result = fit_arm_seed(arm, seed, _WORKER["frame"], _WORKER["plan"])
    if result.errors or result.predictions is None or len(result.folds) != 8:
        return arm, seed, pd.DataFrame(), 0.0, list(result.errors) or ["incomplete folds"]
    return arm, seed, result.predictions, float(result.seconds), []


def acceptance_checks(root: Path, frame: pd.DataFrame, predictions: dict, reports: dict, *, rehearsal: bool = False) -> dict[str, Any]:
    """Section 8 of the preregistration. Raises before any contrast is computed, so a failed gate leaves no result behind.

    A rehearsal uses a shuffled label, so reproduction of the parent's numbers is not meaningful there and is skipped."""
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


def checkpoint_path(output: Path, arm: str, seed: int) -> Path:
    return Path(output) / "checkpoints" / f"{arm}_{seed}.parquet"


def load_checkpoint(output: Path, arm: str, seed: int, fingerprint: str) -> Optional[pd.DataFrame]:
    path, receipt = checkpoint_path(output, arm, seed), checkpoint_path(output, arm, seed).with_suffix(".json")
    if not path.exists() or not receipt.exists():
        return None
    meta = json.loads(receipt.read_text())
    frame = pd.read_parquet(path)
    if meta.get("definition_fingerprint") != fingerprint or meta.get("prediction_sha256") != exp010a._prediction_hash(frame):
        return None
    return frame


def run_study(root: Path = Path("."), *, output: Optional[Path] = None, workers: int = 6, rehearsal: bool = False) -> dict[str, Any]:
    """The registered study. `rehearsal=True` exercises every code path with a shuffled label, writes outside the experiment
    directory, skips the registration gate (it produces no result about the hypotheses) and is marked as a rehearsal."""
    began = time.perf_counter()
    root = Path(root)
    output = Path(output) if output else root / OUTPUT_DIR
    if rehearsal:
        if (root / OUTPUT_DIR).resolve() in (output.resolve(), *output.resolve().parents):
            raise RuntimeError("a rehearsal must not write into the experiment directory")
        gate = {"rehearsal": True, "note": "label shuffled within date; no result about the hypotheses"}
    else:
        gate = prereg_gate(root)                               # before any data is read
    git_state = exp009a._git_state(root)
    guard = exp010b.holdout_guard(root)
    parent = exp010b.verify_parent_artifacts(root)
    if not parent["passed"]:
        raise RuntimeError(f"parent artifacts differ from those registered: {parent['checks']}")
    fingerprint = definition_fingerprint(root) + ("-rehearsal" if rehearsal else "")
    frame = load_frame(root, rehearsal)
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
                    "experiment_id": EXPERIMENT_ID, "arm": arm, "seed": seed, "definition_fingerprint": fingerprint,
                    "prediction_sha256": exp010a._prediction_hash(predictions), "rows": int(len(predictions)), "fit_seconds": seconds,
                    "git_commit": git_state["git_commit"], "python": platform.python_version(), "dependency_versions": dependency_versions()}, indent=1))
                print(f"fitted {arm} seed {seed}: {len(predictions):,} rows in {seconds:.1f}s", flush=True)
    predictions = {(a, s): load_checkpoint(output, a, s, fingerprint) for a, s in tasks()}
    daily, calendar = exp010b.build_daily_panel(root)
    universe = daily[daily["in_universe"]]
    schedule = exp010b.rebalance_schedule(calendar, exp010b.ARMS[exp011.ECONOMICS_ARM]["step_sessions"])
    reports = {key: exp011.arm_seed_report(key[0], key[1], pred, frame, universe, calendar, schedule) for key, pred in predictions.items()}
    acceptance = acceptance_checks(root, frame, predictions, reports, rehearsal=rehearsal)
    series = {key: ic_series(pred) for key, pred in predictions.items()}

    def arm_series(arm: str) -> pd.Series:
        return mean_series([series[(arm, s)] for s in ARMS[arm].get("seeds", (0,))])

    def arm_folds(arm: str) -> list[float]:
        seeds = ARMS[arm].get("seeds", (0,))
        return [float(v) for v in np.mean([reports[(arm, s)]["fold_ic"] for s in seeds], axis=0)]

    contrasts = {name: {"left": l, "right": r, "claim": claim, **paired(arm_series(l), arm_series(r), arm_folds(l), arm_folds(r))}
                 for name, (l, r, claim) in {**CONFIRMATORY, **CONTROLS, **SECONDARY}.items()}
    adjusted = holm({k: contrasts[k]["p_one_sided"] for k in CONFIRMATORY})
    verdicts = {}
    for k in CONFIRMATORY:
        margin = min(contrasts[c]["mean_diff"] for c in PLACEBO_OF[k])
        verdicts[k] = {"adjusted_p": adjusted[k], "label": classify(contrasts[k], adjusted[k], margin), "weakest_placebo_margin": margin}
    output.mkdir(parents=True, exist_ok=True)
    exp010a._atomic_json(output / "definition.json", DEFINITION)
    exp010a._atomic_json(output / "config.json", {"arms": {k: {"features": arm_features(k), "model": v["model"]} for k, v in ARMS.items()},
                                                  "folds": [f.as_dict() for f in plan.folds], "costs": list(exp010b.COSTS)})
    flat = pd.DataFrame([{k: v for k, v in r.items() if k not in ("costs", "fold_ic")} for r in reports.values()])
    flat.to_csv(output / "per_arm_metrics.csv", index=False)
    pd.DataFrame([{"arm": r["arm"], "seed": r["seed"], "fold": i, "mean_rank_ic": v} for r in reports.values() for i, v in enumerate(r["fold_ic"])]).to_csv(output / "fold_metrics.csv", index=False)
    pd.DataFrame([{"contrast": k, **{kk: vv for kk, vv in v.items() if kk != "fold_diffs"}, "fold_diffs": json.dumps(v["fold_diffs"])} for k, v in contrasts.items()]).to_csv(output / "paired_tests.csv", index=False)
    saved = {arm: str(train_artifact(frame, arm, output, fingerprint=fingerprint)) for arm in ("A1", "A5")}
    exp010a._atomic_json(output / "metrics.json", {"per_arm": {f"{a}:{s}": r for (a, s), r in reports.items()}, "contrasts": contrasts, "holm_adjusted": adjusted, "verdicts": verdicts})
    manifest = {"experiment_id": EXPERIMENT_ID, "status": DEFINITION["status"], **gate, **git_state, "holdout": guard, "parent_artifacts_verified": parent["passed"],
                "acceptance": acceptance, "reliability_manifest": json.loads((root / rel.MANIFEST).read_text()), "dependency_versions": dependency_versions(),
                "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(), "workers": workers,
                            "platform": platform.platform(), "python": platform.python_version()},
                "verdicts": verdicts, "artifacts": saved, "completion": "REHEARSAL" if rehearsal else "COMPLETE", "promotion": "NOT ASSESSED"}
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*")) if p.is_file() and p.name != "manifest.json"}
    exp010a._atomic_json(output / "manifest.json", manifest)
    print(f"EXP-012 {'REHEARSAL' if rehearsal else 'COMPLETE'}: {verdicts}", flush=True)
    return {"manifest": manifest, "contrasts": contrasts, "verdicts": verdicts}


def dry_run(root: Path = Path(".")) -> dict[str, Any]:
    """Load, build and fit two cheap arms end to end: proves the plumbing without producing a result."""
    root = Path(root)
    frame = load_frame(root)
    plan = exp009b.recorded_plan(root)
    missing = {arm: [f for f in arm_features(arm) if f not in frame.columns] for arm in ARMS}
    coverage = {c: float(frame[c].notna().mean()) for c in NEW_BLOCK}
    fits = {}
    for arm in ("A0", "A6", "P0s"):
        result = fit_arm_seed(arm, 0, frame, plan)
        fits[arm] = {"errors": list(result.errors), "rows": 0 if result.predictions is None else int(len(result.predictions)), "folds": len(result.folds)}
    return {"rows": int(len(frame)), "columns": int(frame.shape[1]), "missing_features": {k: v for k, v in missing.items() if v},
            "new_block_coverage": coverage, "smoke_fits": fits}
