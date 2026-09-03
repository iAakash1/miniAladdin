"""
ML intelligence service — the product-facing read layer over the research artifacts.

## Read-only, and why that is the whole design

This service **never trains, never backtests and never ingests**. It reads the
study report and the model registry that `scripts/quant/study.py` produced, and
shapes them for the API. A page load must not be able to start a walk-forward,
which is the same reason `src/services/backtest_service.peek_cached` exists:
research is minutes of work and an HTTP request is not the place for it.

The consequence is stated rather than hidden — when no study has been run, every
endpoint reports `unavailable` with the command that would produce one. It does
not compute a quick approximation to have something to render. A cheap
substitute rendered in the place of a rigorous result is worse than an empty
state, because the reader cannot tell which one they are looking at.

## What the payload has to carry

Three things travel with every number, because without them the number is not
evidence:

* **Provenance** — which dataset version, which sources, retrieved when.
* **Status** — `OBSERVED`, `DERIVED` or `MODEL_PREDICTED`. A close is observed,
  a rank is derived, a forecast is none of those, and rendering them alike
  invites a reader to trust them alike.
* **The numbers that argue against it** — the fold-level dispersion, the
  experiment count, the deflated Sharpe, the factor attribution. A leaderboard
  that shows only the winning metric is a marketing surface.
"""

from __future__ import annotations

import json
import math
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("omnisignal.services.ml")

DEFAULT_ROOT = Path("data/research")
REPORT_NAME = "study.json"

#: Study artifacts whose results a later audit invalidated.
#:
#: Keyed by dataset version, because that is what identifies the run. The study
#: file is deliberately NOT deleted: removing it would erase the
#: multiple-testing exposure it created, which docs/RESEARCH_LEDGER.md has to
#: account for. Instead every surface that renders it says so, so a reader
#: cannot encounter the numbers without the retraction attached.
#: The commit that fixed the as-of join defect. A study built at or after this
#: commit is not affected by it, whatever dataset version it used.
#:
#: This distinction was wrong before EXP-005 and would have mislabelled a valid
#: study. The defect lived in the FEATURE CODE, not in the data — EXP-004 rebuilt
#: the very same dataset version with the fix and produced admissible results.
#: Keying invalidity on `dataset_version` alone therefore condemns every future
#: study that happens to rebuild that version, which is the opposite of what the
#: retraction is for. Validity is now a property of the study, identified by its
#: experiment id, with the dataset version kept only as a corroborating signal.
AS_OF_FIX_COMMIT = "3bbe8e36b09098528ba4300fd7c1f2f34fbac940"

#: Experiment ids whose results a later audit invalidated. Never deleted:
#: removing one would erase the multiple-testing exposure it created.
VOID_EXPERIMENT_IDS: frozenset[str] = frozenset({"EXP-002"})

INVALIDATED_STUDIES: dict[str, dict[str, Any]] = {
    "ds-e691b48ca49deb16": {
        "reason": (
            "pandas.merge_asof discards the left index, so both as-of joins wrote "
            "values back positionally into a differently-ordered frame. 12 of the "
            "39 features carried other rows' values, some from later dates."
        ),
        "audit": "docs/PRE_HOLDOUT_AUDIT.md",
        "void_models": "every model consuming the full feature set",
        "surviving_models": [
            "baseline_momentum", "baseline_reversal", "baseline_low_volatility",
        ],
        "surviving_note": (
            "Single-feature passthroughs of correctly-aligned price columns. "
            "Neither is significant at |t| > 2."
        ),
    },
}


