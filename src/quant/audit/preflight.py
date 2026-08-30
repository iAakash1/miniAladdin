"""
Holdout preflight — the checks that must pass before the holdout may be opened.

The holdout is single-use. Once its outcome is known it cannot be un-known, and
every subsequent decision is contaminated by it whether or not anyone intends
that. So the expensive checking happens *before*, and this module refuses
rather than warns: `run_preflight` returns a report whose `ready` flag is false
if any BLOCKING check fails, and the runner will not proceed on a false.

## Blocking versus advisory

A **blocking** failure means the holdout result would not be interpretable —
contamination, a broken invariant, a missing artifact. An **advisory** finding
is a known limitation that the contract must acknowledge but that does not
invalidate the experiment. Regime imbalance is advisory: it does not make the
result wrong, it bounds what the result can be said to cover.

The distinction is recorded per check rather than decided at read time, so a
failing advisory cannot be quietly reclassified as blocking-and-waived, or the
reverse.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass
class Check:
    name: str
    passed: bool
    blocking: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "passed": self.passed,
            "blocking": self.blocking,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class PreflightReport:
    checks: list[Check] = field(default_factory=list)
    holdout_start: Optional[str] = None
    holdout_end: Optional[str] = None
    fingerprint: Optional[str] = None

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def blocking_failures(self) -> list[Check]:
        return [c for c in self.checks if c.blocking and not c.passed]

    @property
    def advisories(self) -> list[Check]:
        return [c for c in self.checks if not c.blocking and not c.passed]

    @property
    def ready(self) -> bool:
        return not self.blocking_failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "holdout_start": self.holdout_start,
            "holdout_end": self.holdout_end,
            "fingerprint": self.fingerprint,
            "checks": [c.as_dict() for c in self.checks],
            "blocking_failures": [c.name for c in self.blocking_failures],
            "advisories": [c.name for c in self.advisories],
        }


# ── individual checks ────────────────────────────────────────────────────────


def check_contract(path: Path, report: PreflightReport) -> Optional[dict[str, Any]]:
    """The contract must exist and pre-register a single primary candidate."""
    if not path.exists():
        report.add(Check(
            "contract_exists", False, True,
            f"no holdout contract at {path}. The holdout may not be opened without "
            "a pre-registered candidate and success criterion.",
        ))
        return None

    text = path.read_text(encoding="utf-8")
    required = [
        "PRIMARY CANDIDATE", "PRIMARY METRIC", "SUCCESS", "FAILURE",
        "INCONCLUSIVE", "HOLDOUT RANGE",
    ]
    missing = [token for token in required if token not in text]
    report.add(Check(
        "contract_complete", not missing, True,
        f"contract is missing required sections: {missing}" if missing
        else "contract declares candidate, metric, and all three outcomes",
        {"path": str(path), "bytes": len(text)},
    ))

    # Section presence is a weak test: a contract can name every heading and
    # still register no candidate. The ARMED marker is the strong one, and it
    # has to be set deliberately by a human editing this file.
    armed = "| Armed | **YES**" in text or "| Armed | YES" in text
    report.add(Check(
        "contract_armed", armed, True,
        "contract is NOT ARMED — no primary candidate is pre-registered. Arming "
        "requires naming exactly one model, label, feature set, hyperparameters "
        "and seed in the PRIMARY CANDIDATE section, then setting Armed to YES."
        if not armed else "contract is armed with a pre-registered candidate",
    ))
    return {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def check_study_artifact(path: Path, report: PreflightReport) -> Optional[dict[str, Any]]:
    if not path.exists():
        report.add(Check("study_exists", False, True, f"no study artifact at {path}"))
        return None
    study = json.loads(path.read_text(encoding="utf-8"))
    report.add(Check(
        "study_exists", True, True,
        f"study {study.get('dataset', {}).get('dataset_version')} present",
        {"labels": sorted(study.get("labels", {})), "git_commit": study.get("git_commit")},
    ))
    return study


def check_holdout_untouched(study: dict[str, Any], report: PreflightReport) -> None:
    """No fold may reach into the holdout, in any label."""
    violations: list[dict[str, Any]] = []
    starts: set[str] = set()
    for label, block in study.get("labels", {}).items():
        plan = block.get("walk_forward_plan", {})
        start = plan.get("holdout_start")
        if start:
            starts.add(start)
        for fold in plan.get("folds", []):
            if start and fold["validation_end"] >= start:
                violations.append({"label": label, "fold": fold["index"],
                                   "validation_end": fold["validation_end"]})
    report.add(Check(
        "no_fold_reaches_holdout", not violations, True,
        f"{len(violations)} fold(s) validate into the holdout" if violations
        else "every fold ends strictly before the holdout begins",
        {"violations": violations[:5]},
    ))
    report.add(Check(
        "holdout_range_consistent", len(starts) <= 1, True,
        f"labels disagree on the holdout start: {sorted(starts)}" if len(starts) > 1
        else f"single holdout start across labels: {sorted(starts)}",
    ))


def check_folds_chronological(study: dict[str, Any], report: PreflightReport) -> None:
    """Folds must be ordered in time and separated by the full purge + embargo."""
    problems: list[dict[str, Any]] = []
    for label, block in study.get("labels", {}).items():
        plan = block.get("walk_forward_plan", {})
        required = int(plan.get("label_horizon_sessions", 0)) + int(plan.get("embargo_sessions", 0))
        folds = plan.get("folds", [])
        for fold in folds:
            if not (fold["train_start"] <= fold["train_end"] < fold["validation_start"] <= fold["validation_end"]):
                problems.append({"label": label, "fold": fold["index"], "issue": "not chronological"})
            if fold.get("gap_sessions", 0) < required:
                problems.append({"label": label, "fold": fold["index"],
                                 "issue": f"gap {fold.get('gap_sessions')} < required {required}"})
        for a, b in zip(folds, folds[1:]):
            if a["validation_end"] >= b["validation_start"]:
                problems.append({"label": label, "fold": b["index"], "issue": "validation windows overlap"})
    report.add(Check(
        "folds_chronological_and_purged", not problems, True,
        f"{len(problems)} fold problem(s)" if problems
        else "all folds chronological, non-overlapping, fully purged",
        {"problems": problems[:5]},
    ))


#: Constructs that split a sample without regard to time. Any of them in the
#: research path invalidates a temporal study.
_RANDOM_SPLITTERS: tuple[str, ...] = (
    "train_test_split", "KFold", "ShuffleSplit", "StratifiedKFold",
    "GroupKFold", "cross_val_score", "cross_validate", "RandomizedSearchCV",
    "GridSearchCV",
)


def check_no_random_split(report: PreflightReport, root: Path = Path("src/quant")) -> None:
    """No random splitter may be imported or called anywhere in the research path.

    Detection is by AST, not by text search. A substring scan flags this very
    module, whose whole job is to name the banned constructs — the first version
    did exactly that and reported itself as a violation. Parsing distinguishes a
    name that is *used* from a string that merely contains it.
    """
    import ast

    hits: list[str] = []
    paths = list(root.rglob("*.py")) + list(Path("scripts/quant").rglob("*.py"))
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in _RANDOM_SPLITTERS:
                        hits.append(f"{path}: imports {alias.name}")
            elif isinstance(node, ast.Call):
                target = node.func
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name in _RANDOM_SPLITTERS:
                    hits.append(f"{path}:{node.lineno}: calls {name}()")

    report.add(Check(
        "no_random_splitter", not hits, True,
        f"random splitting constructs used: {hits[:3]}" if hits
        else f"no random splitter imported or called across {len(paths)} module(s)",
        {"scanned": len(paths)},
    ))


def check_contamination(
    report: PreflightReport,
    *,
    store_root: str = "data/research",
    universe_dir: str = "data/research/universe",
    start: Date,
    holdout_start: Date,
    end: Date,
    step_sessions: int,
    workers: int = 6,
) -> None:
    """Build the dataset with and without the holdout; pre-holdout rows must match.

    The definitive contamination test, and the one that found the as-of join
    defect. It makes no assumption about *how* a feature is produced: any path
    from a holdout observation to a pre-holdout value changes a number here.
    """
    from src.quant.datasets.store import RawStore
    from src.quant.pit.dataset import DatasetBuilder
    from src.quant.pit.universe import UniverseHistory

    store = RawStore(store_root)
    universe = UniverseHistory.load(universe_dir)

    full = DatasetBuilder(store, universe).build(
        start=start, end=end, step_sessions=step_sessions, workers=workers
    )
    truncated = DatasetBuilder(store, universe).build(
        start=start, end=holdout_start - timedelta(days=1),
        step_sessions=step_sessions, workers=workers,
    )

    key = ["symbol", "date"]
    a = full.frame[full.frame["date"] < holdout_start].set_index(key).sort_index()
    b = truncated.frame[truncated.frame["date"] < holdout_start].set_index(key).sort_index()
    shared = a.index.intersection(b.index)

    contaminated: list[dict[str, Any]] = []
    features = [c for c in full.manifest.features if c in a.columns and c in b.columns]
    for column in features:
        left = pd.to_numeric(a.loc[shared, column], errors="coerce").to_numpy(dtype=float)
        right = pd.to_numeric(b.loc[shared, column], errors="coerce").to_numpy(dtype=float)
        if not np.array_equal(np.isnan(left), np.isnan(right)):
            contaminated.append({"feature": column, "kind": "null_pattern",
                                 "rows": int((np.isnan(left) != np.isnan(right)).sum())})
            continue
        both = ~np.isnan(left)
        if both.any() and not np.allclose(left[both], right[both], rtol=1e-9, atol=1e-12):
            contaminated.append({"feature": column, "kind": "values",
                                 "max_abs_diff": float(np.nanmax(np.abs(left[both] - right[both])))})

    report.add(Check(
        "rows_unchanged_by_holdout", len(a) == len(b) and len(shared) == len(a), True,
        f"pre-holdout row sets differ: {len(a)} vs {len(b)}, shared {len(shared)}"
        if not (len(a) == len(b) == len(shared))
        else f"{len(a):,} pre-holdout rows identical in both builds",
    ))
    report.add(Check(
        "features_unchanged_by_holdout", not contaminated, True,
        f"{len(contaminated)} feature(s) change when the holdout is present"
        if contaminated else f"all {len(features)} features identical without the holdout",
        {"contaminated": contaminated[:12]},
    ))


def check_registry_clean(report: PreflightReport, root: str = "data/research/models") -> None:
    """Nothing may already be in production when the holdout is opened."""
    from src.quant.models.registry import ModelRegistry

    registry = ModelRegistry(root)
    promoted = registry.by_status("production")
    report.add(Check(
        "no_model_in_production", not promoted, True,
        f"{len(promoted)} model(s) already in production" if promoted
        else f"registry holds {len(registry.all())} entries, none in production",
        {"by_status": registry.summary()["by_status"]},
    ))


def check_regime_balance(study: dict[str, Any], report: PreflightReport, *, minimum: int = 60) -> None:
    """Advisory: thin regimes bound what the result can be said to cover."""
    distribution = study.get("regimes", {}).get("rules", {}).get("distribution", {})
    thin = {name: count for name, count in distribution.items() if count < minimum}
    report.add(Check(
        "regime_balance", not thin, False,
        f"regimes with fewer than {minimum} observation dates: {thin}. Any claim "
        "about these states is anecdote, not evidence, and the contract must say so."
        if thin else "every regime has adequate representation",
        {"distribution": distribution},
    ))


def check_git_clean(report: PreflightReport) -> Optional[str]:
    """The code that runs the holdout must be committed, so it can be named."""
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=15
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=15
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        report.add(Check("git_clean", False, True, f"git unavailable: {error}"))
        return None
    report.add(Check(
        "git_clean", not dirty, True,
        "working tree has uncommitted changes; the holdout must run on a named "
        f"commit ({len(dirty.splitlines())} paths dirty)" if dirty
        else f"working tree clean at {commit[:12]}",
        {"commit": commit},
    ))
    return commit


# ── driver ───────────────────────────────────────────────────────────────────


def run_preflight(
    *,
    contract_path: Path = Path("docs/HOLDOUT_CONTRACT.md"),
    study_path: Path = Path("data/research/reports/study.json"),
    store_root: str = "data/research",
    run_contamination: bool = True,
    workers: int = 6,
) -> PreflightReport:
    """Every gate. Returns a report; the caller decides nothing, the flag does."""
    report = PreflightReport()

    contract = check_contract(contract_path, report)
    study = check_study_artifact(study_path, report)
    check_no_random_split(report)
    check_registry_clean(report)
    commit = check_git_clean(report)

    if study is not None:
        check_holdout_untouched(study, report)
        check_folds_chronological(study, report)
        check_regime_balance(study, report)

        plan = next(iter(study["labels"].values()))["walk_forward_plan"]
        report.holdout_start = plan.get("holdout_start")
        report.holdout_end = plan.get("holdout_end")

        if run_contamination and report.holdout_start:
            dataset = study.get("dataset", {})
            check_contamination(
                report,
                store_root=store_root,
                start=Date.fromisoformat(dataset["start"]),
                holdout_start=Date.fromisoformat(report.holdout_start),
                end=Date.fromisoformat(dataset["end"]),
                step_sessions=int(dataset.get("step_sessions", 5)),
                workers=workers,
            )

    report.fingerprint = compute_fingerprint(
        study=study, contract_sha=(contract or {}).get("sha256"), commit=commit
    )
    return report


def compute_fingerprint(
    *,
    study: Optional[dict[str, Any]],
    contract_sha: Optional[str],
    commit: Optional[str],
) -> str:
    """Hash of everything that must be frozen before the holdout is opened.

    Recorded before execution and re-checked after. If it changes between
    preflight and run, something was edited in between and the result is not the
    experiment that was pre-registered.
    """
    payload = {
        "dataset_version": (study or {}).get("dataset", {}).get("dataset_version"),
        "content_hash": (study or {}).get("dataset", {}).get("content_hash"),
        "features": sorted((study or {}).get("features_used", [])),
        "seed": (study or {}).get("seed"),
        "contract_sha256": contract_sha,
        "git_commit": commit,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
