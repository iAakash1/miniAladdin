"""
Factor Lab — the service behind cross-sectional factor research.

Assembles three things the repository already had but never connected: the
point-in-time panel (what each factor was worth, and when it was knowable),
realised forward returns (what happened next), and the cross-sectional
estimators in `src/research/`.

## Why this is the panel's first real consumer

`docs/PANEL.md` justifies the wide layout by saying cross-sectional ranking
reads one factor column across every symbol on a date. Until this service,
nothing did that — every view in the product examined one ticker at a time,
which cannot distinguish a factor that works from a market that rose.

## Cost, and why it is cached hard

A cold build is dominated by fetching prices for the whole universe, not by
computation: ~30 provider calls through the bounded fan-out, then a
vectorized panel build at ~13,600 cells/s. Measured end to end at roughly
35-40 s cold for 30 names over 2.5 years, and milliseconds warm.

That asymmetry is why the TTL is long. Factor evidence over a multi-year
window does not change between two page loads; recomputing it per request
would spend a minute of vendor budget to produce an identical answer.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date as Date
from datetime import timedelta
from typing import Any, Optional

import pandas as pd

from src import providers
from src.observability import timer
from src.panel import PanelBuilder, Universe
from src.panel.factors import PRICE_FACTOR_COLUMNS
from src.panel.schema import FACTOR_COLUMNS
from src.providers.parallel import map_concurrent
from src.research import (
    analyse, analyse_redundancy, attribute, dispersion, evaluate_factor,
    forward_returns, rank_cross_section, screen, simulate,
)
from src.research.cross_section import MIN_NAMES_PER_DATE

logger = logging.getLogger("omnisignal.services.factor_lab")

#: Long on purpose — see the module docstring. Evidence over years does not
#: move between page loads.
CACHE_TTL_SECONDS = 3600.0

#: Weekly observation cadence. Daily would multiply vendor cost and panel
#: size ~5x while adding almost no independent information: a 21-day forward
#: return sampled daily overlaps 20/21, so the extra rows are nearly the same
#: observation repeated.
STEP_DAYS = 5

#: One trading month. Long enough for a factor to express itself, short
#: enough that ~2 years of vendor history yields a usable number of
#: non-overlapping windows.
DEFAULT_HORIZON = 21

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def available_universes() -> list[dict[str, Any]]:
    from src.panel.universe import available

    return [
        {"name": name, "symbols": len(Universe.named(name))}
        for name in available()
    ]


def run(
    universe_name: str = "mega30",
    years: float = 2.5,
    horizon: int = DEFAULT_HORIZON,
) -> dict[str, Any]:
    """Evaluate every price factor across a universe. Never raises."""
    key = f"{universe_name}:{years}:{horizon}"
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return {**entry[1], "cached": True}

    try:
        payload = _build(universe_name, years, horizon)
    except KeyError as exc:
        return {"error": f"unknown universe: {exc}", "universes": available_universes()}
    except Exception:  # noqa: BLE001 — a research view must not 500 the app
        logger.exception("factor lab failed for %s", universe_name)
        return {"error": "factor evaluation failed; see server logs"}

    with _lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, payload)
    return payload


def _build(universe_name: str, years: float, horizon: int) -> dict[str, Any]:
    started = time.perf_counter()
    universe = Universe.named(universe_name)
    end = Date.today()
    start = end - timedelta(days=int(years * 365))

    with timer("factor_lab.panel_build", universe=universe_name):
        panel, manifest = PanelBuilder().build(universe, start, end, step=STEP_DAYS)
    if panel.empty:
        return {"error": "no panel data could be built for this universe"}

    with timer("factor_lab.prices", universe=universe_name):
        prices = _load_prices(list(universe.symbols))

    dates = sorted(panel["date"].unique())
    outcomes = forward_returns(prices, dates, horizon)
    if outcomes.empty:
        return {"error": "no realised forward returns available yet"}

    # Two joins, deliberately different.
    #
    # `evaluable` is an INNER join: measuring a factor requires knowing what
    # happened next, so dates whose forward window has not closed cannot
    # contribute to an IC.
    #
    # `rankable` is a LEFT join: the engine's ranking *today* is knowable
    # today, and it is the most useful row on the page. Showing only dates
    # with realised outcomes would hide the current cross-section — which is
    # exactly what an inner join did in the first version of this service.
    evaluable = panel.merge(outcomes, on=["symbol", "date"], how="inner")
    rankable = panel.merge(outcomes, on=["symbol", "date"], how="left")

    # Portfolio simulation uses the *holding-period* return, not the
    # evaluation horizon. Holding for exactly one rebalance interval makes
    # consecutive periods non-overlapping, so the Sharpe ratio needs no
    # autocorrelation correction — the overlap is designed out rather than
    # corrected for.
    periods = forward_returns(prices, dates, STEP_DAYS).rename(
        columns={"forward_return": "period_return"}
    )
    tradeable = panel.merge(periods, on=["symbol", "date"], how="inner")

    # Evaluate whatever the panel actually populated, not a hardcoded sleeve.
    # SEC-derived fundamentals appear here automatically once the builder
    # fills them, which is what lets a new factor be judged by the same bar
    # as every existing one rather than being introduced by assertion.
    populated = tuple(
        name for name in FACTOR_COLUMNS
        if name in evaluable.columns and evaluable[name].notna().any()
    )

    with timer("factor_lab.evaluate", universe=universe_name):
        factors = [
            _serialise(evaluation)
            for name in populated
            if (evaluation := evaluate_factor(
                evaluable, name, horizon, STEP_DAYS
            )) is not None
        ]
    with timer("factor_lab.portfolios", universe=universe_name):
        portfolios = {
            name: _serialise_portfolio(result)
            for name in populated
            if (result := simulate(tradeable, name)) is not None
        }
    for row in factors:
        row["portfolio"] = portfolios.get(row["factor"])
        row["stability"] = _serialise_stability(
            analyse(row["factor"], [(d, v) for d, v in row["ic_series"]])
        )

    factors.sort(key=lambda row: -abs(row["t_stat"]))

    if not factors:
        return {
            "error": (
                f"{universe_name} has {len(universe)} symbols; cross-sectional "
                f"evaluation needs at least {MIN_NAMES_PER_DATE} names on a date. "
                "A rank correlation over five names is noise, not a ranking — so "
                "this reports nothing rather than a number that would look real."
            ),
            "universes": available_universes(),
        }

    latest = max(dates)
    return {
        "universe": {
            "name": universe_name,
            "symbols": list(universe.symbols),
            "point_in_time_membership": universe.point_in_time,
        },
        "window": {
            "start": str(start), "end": str(end),
            "observation_dates": len(dates),
            "evaluable_cells": len(evaluable),
            "step_days": STEP_DAYS,
            "horizon_days": horizon,
        },
        "factors": factors,
        "latest_cross_section": {
            "date": str(latest),
            "factors": {
                name: rank_cross_section(rankable, name, latest)
                for name in populated
            },
        },
        "screen": _screen_payload(rankable, latest, populated),
        "redundancy": _redundancy_payload(panel, populated),
        "attribution": _attribution_payload(evaluable, populated),
        "caveats": _caveats(len(factors), universe),
        "engine_version": manifest.engine_version,
        "build_seconds": round(time.perf_counter() - started, 2),
        "cached": False,
    }


def _serialise(evaluation) -> dict[str, Any]:
    return {
        "factor": evaluation.factor,
        "mean_ic": round(evaluation.mean_ic, 5),
        "std_ic": round(evaluation.std_ic, 4),
        "t_stat": round(evaluation.t_stat, 3),
        "naive_t_stat": round(evaluation.naive_t_stat, 3),
        "overlap_inflation": round(evaluation.inflation, 2),
        "newey_west_lags": evaluation.newey_west_lags,
        "hit_rate": round(evaluation.hit_rate, 3),
        "dates": evaluation.dates,
        "names_median": evaluation.names_median,
        "top_minus_bottom": (
            round(evaluation.top_minus_bottom, 5)
            if evaluation.top_minus_bottom is not None else None
        ),
        "quantiles": evaluation.quantiles,
        "saturation": round(evaluation.saturation, 4),
        "significant": evaluation.significant,
        "assessment": evaluation.assessment,
        "ic_series": evaluation.ic_series,
    }


def _serialise_stability(stability) -> dict[str, Any]:
    return {
        "window": stability.window,
        "rolling": stability.rolling,
        "first_half_ic": (
            round(stability.first_half_ic, 5)
            if stability.first_half_ic is not None else None
        ),
        "second_half_ic": (
            round(stability.second_half_ic, 5)
            if stability.second_half_ic is not None else None
        ),
        "best_window": stability.best_window,
        "worst_window": stability.worst_window,
        "concentration": round(stability.concentration, 3),
        "sign_flips": stability.sign_flips,
        "decayed": stability.decayed,
        "assessment": stability.assessment,
    }


def _attribution_payload(
    evaluable: pd.DataFrame, factors: tuple[str, ...]
) -> Optional[dict[str, Any]]:
    """How much of the cross-section the factors actually explain."""
    result = attribute(evaluable, factors)
    if result is None:
        return None
    return {
        "factors": result.factors,
        "factor_returns": {k: round(v, 6) for k, v in result.factor_returns.items()},
        "t_stats": {k: round(v, 3) for k, v in result.t_stats.items()},
        "mean_r_squared": round(result.mean_r_squared, 4),
        "mean_adjusted_r_squared": round(result.mean_adjusted_r_squared, 4),
        "overfit_gap": round(result.overfit_gap, 4),
        "names_median": result.names_median,
        "unexplained_share": round(result.unexplained_share, 4),
        "dates": result.dates,
        "assessment": result.assessment,
    }


def _redundancy_payload(
    panel: pd.DataFrame, factors: tuple[str, ...]
) -> Optional[dict[str, Any]]:
    """How many independent signals the seven factors actually represent."""
    result = analyse_redundancy(panel, factors)
    if result is None:
        return None
    return {
        "factors": result.factors,
        "matrix": result.matrix,
        "effective_factors": result.effective_factors,
        "redundant_pairs": [
            {"a": a, "b": b, "correlation": c} for a, b, c in result.redundant_pairs
        ],
        "dates": result.dates,
        "assessment": result.assessment,
    }


def _screen_payload(
    rankable: pd.DataFrame, latest: Date, factors: tuple[str, ...]
) -> dict[str, Any]:
    """The composite cross-section: every name ranked, with factor agreement."""
    rows = screen(rankable, factors, latest)
    return {
        "date": str(latest),
        "dispersion": dispersion(rows),
        "rows": [
            {
                "rank": row.rank,
                "symbol": row.symbol,
                "composite": round(row.composite, 1),
                "agreement": round(row.agreement, 3),
                "conviction": row.conviction,
                "factors_used": row.factors_used,
                "percentiles": row.percentiles,
                "strongest": row.strongest,
                "weakest": row.weakest,
            }
            for row in rows
        ],
    }


def _serialise_portfolio(result) -> dict[str, Any]:
    return {
        "buckets": result.buckets,
        "rebalances": result.rebalances,
        "total_return": round(result.total_return, 5),
        "annualised_return": round(result.annualised_return, 5),
        "annualised_volatility": round(result.annualised_volatility, 5),
        "sharpe": round(result.sharpe, 3),
        "max_drawdown": round(result.max_drawdown, 5),
        "hit_rate": round(result.hit_rate, 3),
        "turnover": round(result.turnover, 4),
        "long_leg_return": round(result.long_leg_return, 5),
        "short_leg_return": round(result.short_leg_return, 5),
        "benchmark_return": round(result.benchmark_return, 5),
        "beat_benchmark": result.beat_benchmark,
        "assessment": result.assessment,
        "equity_curve": result.equity_curve,
    }


def _caveats(factor_count: int, universe: Universe) -> list[str]:
    """Stated with the results, not buried in a footnote.

    A research tool that reports statistics without their limitations is
    presenting decoration. Each of these materially changes how the numbers
    above should be read.
    """
    family_wise = 1 - 0.95 ** max(factor_count, 1)
    return [
        f"Multiple comparisons: {factor_count} factors were tested. Even if none "
        f"had predictive power, the chance at least one appears significant at "
        f"the 5% level is about {family_wise:.0%}. Judge the set, not the best member.",
        "Overlapping windows: forward returns overlap between observation dates, "
        "so t-statistics are Newey-West corrected. The uncorrected values are shown "
        "alongside — the gap between them is how much the naive statistic overstates.",
        "Survivorship bias: universe membership is current, not historical, so every "
        "name in it survived to today. This inflates results in an unknown direction "
        "and is not correctable without point-in-time index membership."
        if not universe.point_in_time else
        "Universe membership is point-in-time.",
        "Factor coverage: every factor the panel populated is evaluated here. "
        "Price factors come from OHLCV; fundamentals come from SEC XBRL with each "
        "figure dated by its filing, so a restatement becomes visible exactly when "
        "it was published. Sleeves with no point-in-time source are absent rather "
        "than approximated.",
        "Trading costs are not modelled. Turnover is reported per factor so a "
        "cost assumption can be applied by the reader rather than inherited from "
        "one invented here — at 40% weekly turnover, realistic costs can exceed "
        "the entire simulated edge.",
        "Factor redundancy: the screen weights every factor equally, but the "
        "correlation matrix shows how many independent signals those factors "
        "actually represent. Where that number is well below the factor count, "
        "equal weighting silently over-votes whichever family is duplicated.",
        "The screen weights every factor equally. Weighting by measured IC would "
        "fit weights to noise, since none of these factors is statistically "
        "significant on this sample — so the composite makes a deliberately weak "
        "claim, and the agreement column carries more information than the rank.",
        "Sample size: roughly two years of free-tier vendor history. Factor evidence "
        "at this length is suggestive at best; treat a single significant result as a "
        "hypothesis, not a finding.",
    ]


def _load_prices(symbols: list[str]) -> dict[str, pd.Series]:
    """Close series per symbol, fanned out through the bounded pool."""
    def load(symbol: str) -> tuple[str, Optional[pd.Series]]:
        result = providers.market_data.get_series(symbol, "5y")
        if not result.ok or not result.data.bars:
            return symbol, None
        series = pd.Series(
            {pd.Timestamp(bar.date): bar.close for bar in result.data.bars}
        ).sort_index()
        return symbol, series

    outcomes = map_concurrent(load, symbols, label="factor-lab-prices")
    return {
        symbol: series
        for symbol, series in (outcome.value for outcome in outcomes if outcome.ok)
        if series is not None and not series.empty
    }


def reset_for_tests() -> None:
    with _lock:
        _cache.clear()
