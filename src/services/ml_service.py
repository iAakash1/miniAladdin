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
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("omnisignal.services.ml")

DEFAULT_ROOT = Path("data/research")
REPORT_NAME = "study.json"

#: Study artifacts are immutable outputs of a batch job, so a long TTL is
#: correct: re-reading a 2 MB JSON per request would spend I/O to produce an
#: identical answer. Invalidated by mtime, so a fresh study is picked up.
CACHE_TTL_SECONDS = 300.0

_cache: dict[str, tuple[float, float, Any]] = {}
_lock = threading.Lock()


class MLUnavailable(RuntimeError):
    """Raised when no study artifact exists. Never substituted with an estimate."""


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

    payload = json.loads(path.read_text(encoding="utf-8"))
    with _lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, mtime, payload)
    return payload


def _study(root: Path) -> Any:
    path = root / "reports" / REPORT_NAME
    if not path.exists():
        raise MLUnavailable(
            f"no study report at {path}. Run `python -m scripts.quant.study --all-labels`. "
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
    """The catalog as data, including what is deliberately excluded and why."""
    from src.quant.datasets.catalog import CATALOG, catalog_payload, training_admissible

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


def overview(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    """Headline state: dataset, universe, regime, and the leaderboard summary."""
    try:
        study = _study(Path(root))
    except MLUnavailable as error:
        return _unavailable(error)

    labels = study.get("labels", {})
    headline: list[dict[str, Any]] = []
    for label, report in labels.items():
        leaderboard = report.get("leaderboard", [])
        if not leaderboard:
            continue
        best = leaderboard[0]
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
                "verdict": _verdict(report, model_id),
            }
        )

    regimes = study.get("regimes", {})
    rules = regimes.get("rules", {})
    return {
        "status": "available",
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


def _verdict(report: dict[str, Any], model_id: Optional[str]) -> str:
    """A one-line reading that cannot overstate what was measured.

    Deliberately conservative and ordered by severity: the strongest available
    negative finding wins. A model that clears the IC bar but loses to costs is
    reported as losing to costs.
    """
    if not model_id:
        return "No model produced predictions."

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