def study_validity(
    dataset_version: Optional[str],
    *,
    experiment_id: Optional[str] = None,
    git_commit: Optional[str] = None,
) -> dict[str, Any]:
    """Whether a study's results may be presented as findings.

    A study is void because of how it was BUILT, not because of which dataset
    version it read. `experiment_id` is therefore the authoritative key; the
    dataset version is consulted only when the caller cannot supply one, and
    even then a study built at the fix commit is cleared.
    """
    if experiment_id is not None:
        if experiment_id in VOID_EXPERIMENT_IDS:
            record = INVALIDATED_STUDIES.get(dataset_version or "", {})
            return {"valid": False, "dataset_version": dataset_version,
                    "experiment_id": experiment_id, **record}
        return {"valid": True, "experiment_id": experiment_id}

    record = INVALIDATED_STUDIES.get(dataset_version or "")
    if record is None:
        return {"valid": True}

    if git_commit and git_commit.startswith(AS_OF_FIX_COMMIT[:12]):
        return {
            "valid": True,
            "dataset_version": dataset_version,
            "note": (
                "Built at the commit that fixed the as-of join defect. The defect "
                "was in the feature code, not in this dataset version."
            ),
        }
    return {"valid": False, "dataset_version": dataset_version, **record}

#: Study artifacts are immutable outputs of a batch job, so a long TTL is
#: correct: re-reading a 2 MB JSON per request would spend I/O to produce an
#: identical answer. Invalidated by mtime, so a fresh study is picked up.
CACHE_TTL_SECONDS = 300.0

_cache: dict[str, tuple[float, float, Any]] = {}
_lock = threading.Lock()


class MLUnavailable(RuntimeError):
    """Raised when no study artifact exists. Never substituted with an estimate."""


