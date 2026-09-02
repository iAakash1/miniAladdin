"""
Cost-aware cross-sectional backtest — from out-of-sample predictions to money.

## Why a backtest is needed at all when the IC is already known

An information coefficient says the ordering carries information. It does not
say the information survives being traded. A signal with an IC of 0.03 that
completely reshuffles its portfolio every week can easily lose money after
costs, while an IC of 0.02 with a third of the turnover makes it. The two are
indistinguishable at the metric layer and obvious here.

So this consumes only **out-of-sample predictions from the walk-forward
driver**. There is no path in this module that can see a fitted model or an
in-sample prediction, which is what makes the equity curve mean something.

## The construction, and where each choice binds

At each rebalance date, names are ranked by prediction and the extreme
quantiles are held: long the top, short the bottom in a market-neutral book, or
long the top alone in a long-only one. Equal-weighted within each leg.

**Equal weight, not prediction-weighted.** Prediction magnitude at this
signal-to-noise ratio is mostly noise, and weighting by it concentrates the
book in whichever names the model happened to be most extreme about. Equal
weight makes a weaker claim, which is the correct claim.

**Positions are formed from the prediction at date `t` and earn the return
from `t` to the next rebalance.** Never `t`'s own return. That single
off-by-one is the most common backtest error there is, and it manufactures
performance exactly proportional to how good the signal is.

**Trades are charged at the rebalance.** See `costs.py`.

## Terminology, held to the repository's standard

Nothing in this module produces a number called alpha. It produces gross and
net returns, and a return difference against a benchmark. Alpha requires a
factor model with an intercept and a standard error, which lives in
`attribution.py` and nowhere else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.backtest.costs import SimpleCostModel

logger = logging.getLogger("omnisignal.quant.backtest.engine")

TRADING_DAYS = 252

#: A cross-section thinner than this cannot form two distinct quantile buckets
#: worth trading. Matches `src/research/portfolio.MIN_NAMES`.
MIN_NAMES = 10


@dataclass
class BacktestConfig:
    """Everything that decides what the backtest does."""

    quantiles: int = 5
    long_short: bool = True
    capital: float = 1_000_000.0
    rebalance_step_sessions: int = 5
    cost_model: SimpleCostModel = field(default_factory=SimpleCostModel)
    max_weight: float = 0.10
    min_names: int = MIN_NAMES

    #: Rebalance periods between observing a signal and acting on it.
    #:
    #: 0 means the position is formed at the close of the session the signal was
    #: computed from — the signal uses that close, and trades at it. That is the
    #: common convention and it is not achievable: the close is not knowable
    #: until the session ends, and an order placed on it is an order placed in
    #: the past.
    #:
    #: 1 means the signal from period `t` is acted on in period `t + 1`. At the
    #: default 5-session stride that is a full trading week of delay, which is
    #: *more* conservative than reality (a close-to-next-open fill is one
    #: session), and deliberately so: it is the pessimistic bound, and a signal
    #: that survives it survives any realistic fill.
    #:
    #: Both are reported. `docs/HOLDOUT_CONTRACT.md` pre-registers 1 as the
    #: primary and 0 as a diagnostic, so the more flattering number can never be
    #: the one chosen after the fact.
    execution_lag_periods: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "quantiles": self.quantiles,
            "long_short": self.long_short,
            "capital": self.capital,
            "rebalance_step_sessions": self.rebalance_step_sessions,
            "max_weight": self.max_weight,
            "min_names": self.min_names,
            "execution_lag_periods": self.execution_lag_periods,
            "execution_lag_note": (
                "0 = trade at the close the signal was computed from (not achievable); "
                "1 = act one full rebalance period later (pessimistic bound)."
            ),
            "costs": self.cost_model.assumptions(),
        }


@dataclass
class BacktestResult:
    """Period returns, costs, and the metrics computed from them."""

    periods: pd.DataFrame
    metrics: dict[str, Any]
    config: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def net_returns(self) -> pd.Series:
        return self.periods.set_index("date")["net_return"]

    def as_dict(self, *, include_periods: bool = False) -> dict[str, Any]:
        payload = {
            "metrics": dict(self.metrics),
            "config": dict(self.config),
            "warnings": list(self.warnings),
            "periods": len(self.periods),
        }
        if include_periods:
            payload["period_rows"] = self.periods.to_dict(orient="records")
        return payload


def run_backtest(
    predictions: pd.DataFrame,
    returns_panel: pd.DataFrame,
    *,
    config: Optional[BacktestConfig] = None,
    prediction_column: str = "prediction",
    date_column: str = "date",
    symbol_column: str = "symbol",
    forward_return_column: Optional[str] = None,
) -> BacktestResult:
    """Trade out-of-sample predictions and report gross and net performance.

    `returns_panel` supplies the realised **forward** return each position
    earns, and `dollar_volume` when impact costs are wanted. The forward return
    must already be the return from the rebalance date to the next one — it is
    read, never derived here, so the horizon cannot silently disagree with the
    rebalance frequency.
    """
    config = config or BacktestConfig()
    forward_column = forward_return_column or f"fwd_ret_{config.rebalance_step_sessions}"

    if forward_column not in returns_panel.columns:
        raise ValueError(
            f"returns_panel has no column {forward_column!r}. The backtest reads the "
            "realised forward return matching its rebalance frequency rather than "
            "deriving one, so that horizon and rebalance cannot disagree silently."
        )

    merge_columns = [date_column, symbol_column, forward_column]
    if "dollar_volume" in returns_panel.columns:
        merge_columns.append("dollar_volume")

    predictions = _apply_execution_lag(
        predictions, config.execution_lag_periods,
        prediction_column=prediction_column,
        date_column=date_column, symbol_column=symbol_column,
    )
    frame = predictions.merge(
        returns_panel[merge_columns], on=[date_column, symbol_column], how="inner"
    )
    if frame.empty:
        raise ValueError("no rows survived the join between predictions and returns")

    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    previous_weights = pd.Series(dtype=float)
    thin_dates = 0

    for day, group in frame.groupby(date_column, sort=True):
        usable = group.dropna(subset=[prediction_column, forward_column])
        if len(usable) < config.min_names:
            thin_dates += 1
            continue

        weights = _quantile_weights(
            usable.set_index(symbol_column)[prediction_column],
            quantiles=config.quantiles,
            long_short=config.long_short,
            max_weight=config.max_weight,
        )
        if weights is None:
            thin_dates += 1
            continue

        forward = usable.set_index(symbol_column)[forward_column].reindex(weights.index)
        gross = float((weights * forward.fillna(0.0)).sum())

        # Weight change against the previous rebalance, over the union of both
        # name sets — a name dropped entirely is a full exit and is charged.
        union = weights.index.union(previous_weights.index)
        delta = weights.reindex(union).fillna(0.0) - previous_weights.reindex(union).fillna(0.0)
        volumes = (
            usable.set_index(symbol_column)["dollar_volume"].reindex(union)
            if "dollar_volume" in usable.columns
            else None
        )
        cost = config.cost_model.charge(delta, capital=config.capital, dollar_volume=volumes)
        cost_fraction = cost.total / config.capital

        rows.append(
            {
                "date": day,
                "names": int(len(weights)),
                "long_names": int((weights > 0).sum()),
                "short_names": int((weights < 0).sum()),
                "gross_return": gross,
                "cost_return": cost_fraction,
                "net_return": gross - cost_fraction,
                # One-way, and named so at every aggregate below. The cost model
                # charges the ROUND-TRIP notional, so these two differ by exactly
                # 2x and reporting only one of them makes the cost unreconcilable.
                "turnover": float(delta.abs().sum()) / 2.0,
                "turnover_round_trip": float(delta.abs().sum()),
                "gross_exposure": float(weights.abs().sum()),
                "net_exposure": float(weights.sum()),
                "commission": cost.commission,
                "spread": cost.spread,
                "impact": cost.impact,
            }
        )
        previous_weights = weights

    if not rows:
        raise ValueError(
            f"no rebalance date had {config.min_names} usable names — nothing to trade"
        )
    if thin_dates:
        warnings.append(
            f"{thin_dates} rebalance date(s) skipped for fewer than {config.min_names} names"
        )

    periods = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    metrics = performance_metrics(
        periods, periods_per_year=TRADING_DAYS / config.rebalance_step_sessions
    )
    logger.info(
        "backtest: %d periods, net CAGR %s, net Sharpe %s",
        len(periods), _fmt(metrics.get("net_cagr")), _fmt(metrics.get("net_sharpe")),
    )
    return BacktestResult(
        periods=periods, metrics=metrics, config=config.as_dict(), warnings=warnings
    )


def _apply_execution_lag(
    predictions: pd.DataFrame,
    periods: int,
    *,
    prediction_column: str,
    date_column: str,
    symbol_column: str,
) -> pd.DataFrame:
    """Carry each symbol's prediction forward by `periods` rebalance dates.

    The prediction attached to date `d` becomes the prediction that was made
    `periods` rebalances earlier, so the book acts on information it demonstrably
    already had. Shifting per symbol rather than globally matters: symbols enter
    and leave the universe, and a global shift would hand one name's signal to
    another.

    The first `periods` observations of each symbol have no prior signal and are
    dropped rather than filled — a forward-filled first signal would be an
    invented view.
    """
    if periods <= 0:
        return predictions

    frame = predictions.sort_values([symbol_column, date_column], kind="mergesort").copy()
    frame[prediction_column] = frame.groupby(symbol_column, sort=False)[
        prediction_column
    ].shift(periods)
    return frame.dropna(subset=[prediction_column]).reset_index(drop=True)


def _quantile_weights(
    predictions: pd.Series, *, quantiles: int, long_short: bool, max_weight: float
) -> Optional[pd.Series]:
    """Equal-weight the extreme quantiles of a cross-section."""
    values = pd.to_numeric(predictions, errors="coerce").dropna()
    if len(values) < quantiles * 2 or values.nunique() < quantiles:
        return None
    try:
        buckets = pd.qcut(values.rank(method="first"), quantiles, labels=False)
    except ValueError:
        return None

    top = values.index[buckets == quantiles - 1]
    bottom = values.index[buckets == 0]
    if len(top) == 0 or (long_short and len(bottom) == 0):
        return None

    weights = pd.Series(0.0, index=values.index, dtype=float)
    if long_short:
        # Gross exposure 1.0 split evenly between the legs: 0.5 long, 0.5 short,
        # so the book is dollar-neutral and its return is a spread rather than a
        # market exposure wearing a signal's name.
        weights[top] = 0.5 / len(top)
        weights[bottom] = -0.5 / len(bottom)
    else:
        weights[top] = 1.0 / len(top)

    over = weights.abs() > max_weight
    if over.any():
        weights[over] = np.sign(weights[over]) * max_weight
    return weights[weights != 0.0]


def performance_metrics(periods: pd.DataFrame, *, periods_per_year: float) -> dict[str, Any]:
    """Gross and net performance, with each ratio computed or reported absent.

    Nothing here is emitted unless it is correctly computable. A Sharpe ratio on
    eight observations is a number, not a statistic, so it is None below the
    minimum — the repository's standard is that a metric shown is a metric that
    means what its name says.
    """
    if periods.empty:
        return {}

    out: dict[str, Any] = {
        "periods": int(len(periods)),
        "periods_per_year": round(periods_per_year, 2),
        "start": str(periods["date"].min()),
        "end": str(periods["date"].max()),
    }
    for prefix in ("gross", "net"):
        returns = pd.to_numeric(periods[f"{prefix}_return"], errors="coerce").dropna()
        out.update({f"{prefix}_{k}": v for k, v in _series_metrics(returns, periods_per_year).items()})

    costs = pd.to_numeric(periods["cost_return"], errors="coerce")
    out["total_cost_return"] = float(costs.sum())
    out["mean_cost_bps_per_period"] = float(costs.mean() * 10000)
    out["mean_turnover"] = float(pd.to_numeric(periods["turnover"], errors="coerce").mean())
    out["annualised_turnover"] = float(out["mean_turnover"] * periods_per_year)
    # The same quantities on the basis the cost model actually charges. Declared
    # rather than left for the reader to infer: turnover x rate reproduces the
    # cost only on the round-trip figure.
    out["turnover_convention"] = "one-way (sum|delta_w| / 2)"
    out["mean_turnover_round_trip"] = 2.0 * out["mean_turnover"]
    out["annualised_turnover_round_trip"] = 2.0 * out["annualised_turnover"]
    out["cost_rate_bps_of_traded_notional"] = (
        float(costs.sum() / periods["turnover_round_trip"].sum() * 10000)
        if "turnover_round_trip" in periods
        and float(pd.to_numeric(periods["turnover_round_trip"], errors="coerce").sum()) > 0
        else None
    )
    out["mean_names"] = float(pd.to_numeric(periods["names"], errors="coerce").mean())
    out["mean_gross_exposure"] = float(
        pd.to_numeric(periods["gross_exposure"], errors="coerce").mean()
    )
    # Only defined when there IS gross profit to take a share of. The
    # denominator was previously an absolute value, which made a strategy that
    # lost 10% gross and paid 5% in costs report 0.50 — the same number as one
    # that turned +10% into +5%, and reading exactly like a healthy strategy
    # giving up half its edge. The ratio also improved as the strategy lost
    # more, and PRODUCTION_THRESHOLDS treats it as a maximum, so a gross-losing
    # candidate could clear a gate whose stated purpose is to catch strategies
    # that are really transaction-cost bets. Undefined is the honest answer;
    # `thresholds_not_met` counts a missing value as unmet, so this fails closed.
    gross_total = float(pd.to_numeric(periods["gross_return"], errors="coerce").sum())
    out["gross_total_return"] = gross_total
    out["cost_share_of_gross"] = (
        float(costs.sum() / gross_total) if gross_total > 1e-12 else None
    )
    return out


def _series_metrics(returns: pd.Series, periods_per_year: float) -> dict[str, Any]:
    """Risk and return statistics for one period-return series."""
    values = returns.to_numpy(dtype=float)
    if len(values) < 8:
        return {"periods": int(len(values)), "note": "fewer than 8 periods — no ratio reported"}

    equity = np.cumprod(1.0 + values)
    total = float(equity[-1] - 1.0)
    years = len(values) / periods_per_year
    cagr = float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 and equity[-1] > 0 else None

    mean, std = float(np.mean(values)), float(np.std(values, ddof=1))
    volatility = std * np.sqrt(periods_per_year)
    downside = values[values < 0]
    downside_deviation = (
        float(np.sqrt(np.mean(downside**2)) * np.sqrt(periods_per_year))
        if len(downside) >= 3
        else None
    )
    peak = np.maximum.accumulate(equity)
    drawdown = float(np.min(equity / peak - 1.0))

    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()

    return {
        "total_return": total,
        "cagr": cagr,
        "volatility": float(volatility),
        # Excess over cash is NOT deducted here: these are long/short spread
        # returns on a dollar-neutral book, which is already an excess return.
        # For a long-only run the Sharpe is therefore a raw-return Sharpe and
        # is labelled as such in the report.
        "sharpe": float(mean / std * np.sqrt(periods_per_year)) if std > 0 else None,
        "sortino": (
            float(mean * periods_per_year / downside_deviation)
            if downside_deviation and downside_deviation > 0
            else None
        ),
        "max_drawdown": drawdown,
        "calmar": float(cagr / abs(drawdown)) if cagr is not None and drawdown < -1e-9 else None,
        "hit_rate": float(np.mean(values > 0)),
        "profit_factor": float(gains / losses) if losses > 1e-12 else None,
        "best_period": float(np.max(values)),
        "worst_period": float(np.min(values)),
        "downside_deviation": downside_deviation,
    }


def _fmt(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.4f}"
