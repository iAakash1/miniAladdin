"""
Portfolio construction and risk, computed for the UI.

## What this is for

`/quant` needs to show what the research signal would look like *as a book*:
weights, risk contributions, concentration and the estimated execution cost of
entering the illustrative book. All of that is arithmetic on artifacts that
already exist, so it is computed here on demand rather than stored.

## What it deliberately does not do

It does not promote anything, it does not recompute any research metric, and it
does not present an optimised weight as evidence. An allocation built from a
model whose net Sharpe is −0.102 is an illustration of how that signal would be
held — not a claim that holding it is a good idea. Every payload says so.

Predictions come from the committed EXP-006 artifact, so this surface works
without the inference service and without the 14 GB research dataset.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.services.quant_portfolio")

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPOSITORY_ROOT / "experiments"
RUNTIME_ARTIFACTS = REPOSITORY_ROOT / "artifacts" / "runtime" / "portfolio"
RUNTIME_SCHEMA_VERSION = 1
REQUIRED_PREDICTION_COLUMNS = frozenset({"date", "symbol", "model", "prediction"})

#: Cached because the parquet is 10 MB and the artifact is immutable.
_cache: dict[str, Any] = {}
_lock = threading.Lock()

#: Names per side of the long/short book, matching the backtest engine's
#: quintile construction on a 250-name universe.
DEFAULT_BOOK_SIZE = 50


class PortfolioUnavailable(RuntimeError):
    """A known operational condition that is safe to show as availability."""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        remedy: Optional[str] = None,
        **detail: Any,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.remedy = remedy
        self.safe_detail = detail

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": "unavailable",
            "reason": self.reason,
            # `detail` remains a sentence for existing UI callers. Structured
            # facts live alongside it and never include an absolute path.
            "detail": self.message,
            "message": self.message,
            "remedy": self.remedy,
        }
        body.update(self.safe_detail)
        return body


def _runtime_artifact(experiment_id: str, target: str, model_id: str) -> Path:
    return RUNTIME_ARTIFACTS / experiment_id / target / f"{model_id}.parquet"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_runtime_metadata(path: Path) -> None:
    metadata_path = path.with_suffix(".json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortfolioUnavailable(
            "ARTIFACT_METADATA_INVALID",
            "The deployed portfolio artifact has no readable provenance metadata.",
            remedy="Re-export the runtime portfolio artifact.",
            required_artifact=path.name,
        ) from exc

    if metadata.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        raise PortfolioUnavailable(
            "SCHEMA_MISMATCH",
            "The deployed portfolio artifact uses an unsupported schema version.",
            remedy="Re-export the runtime portfolio artifact with this release.",
            required_artifact=path.name,
        )
    expected_hash = metadata.get("artifact_sha256")
    if not isinstance(expected_hash, str) or _sha256(path) != expected_hash:
        raise PortfolioUnavailable(
            "ARTIFACT_INTEGRITY_FAILED",
            "The deployed portfolio artifact does not match its recorded content hash.",
            remedy="Replace it with a verified runtime export.",
            required_artifact=path.name,
        )


def _predictions(
    experiment_id: str,
    target: str,
    model_id: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    runtime = _runtime_artifact(experiment_id, target, model_id) if model_id else None
    legacy = EXPERIMENTS / experiment_id / f"predictions_{target}.parquet"
    path = runtime if runtime is not None and runtime.exists() else legacy
    if not path.exists():
        return None

    if runtime is not None and path == runtime:
        _validate_runtime_metadata(path)

    key = f"{path}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    try:
        frame = pd.read_parquet(path)
    except (ImportError, OSError, ValueError) as exc:
        logger.warning("portfolio artifact unreadable: %s", type(exc).__name__)
        raise PortfolioUnavailable(
            "ARTIFACT_UNREADABLE",
            "The deployed portfolio artifact could not be read by this runtime.",
            remedy="Re-export the artifact and verify the Parquet runtime dependency.",
            required_artifact=path.name,
        ) from exc

    missing = REQUIRED_PREDICTION_COLUMNS.difference(frame.columns)
    if missing:
        raise PortfolioUnavailable(
            "SCHEMA_MISMATCH",
            "The deployed portfolio artifact does not match the required prediction schema.",
            remedy="Re-export the runtime portfolio artifact with this release.",
            required_artifact=path.name,
            missing_columns=sorted(missing),
        )
    if target not in frame.columns:
        raise PortfolioUnavailable(
            "TARGET_MISSING",
            "The deployed portfolio artifact does not contain the requested target.",
            remedy="Select a deployed target or export its runtime artifact.",
            required_artifact=path.name,
            target=target,
        )
    with _lock:
        _cache.clear()
        _cache[key] = frame
    return frame


def _panel(experiment_id: str, target: str, model_id: str) -> Optional[pd.DataFrame]:
    """A date x symbol matrix of realised forward ranks, for covariance.

    The target is a cross-sectional rank, so this is a co-movement matrix of
    *rank* outcomes, not of returns. Every downstream number inherits those
    units and the payload says so — a "volatility" computed here is rank
    dispersion, not annualised return volatility.
    """
    frame = _predictions(experiment_id, target, model_id)
    if frame is None:
        return None
    block = frame[frame["model"] == model_id]
    if block.empty:
        return None
    wide = block.pivot_table(index="date", columns="symbol", values=target, aggfunc="first")
    return wide.dropna(axis=1, thresh=max(20, int(len(wide) * 0.5)))


def panel_and_weights(
    experiment_id: str = "EXP-006",
    model_id: str = "gradient_boosting",
    *,
    target: str = "fwd_rank_21",
) -> Optional[tuple[pd.DataFrame, pd.Series]]:
    """The return panel and weights a built book rests on.

    Exposed so the covariance comparison can estimate several matrices from the
    same inputs the book itself used. It calls `build` rather than repeating its
    selection logic: a second copy of "which names are in the book" would drift
    from the first, and then the comparison would be describing a different book
    than the one on screen.
    """
    panel, _ = panel_and_weights_detailed(experiment_id, model_id, target=target)
    return panel


#: Minimum overlapping names before a covariance matrix is worth estimating.
#: Below this the sample covariance is badly conditioned and the estimators
#: disagree for arithmetic reasons rather than financial ones.
MIN_COVARIANCE_NAMES = 10


def panel_and_weights_detailed(
    experiment_id: str = "EXP-006",
    model_id: str = "gradient_boosting",
    *,
    target: str = "fwd_rank_21",
) -> tuple[Optional[tuple[pd.DataFrame, pd.Series]], Optional[str]]:
    """The panel and weights, or `(None, reason)` saying which step failed.

    Six different situations used to collapse into one bare `None`: no book,
    an empty weight vector, a missing panel, an empty panel, too few
    overlapping names, and a book that failed to build at all. The caller
    could then only say "unavailable", which is the least useful true thing
    it could tell a reader.
    """
    book = build(experiment_id, model_id, target=target)
    if book.get("status") != "ok":
        # The common one on a deployment: the predictions artifact is
        # gitignored as regenerable, so the book cannot be built there.
        return None, "NO_BOOK"

    weights = pd.Series(
        {row["symbol"]: float(row["weight"]) for row in book.get("weights", [])},
        dtype=float,
    )
    if weights.empty:
        return None, "NO_POSITIONS"

    panel = _panel(experiment_id, target, model_id)
    if panel is None:
        return None, "NO_PANEL"
    if panel.empty:
        return None, "INSUFFICIENT_HISTORY"

    usable = [s for s in weights.index if s in panel.columns]
    if len(usable) < MIN_COVARIANCE_NAMES:
        return None, "INSUFFICIENT_POSITIONS"

    return (panel[usable], weights.reindex(usable)), None


def build(
    experiment_id: str = "EXP-006",
    model_id: str = "gradient_boosting",
    *,
    target: str = "fwd_rank_21",
    method: str = "risk_parity",
    long_only: bool = False,
    max_weight: float = 0.05,
    max_turnover: Optional[float] = None,
    book_size: int = DEFAULT_BOOK_SIZE,
) -> dict[str, Any]:
    """Construct a book from the most recent predictions and measure it."""
    required_name = f"{model_id}.parquet"
    try:
        frame = _predictions(experiment_id, target, model_id)
    except PortfolioUnavailable as exc:
        return exc.payload()
    if frame is None:
        return PortfolioUnavailable(
            "ARTIFACT_NOT_DEPLOYED",
            "The compact portfolio runtime artifact is not deployed for this experiment and model.",
            remedy="Export and deploy the versioned runtime portfolio artifact.",
            required_artifact=required_name,
            experiment_id=experiment_id,
            model_id=model_id,
            target=target,
        ).payload()

    block = frame[frame["model"] == model_id]
    if block.empty:
        return PortfolioUnavailable(
            "MODEL_MISSING",
            "The deployed portfolio artifact does not contain the requested model.",
            remedy="Select a deployed model or export its runtime artifact.",
            required_artifact=required_name,
            model_id=model_id,
        ).payload()

    as_of = block["date"].max()
    latest = block[block["date"] == as_of].dropna(subset=["prediction"])
    if len(latest) < book_size * 2:
        return PortfolioUnavailable(
            "INSUFFICIENT_NAMES",
            "The latest prediction cross-section is too small to build this book honestly.",
            names=int(len(latest)),
            required_names=int(book_size * 2),
            as_of=str(as_of),
        ).payload()

    ranked = latest.sort_values("prediction")
    shorts = ranked.head(book_size)["symbol"].tolist()
    longs = ranked.tail(book_size)["symbol"].tolist()
    selected = longs if long_only else longs + shorts

    try:
        panel = _panel(experiment_id, target, model_id)
    except PortfolioUnavailable as exc:
        return exc.payload()
    if panel is None or panel.empty:
        return PortfolioUnavailable(
            "COVARIANCE_UNAVAILABLE",
            "The deployed artifact cannot supply a covariance history for this model.",
        ).payload()
    usable = [s for s in selected if s in panel.columns]
    if len(usable) < 10:
        return PortfolioUnavailable(
            "COVARIANCE_UNAVAILABLE",
            "Too few selected names have enough overlapping history for covariance.",
            names=int(len(usable)),
            required_names=10,
        ).payload()
    sub = panel[usable]

    # These imports are needed only when a deployable artifact exists. Keeping
    # them after the availability checks lets a tracked-files-only deployment
    # answer ARTIFACT_NOT_DEPLOYED even if an optional numerical dependency is
    # broken, while requirements.txt still installs SciPy for a working book.
    try:
        from src.quant.backtest.costs import SimpleCostModel
        from src.quant.portfolio.optimizer import Constraints, apply_constraints, optimize
        from src.quant.risk import engine as risk
    except ModuleNotFoundError as exc:
        if exc.name == "scipy" or (exc.name or "").startswith("scipy."):
            logger.error("portfolio runtime dependency missing: scipy")
            return PortfolioUnavailable(
                "RUNTIME_DEPENDENCY_MISSING",
                "The portfolio numerical runtime is not installed on this deployment.",
                remedy="Install the pinned runtime dependencies and redeploy.",
            ).payload()
        raise

    # A signal-tilted book: the optimiser sizes risk, the sign comes from the
    # model's own ranking. Sign and size are separate decisions, deliberately.
    expected = ranked.set_index("symbol")["prediction"].reindex(usable)

    constraints = Constraints(
        long_only=long_only,
        max_weight=max_weight,
        max_turnover=max_turnover,
        net_target=None if long_only else 0.0,
    )
    try:
        allocation = optimize(
            method,
            returns=sub,
            expected=expected,
            constraints=constraints,
        )
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.info("portfolio allocation unavailable: %s", type(exc).__name__)
        return PortfolioUnavailable(
            "ALLOCATOR_INFEASIBLE",
            "The selected allocator could not produce a valid book from this covariance input.",
            method=method,
        ).payload()
    if not long_only and method != "mean_variance":
        # Apply the model's direction to a risk-sized book, then re-neutralise.
        sign = pd.Series(
            [1.0 if s in longs else -1.0 for s in allocation.weights.index],
            index=allocation.weights.index,
        )
        tilted = allocation.weights.abs() * sign
        gross = float(tilted.abs().sum())
        if gross > 0:
            tilted = tilted / gross
            tilted = tilted - tilted.sum() / len(tilted)
            # Sign-tilting happens after the allocator's own constraint pass.
            # Re-run the same contract over the actual returned book; otherwise
            # neutralising can lift a name through the cap while the payload
            # still claims the pre-tilt allocation was feasible.
            tilted, violations, notes = apply_constraints(tilted, constraints)
            allocation.weights = tilted
            allocation.violations = violations
            allocation.feasible = not violations
            allocation.notes.extend(notes)

    if not allocation.feasible:
        return PortfolioUnavailable(
            "ALLOCATOR_INFEASIBLE",
            "The selected allocator could not satisfy the requested portfolio constraints.",
            method=method,
            violations=list(allocation.violations),
        ).payload()

    weights = allocation.weights
    cov = risk.covariance_matrix(sub)
    # An invalid covariance is reported as such rather than allowed to render as
    # a book with no risk. Every `risk_share` below already falls back to None
    # when a symbol is absent, so an empty table degrades to "—" per position
    # instead of to a confident zero.
    try:
        contributions = risk.risk_contributions(weights, cov)
        contributions_note = None
    except risk.NotPositiveSemiDefinite as exc:
        contributions = pd.DataFrame(columns=["weight", "marginal", "component", "share"])
        contributions_note = str(exc)

    # Book-level outcome series, in RANK units.
    series = (sub[weights.index] * weights).sum(axis=1)
    # The book-level series is in RANK units, so metrics that presuppose returns
    # are refused rather than computed under a name that would misdescribe them.
    # compound=False for the same reason: compounding a rank once produced a
    # +6,553% "equity curve".
    report = risk.analyse(
        series, weights=weights, panel=sub, compound=False,
        series_unit=risk.SeriesUnit.RANK,
        # The series is one observation per rebalance date, not per session.
        frequency="rebalance period",
    )

    cost_model = SimpleCostModel(commission_bps=1.0, half_spread_bps=10.0, slippage_bps=2.0)
    illustrative_capital = 1_000_000.0
    breakdown = cost_model.charge(weights.abs(), capital=illustrative_capital)

    return {
        "status": "ok",
        "experiment_id": experiment_id,
        "model_id": model_id,
        "target": target,
        "as_of": str(as_of),
        "method": method,
        "allocation": allocation.as_dict(),
        "weights": [
            {
                "symbol": str(sym),
                # Enough precision that summing the serialised full book still
                # reproduces its gross/net constraints. Six decimals across
                # 100 names drifted the client-computed gross above 1.0.
                "weight": round(float(w), 8),
                "side": "long" if w > 0 else "short",
                "signal": round(float(expected.get(sym, np.nan)), 6)
                if pd.notna(expected.get(sym, np.nan)) else None,
                "risk_share": round(float(contributions.loc[sym, "share"]), 6)
                if sym in contributions.index else None,
            }
            # The allocation diagnostics describe the whole book. Truncating
            # this list to the 25 largest names made the client recompute a
            # different gross, net and position count from a partial book.
            for sym, w in weights.sort_values(key=abs, ascending=False).items()
        ],
        "risk": report.as_dict(),
        "risk_contributions_unavailable": contributions_note,
        "cost": {
            "breakdown": breakdown.as_dict(),
            "breakdown_units": {
                "traded_notional": "USD",
                "commission": "USD",
                "spread": "USD",
                "slippage": "USD",
                "impact": "USD",
                "total": "USD",
                "total_bps": "bps of traded notional",
            },
            # A return waterfall requires a return series. `series` above is a
            # cross-sectional rank, so subtracting dollar cost fractions from
            # its mean is dimensionally invalid. The costed walk-forward result
            # belongs to the Performance workspace; this book only estimates
            # the dollars required to enter the shown weights.
            "waterfall": {
                "status": "unavailable",
                "reason": (
                    "This illustrative book is measured on rank outcomes, not "
                    "returns; a gross-to-net P&L waterfall cannot be computed."
                ),
            },
            "assumptions": {
                "commission_bps": cost_model.commission_bps,
                "half_spread_bps": cost_model.half_spread_bps,
                "slippage_bps": cost_model.slippage_bps,
                "impact_coefficient": cost_model.impact_coefficient,
                "half_spread_source": "ASSUMED — the equity dataset carries no bid/ask",
                "capital_usd": illustrative_capital,
                "scope": "hypothetical one-time entry from cash into this illustrative book",
            },
        },
        "units": (
            f"{target} is a cross-sectional RANK in [-1, 1], not a return. Every "
            "risk figure here inherits rank units. Execution costs are a separate "
            "USD estimate for entering a $1,000,000 illustrative book; they are "
            "not subtracted from ranks and are not a P&L. The Sharpe and return "
            "figures that carry evidential weight come from the experiment's "
            "costed backtest."
        ),
        "disclaimer": (
            "An allocation built from a model whose net Sharpe is negative is an "
            "illustration of how that signal would be held, not a recommendation "
            "to hold it. Optimised weights allocate risk; they are not alpha."
        ),
    }


def methods() -> dict[str, Any]:
    """The allocators available, and what each assumes."""
    from src.quant.portfolio.optimizer import METHODS

    described = {
        "equal_weight": "No estimation, so no estimation error. The one to beat.",
        "inverse_volatility": "Sizes by 1/σ. Ignores correlation entirely.",
        "minimum_variance": "Analytic Σ⁻¹1. Unconstrained it will short.",
        "maximum_diversification": "Maximises Σwσ / √(wΣw).",
        "risk_parity": "Equal risk contribution by coordinate descent. Long-only by construction.",
        "mean_variance": "Σ⁻¹μ / λ. Consumes a supplied expected-return vector; does not create one.",
        "volatility_target": "Inverse-vol scaled to a target ex-ante volatility.",
        "min_cvar_heuristic": "Tail-weighted. NOT an LP-optimal CVaR solution — ignores tail dependence.",
    }
    return {
        "methods": [{"name": m, "description": described.get(m, "")} for m in METHODS],
        "note": (
            "Estimation and optimisation are separate objects here: the optimiser "
            "consumes covariance and expected-return estimates, it does not "
            "produce them."
        ),
    }