def _finite(value: Any) -> Any:
    """Replace non-finite floats with None, everywhere in a parsed payload.

    A study artifact can legitimately contain NaN. `deflated_sharpe` on a model
    with twelve observations is the case that prompted this: the routine
    correctly refuses a verdict — `deflated_probability` and `significant` are
    already null, with a note reading "fewer than 30 periods" — but the inputs
    it could not compute stay NaN.

    Two reasons those cannot travel further.

    NaN is not JSON. `json.dumps` refuses it, so one unreachable statistic on
    one baseline model took the entire label report to a 500 and every surface
    reading it went blank. An endpoint that fails completely because a single
    number could not be computed is worse than one that says so.

    And null is what this codebase already means by "not computed". It is the
    convention every envelope uses, and this same dict already applies it to its
    own verdict fields — so a NaN becoming null says exactly what the
    surrounding data says, in the form the rest of the product reads.

    Zero is emphatically not the substitute. A Sharpe of NaN means the statistic
    could not be formed; a Sharpe of 0.0 means it was formed and came out flat,
    which is a measurement this model never produced.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def _read_json(path: Path) -> Any:
    key = str(path)
    now = time.time()
    try:
        mtime = path.stat().st_mtime
    except OSError as error:
        raise MLUnavailable(str(error)) from error

    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now and entry[1] == mtime:
            return entry[2]

    payload = _finite(json.loads(path.read_text(encoding="utf-8")))
    with _lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, mtime, payload)
    return payload


#: Where completed experiments are written. Preferred over the legacy report.
EXPERIMENTS_ROOT = Path("experiments")


def _newest_valid_experiment(root: Optional[Path] = None) -> Optional[tuple[str, Path]]:
    """The newest completed, non-void experiment artifact.

    `data/research/reports/study.json` is written by the standalone study runner
    and carries no experiment id, so `study_validity` can only key it on dataset
    version — and the one on disk was generated before the as-of fix, against
    the version that voided EXP-002. The Models workspace was therefore serving
    the invalidated study as its leaderboard, walk-forward, cost and regime
    sections, under headings that did not say which study they were.

    EXP-004 onward are on disk, valid, and schema-compatible. This prefers them,
    newest first, and falls back to the legacy report only when no experiment
    artifact exists.
    """
    # Resolved at call time, not bound as a default: a module-level constant
    # captured in a signature cannot be overridden by a deployment or a test,
    # and silently ignoring the override is worse than not offering one.
    root = Path(root) if root is not None else EXPERIMENTS_ROOT
    if not root.exists():
        return None
    candidates: list[tuple[str, str, Path]] = []
    for directory in sorted(root.iterdir(), reverse=True):
        artifact = directory / "metrics.json"
        if not artifact.is_file():
            continue
        try:
            payload = _finite(json.loads(artifact.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
        experiment_id = (payload.get("experiment") or {}).get("experiment_id")
        if experiment_id in VOID_EXPERIMENT_IDS:
            continue
        if not payload.get("labels"):
            continue
        generated = str(payload.get("generated_at") or "")
        candidates.append((generated, experiment_id or directory.name, artifact))
    if not candidates:
        return None
    generated, experiment_id, artifact = max(candidates)
    return experiment_id, artifact


def _study(root: Path) -> Any:
    """The study the ML surfaces render. Newest valid experiment wins.

    The experiment preference applies to the DEFAULT root only. A caller that
    names a root means it — a test pointing at a fixture directory, or a
    deployment mounting research data elsewhere — and silently serving a
    different study than the one asked for is a worse failure than the one this
    preference exists to fix.
    """
    newest = _newest_valid_experiment() if Path(root) == DEFAULT_ROOT else None
    if newest is not None:
        experiment_id, artifact = newest
        payload = _read_json(artifact)
        # Stamp the source so callers — and the page — can name the study.
        payload.setdefault("experiment_id", experiment_id)
        payload.setdefault("source_artifact", str(artifact))
        return payload

    path = root / "reports" / REPORT_NAME
    if not path.exists():
        raise MLUnavailable(
            f"no completed experiment under {EXPERIMENTS_ROOT} and no study report "
            f"at {path}. Run `python -m scripts.quant.study --all-labels`. "
            "Nothing is estimated in its place: an approximation rendered where a "
            "walk-forward result belongs cannot be told apart from the real thing."
        )
    return _read_json(path)


def _unavailable(error: Exception) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": str(error),
        "remediation": "python -m scripts.quant.study --all-labels",
    }


# ── public surface ───────────────────────────────────────────────────────────


def capabilities(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """What the ML layer can currently answer, and why not when it cannot.

    Mirrors `/api/providers/capabilities`: availability is reported per
    capability with a named reason, rather than a page discovering emptiness
    by rendering it.
    """
    root = Path(root)
    out: dict[str, Any] = {"root": str(root), "capabilities": {}}

    from src.quant.datasets.store import RawStore
    from src.quant.models.linear import SKLEARN_AVAILABLE

    store = RawStore(root)
    try:
        datasets = store.list_datasets()
    except Exception as error:  # noqa: BLE001
        datasets = []
        out["dataset_error"] = str(error)

    def record(name: str, ready: bool, detail: str, **extra: Any) -> None:
        out["capabilities"][name] = {
            "status": "available" if ready else "unavailable",
            "detail": detail,
            **extra,
        }

    record(
        "raw_datasets", bool(datasets),
        f"{len(datasets)} ingested dataset(s)" if datasets
        else "no raw datasets — run `python -m scripts.quant.backfill --stage all`",
        datasets=[
            {
                "dataset_id": manifest.dataset_id,
                "rows": manifest.rows,
                "partitions": len(manifest.partitions),
                "min_date": manifest.min_date,
                "max_date": manifest.max_date,
                "point_in_time_status": manifest.point_in_time_status,
                "survivorship_status": manifest.survivorship_status,
                "retrieved_at": manifest.retrieved_at,
            }
            for manifest in datasets
        ],
    )

    universe_path = root / "universe" / "liquid.json"
    record(
        "point_in_time_universe", universe_path.exists(),
        "survivorship-free monthly membership" if universe_path.exists()
        else "no universe — run `backfill --stage universe`",
    )

    record(
        "learned_models", SKLEARN_AVAILABLE,
        "scikit-learn present" if SKLEARN_AVAILABLE
        else "scikit-learn absent; baselines still run, learned models report unavailable",
    )

    try:
        study = _study(root)
        record(
            "study", True,
            f"{len(study.get('labels', {}))} label(s) evaluated",
            generated_at=study.get("generated_at"),
            git_commit=study.get("git_commit"),
            runtime_seconds=study.get("runtime_seconds"),
        )
    except MLUnavailable as error:
        record("study", False, str(error))

    return out


def dataset_catalog() -> dict[str, Any]:
    """The catalog as data: what is admissible, what is gated, what is refused.

    Three tiers, not two. `excluded` is refused outright at admission.
    `gated` is admissible but only behind a publication gate — a fiscal-period
    key is not an availability date, so those sources reach a feature only after
    an as-of join to an announcement. Reporting only `excluded` would let the UI
    imply that everything not refused is unconditionally safe, which is the
    opposite of what PUBLICATION_LAGGED means.
    """
    from src.quant.datasets.catalog import (
        CATALOG, PointInTimeClass, catalog_payload, training_admissible,
    )

    return {
        "datasets": catalog_payload(),
        "total": len(CATALOG),
        "training_admissible": len(training_admissible()),
        "excluded": [
            {
                "dataset_id": spec.dataset_id,
                "reason": spec.point_in_time_note,
                "classification": spec.point_in_time.value,
            }
            for spec in CATALOG
            if not spec.historical_training_allowed
        ],
        "gated": [
            {
                "dataset_id": spec.dataset_id,
                "reason": spec.point_in_time_note,
                "classification": spec.point_in_time.value,
                "gate": (
                    "Admissible only after an as-of join to an availability date. "
                    "The builder refuses to read this source as-dated."
                ),
                "residual_risk": [
                    limit for limit in spec.limitations
                    if "restatement" in limit.lower() or "UNQUANTIFIED" in limit
                ],
            }
            for spec in CATALOG
            if spec.point_in_time is PointInTimeClass.PUBLICATION_LAGGED
        ],
    }


def feature_catalog() -> dict[str, Any]:
    """Every feature's definition, rationale and point-in-time contract."""
    from src.quant.features import cross_section, macro, price  # noqa: F401
    from src.quant.features.registry import REGISTRY
    from src.quant.labels import catalog as label_catalog

    return {
        "features": REGISTRY.catalog(),
        "feature_count": len(REGISTRY.definitions),
        "labels": label_catalog(),
        "unsafe_features": REGISTRY.unsafe(),
        "max_lookback_sessions": REGISTRY.max_lookback(),
    }


