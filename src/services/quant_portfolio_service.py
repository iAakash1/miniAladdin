"""
Portfolio construction and risk, computed for the UI.

## What this is for

`/quant` needs to show what the research signal would look like *as a book*:
weights, risk contributions, concentration, turnover and the cost waterfall that
turns a gross number negative. All of that is arithmetic on artifacts that
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

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.services.quant_portfolio")

EXPERIMENTS = Path("experiments")

#: Cached because the parquet is 10 MB and the artifact is immutable.
_cache: dict[str, Any] = {}
_lock = threading.Lock()

#: Names per side of the long/short book, matching the backtest engine's
#: quintile construction on a 250-name universe.
DEFAULT_BOOK_SIZE = 50


def _predictions(experiment_id: str, target: str) -> Optional[pd.DataFrame]:
    path = EXPERIMENTS / experiment_id / f"predictions_{target}.parquet"
    if not path.exists():
        return None
    key = f"{path}:{path.stat().st_mtime}"
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    frame = pd.read_parquet(path)
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
    frame = _predictions(experiment_id, target)
    if frame is None:
        return None
    block = frame[frame["model"] == model_id]
    if block.empty:
        return None
    wide = block.pivot_table(index="date", columns="symbol", values=target, aggfunc="first")
    return wide.dropna(axis=1, thresh=max(20, int(len(wide) * 0.5)))


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
    from src.quant.backtest.costs import SimpleCostModel, waterfall
    from src.quant.portfolio.optimizer import Constraints, optimize
    from src.quant.risk import engine as risk

    frame = _predictions(experiment_id, target)
    if frame is None:
        return {
            "status": "unavailable",
            "detail": f"no predictions artifact for {experiment_id}/{target}",
            "remedy": "Run the experiment, or select one that has completed.",
        }

    block = frame[frame["model"] == model_id]
    if block.empty:
        return {"status": "unavailable", "detail": f"no predictions for {model_id}"}

    as_of = block["date"].max()
    latest = block[block["date"] == as_of].dropna(subset=["prediction"])
    if len(latest) < book_size * 2:
        return {
            "status": "unavailable",
            "detail": f"only {len(latest)} names on {as_of}; need {book_size * 2}",
        }

    ranked = latest.sort_values("prediction")
    shorts = ranked.head(book_size)["symbol"].tolist()
    longs = ranked.tail(book_size)["symbol"].tolist()
    selected = longs if long_only else longs + shorts

    panel = _panel(experiment_id, target, model_id)
    if panel is None or panel.empty:
        return {"status": "unavailable", "detail": "could not build a covariance panel"}
    usable = [s for s in selected if s in panel.columns]
    if len(usable) < 10:
        return {
            "status": "unavailable",
            "detail": f"only {len(usable)} selected names have enough history for covariance",
        }
    sub = panel[usable]

    # A signal-tilted book: the optimiser sizes risk, the sign comes from the
    # model's own ranking. Sign and size are separate decisions, deliberately.
    expected = ranked.set_index("symbol")["prediction"].reindex(usable)

    allocation = optimize(
        method,
        returns=sub,
        expected=expected,
        constraints=Constraints(
            long_only=long_only,
            max_weight=max_weight,
            max_turnover=max_turnover,
            net_target=None if long_only else 0.0,
        ),
    )
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
            allocation.weights = tilted

    weights = allocation.weights
    cov = risk.covariance_matrix(sub)
    contributions = risk.risk_contributions(weights, cov)

    # Book-level outcome series, in RANK units.
    series = (sub[weights.index] * weights).sum(axis=1)
    report = risk.analyse(series, weights=weights, panel=sub, compound=False)

    cost_model = SimpleCostModel(commission_bps=1.0, half_spread_bps=10.0, slippage_bps=2.0)
    breakdown = cost_model.charge(weights.abs(), capital=1_000_000.0)
    gross_period = float(series.mean())
    flow = waterfall(gross_period, breakdown, capital=1_000_000.0)

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
                "weight": round(float(w), 6),
                "side": "long" if w > 0 else "short",
                "signal": round(float(expected.get(sym, np.nan)), 6)
                if pd.notna(expected.get(sym, np.nan)) else None,
                "risk_share": round(float(contributions.loc[sym, "share"]), 6)
                if sym in contributions.index else None,
            }
            for sym, w in weights.sort_values(key=abs, ascending=False).head(25).items()
        ],
        "risk": report.as_dict(),
        "cost": {
            "breakdown": breakdown.as_dict(),
            "waterfall": flow.as_dict(),
            "assumptions": {
                "commission_bps": cost_model.commission_bps,
                "half_spread_bps": cost_model.half_spread_bps,
                "slippage_bps": cost_model.slippage_bps,
                "impact_coefficient": cost_model.impact_coefficient,
                "half_spread_source": "ASSUMED — the equity dataset carries no bid/ask",
            },
        },
        "units": (
            f"{target} is a cross-sectional RANK in [-1, 1], not a return. Every "
            "risk and cost figure here is in rank units. They describe the shape "
            "of the book, not a P&L. The Sharpe and return figures that carry "
            "evidential weight come from the experiment's costed backtest."
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