#: Models in the ladder purely as diagnostics. They may never be presented as a
#: study's best result. Mirrors `quant_service.OVERFIT_CONTROL_MODELS`.
OVERFIT_CONTROL_MODELS: frozenset[str] = frozenset({"gradient_boosting_deep"})


def _headline_model(leaderboard: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The best genuine candidate, skipping diagnostic controls.

    Falls back to nothing rather than to the control: a study whose only entry
    is an overfitting control has no best model, and saying so is correct.
    """
    for row in leaderboard:
        if row.get("model_id") not in OVERFIT_CONTROL_MODELS:
            return row
    return None


def overview(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """Headline state: dataset, universe, regime, and the leaderboard summary."""
    try:
        study = _study(Path(root))
    except MLUnavailable as error:
        return _unavailable(error)

    validity = study_validity(study.get("dataset", {}).get("dataset_version"))
    labels = study.get("labels", {})
    headline: list[dict[str, Any]] = []
    for label, report in labels.items():
        leaderboard = report.get("leaderboard", [])
        if not leaderboard:
            continue
        # The leaderboard is ordered by IC, and `gradient_boosting_deep` is the
        # deliberately over-parameterised control — it tops that ordering
        # BECAUSE it memorises the training fold. Taking row zero would headline
        # the one model in the ladder that exists to prove the overfitting
        # diagnostic fires, and label it "best".
        #
        # The control stays in the leaderboard table below, where its gap is
        # visible and makes the point it is there to make. It is only excluded
        # from being called best.
        best = _headline_model(leaderboard)
        if best is None:
            continue
        model_id = best.get("model_id")
        headline.append(
            {
                "label": label,
                "horizon_sessions": report.get("horizon_sessions"),
                "best_model": model_id,
                "mean_ic": best.get("mean_ic"),
                "ic_t_stat": best.get("ic_t_stat"),
                "fold_ic_positive_rate": best.get("fold_ic_positive_rate"),
                # The overfitting diagnostic travels with the headline, not
                # only in the detail table: a card showing IC without the gap
                # invites reading a memorised training fold as a result.
                "train_mean_ic": best.get("train_mean_ic"),
                "train_ic_gap": best.get("train_ic_gap"),
                "experiments": report.get("experiment_distribution", {}).get("experiments"),
                "median_ic": report.get("experiment_distribution", {}).get("median"),
                "net_sharpe": (
                    report.get("backtests", {}).get(model_id, {}).get("metrics", {}).get("net_sharpe")
                ),
                "alpha_significant": (
                    report.get("factor_attribution", {}).get(model_id, {}).get("alpha_significant")
                ),
                "deflated_sharpe_probability": (
                    report.get("significance", {}).get(model_id, {})
                    .get("deflated_sharpe", {}).get("deflated_probability")
                ),
                "pbo": report.get("probability_of_backtest_overfitting", {}).get("pbo"),
                "verdict": _verdict(report, model_id, validity=validity),
            }
        )

    regimes = study.get("regimes", {})
    rules = regimes.get("rules", {})
    return {
        "status": "available",
        "validity": validity,
        "generated_at": study.get("generated_at"),
        "git_commit": study.get("git_commit"),
        "runtime_seconds": study.get("runtime_seconds"),
        "dataset": {
            key: study.get("dataset", {}).get(key)
            for key in ("dataset_version", "rows", "symbols", "dates", "start", "end", "content_hash")
        },
        "guards": study.get("dataset", {}).get("guard_report", {}),
        "universe": study.get("universe", {}),
        "regime": {
            "method": rules.get("method"),
            "distribution": rules.get("distribution", {}),
            "current": _current_regime(study),
            "agreement": regimes.get("agreement", {}),
        },
        "labels": headline,
        # Which study these numbers are. The page previously rendered a study it
        # could not name, which is how it went on serving a voided one.
        "experiment_id": study.get("experiment_id")
        or (study.get("experiment") or {}).get("experiment_id"),
        "source_artifact": study.get("source_artifact"),
        "feature_count": len(study.get("features_used", [])),
        "dependency_versions": study.get("dependency_versions", {}),
    }


def label_report(label: str, root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """Everything measured for one label — every model, not only the winner."""
    try:
        study = _study(Path(root))
    except MLUnavailable as error:
        return _unavailable(error)

    report = study.get("labels", {}).get(label)
    if report is None:
        return {
            "status": "unavailable",
            "reason": f"label {label!r} was not evaluated",
            "available": sorted(study.get("labels", {})),
        }

    models: list[dict[str, Any]] = []
    for row in report.get("leaderboard", []):
        model_id = row["model_id"]
        backtest = report.get("backtests", {}).get(model_id, {})
        models.append(
            {
                **row,
                "kind": "baseline" if model_id.startswith("baseline_") else "learned",
                "backtest": backtest.get("metrics", {}),
                "cost_sensitivity": report.get("cost_sensitivity", {}).get(model_id, []),
                "factor_attribution": report.get("factor_attribution", {}).get(model_id, {}),
                "regime_performance": report.get("regime_performance", {}).get(model_id, []),
                "significance": report.get("significance", {}).get(model_id, {}),
                "explanation": _explanation_for(report, model_id),
            }
        )

    return {
        "status": "available",
        "validity": study_validity(study.get("dataset", {}).get("dataset_version")),
        "label": label,
        "horizon_sessions": report.get("horizon_sessions"),
        "walk_forward": report.get("walk_forward_plan", {}),
        "fold_rows": report.get("fold_rows", []),
        "overlap_check": report.get("overlap_check", {}),
        "experiment_distribution": report.get("experiment_distribution", {}),
        "probability_of_backtest_overfitting": report.get("probability_of_backtest_overfitting", {}),
        "models": models,
        "dataset": study.get("dataset", {}),
    }


def registry(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """The model registry: status, evidence, and what each model still lacks."""
    from src.quant.models.registry import ModelRegistry

    try:
        store = ModelRegistry(Path(root) / "models")
    except Exception as error:  # noqa: BLE001
        return _unavailable(error)

    entries = store.all()
    if not entries:
        return _unavailable(MLUnavailable("no models registered"))
    return {
        "status": "available",
        "summary": store.summary(),
        "leaderboard": store.leaderboard(),
        "entries": [entry.as_dict() for entry in entries],
        "promotion_gates": {
            status: [description for _, description in requirements]
            for status, requirements in
            __import__("src.quant.models.registry", fromlist=["PROMOTION_GATES"]).PROMOTION_GATES.items()
        },
    }


def provenance(label: str, model_id: str, root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """The full chain behind one model's predictions.

    Answers "why did the model predict this?" by naming every layer between a
    raw vendor observation and the number on screen. It does not claim a causal
    story; it names the inputs, which is the claim the architecture can support.
    """
    try:
        study = _study(Path(root))
    except MLUnavailable as error:
        return _unavailable(error)

    report = study.get("labels", {}).get(label)
    if report is None:
        return {"status": "unavailable", "reason": f"label {label!r} not evaluated"}

    dataset = study.get("dataset", {})
    return {
        "status": "available",
        "chain": [
            {
                "stage": "source",
                "kind": "OBSERVED",
                "detail": "Vendor observations in immutable, checksummed partitions.",
                "evidence": dataset.get("source_datasets", []),
            },
            {
                "stage": "point_in_time_returns",
                "kind": "DERIVED",
                "detail": (
                    "Split and dividend applied on the ex-date only. No back-adjustment, "
                    "so no historical value changes when a later action occurs."
                ),
                "evidence": {"module": "src/quant/pit/adjust.py"},
            },
            {
                "stage": "features",
                "kind": "DERIVED",
                "detail": "Backward-looking windows only; each feature declares its lookback and lag.",
                "evidence": {
                    "features": study.get("features_used", []),
                    "guards": dataset.get("guard_report", {}),
                },
            },
            {
                "stage": "universe",
                "kind": "DERIVED",
                "detail": (
                    "Survivorship-free monthly membership selected from whole-market "
                    "cross-sections. Cross-sectional ranks are computed within it."
                ),
                "evidence": study.get("universe", {}),
            },
            {
                "stage": "model",
                "kind": "MODEL_PREDICTED",
                "detail": f"{model_id} fitted per walk-forward fold on training rows only.",
                "evidence": {
                    "walk_forward": report.get("walk_forward_plan", {}),
                    "explanation": _explanation_for(report, model_id),
                    "seed": study.get("seed"),
                    "dependency_versions": study.get("dependency_versions", {}),
                },
            },
            {
                "stage": "backtest",
                "kind": "DERIVED",
                "detail": "Out-of-sample predictions traded with per-rebalance costs.",
                "evidence": report.get("backtests", {}).get(model_id, {}).get("config", {}),
            },
            {
                "stage": "attribution",
                "kind": "DERIVED",
                "detail": (
                    "Net returns regressed on Fama-French 5 factors plus momentum. "
                    "The intercept is the only quantity here that may be called alpha."
                ),
                "evidence": report.get("factor_attribution", {}).get(model_id, {}),
            },
        ],
        "dataset_version": dataset.get("dataset_version"),
        "content_hash": dataset.get("content_hash"),
        "git_commit": study.get("git_commit"),
    }


# ── helpers ──────────────────────────────────────────────────────────────────


def _explanation_for(report: dict[str, Any], model_id: str) -> dict[str, Any]:
    for result in report.get("experiments", {}).get("results", []):
        if result.get("model_id") == model_id:
            return result.get("explanation", {})
    return {}


def _current_regime(study: dict[str, Any]) -> Optional[str]:
    distribution = study.get("regimes", {}).get("rules", {}).get("distribution", {})
    return max(distribution, key=distribution.get) if distribution else None


def _verdict(
    report: dict[str, Any],
    model_id: Optional[str],
    *,
    validity: Optional[dict[str, Any]] = None,
) -> str:
    """A one-line reading that cannot overstate what was measured.

    Deliberately conservative and ordered by severity: the strongest available
    negative finding wins. A model that clears the IC bar but loses to costs is
    reported as losing to costs.
    """
    if not model_id:
        return "No model produced predictions."

    # A retraction outranks every other finding. Rendering "survives every test"
    # for a model fitted on a corrupted matrix would be the worst possible
    # failure of this surface.
    if validity and not validity.get("valid", True):
        surviving = set(validity.get("surviving_models", []))
        if model_id in surviving:
            return (
                f"RESULT VALID but not significant. {model_id} is a single-feature "
                "passthrough unaffected by the join defect that voided this study; "
                f"see {validity.get('audit')}."
            )
        return (
            f"RESULT VOID — this study was invalidated by a later audit. "
            f"{validity.get('reason')} See {validity.get('audit')}."
        )

    leaderboard = {row["model_id"]: row for row in report.get("leaderboard", [])}
    row = leaderboard.get(model_id, {})
    ic_t = row.get("ic_t_stat")
    baselines = [
        r.get("mean_ic") for key, r in leaderboard.items()
        if key.startswith("baseline_") and isinstance(r.get("mean_ic"), (int, float))
    ]
    mean_ic = row.get("mean_ic")
    backtest = report.get("backtests", {}).get(model_id, {}).get("metrics", {})
    attribution = report.get("factor_attribution", {}).get(model_id, {})
    significance = (
        report.get("significance", {}).get(model_id, {}).get("deflated_sharpe", {})
    )

    if not isinstance(mean_ic, (int, float)):
        return "No usable out-of-sample predictions."
    if isinstance(ic_t, (int, float)) and abs(ic_t) < 2.0:
        return (
            f"NO STATISTICALLY USEFUL SIGNAL FOUND. Mean rank IC {mean_ic:+.4f} with a "
            f"Newey-West t of {ic_t:+.2f} — not distinguishable from zero."
        )
    if baselines and mean_ic <= max(baselines):
        return (
            f"Does not beat the best free baseline (IC {mean_ic:+.4f} vs "
            f"{max(baselines):+.4f}). The learned model adds nothing over a factor "
            "available since 1993."
        )
    net_sharpe = backtest.get("net_sharpe")
    gross_sharpe = backtest.get("gross_sharpe")
    turnover = backtest.get("annualised_turnover")
    cost_share = backtest.get("cost_share_of_gross")
    if isinstance(net_sharpe, (int, float)) and net_sharpe <= 0:
        detail = f"gross Sharpe {gross_sharpe:+.2f}" if isinstance(gross_sharpe, (int, float)) else "gross Sharpe n/a"
        if isinstance(turnover, (int, float)):
            detail += f", turnover {turnover:.1f}x/yr"
        if isinstance(cost_share, (int, float)):
            detail += f", costs {cost_share * 100:.0f}% of gross"
        return f"Signal survives significance but NOT costs: {detail}, net Sharpe {net_sharpe:+.2f}."
    if attribution.get("alpha_significant") is False:
        return (
            "Returns are explained by factor exposure. "
            + str(attribution.get("verdict", ""))
        )
    if significance.get("significant") is False:
        return (
            "Not significant once the number of configurations tried is accounted for "
            f"(deflated Sharpe probability {significance.get('deflated_probability')})."
        )
    if isinstance(net_sharpe, (int, float)) and abs(net_sharpe) < 0.15:
        return (
            f"Statistically detectable, economically negligible: mean IC {mean_ic:+.4f} "
            f"(t {ic_t:+.2f}) but net Sharpe {net_sharpe:+.2f} after costs. A signal this "
            "size is not tradeable at the turnover it requires."
        )
    return (
        f"Survives significance, costs and factor attribution: mean IC {mean_ic:+.4f}, "
        f"t {ic_t:+.2f}, net Sharpe {net_sharpe:+.2f}."
    )


def reset_for_tests() -> None:
    with _lock:
        _cache.clear()
