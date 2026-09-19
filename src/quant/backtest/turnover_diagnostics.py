"""
Where does the turnover come from? — a decomposition of the baseline book.

EXP-006's gradient-boosting book turns over 20.15x a year (one-way). That figure
is a scalar, and a scalar cannot say *why*. Turnover has several distinct
sources and they call for different remedies:

* **full reversal** — a name jumps from one extreme quintile to the opposite
  one. Only a better signal removes this;
* **drift** — a name slides two or three quintiles. A real change of view;
* **boundary churn** — a name that was just inside the cutoff is just outside
  it. Its expected return has barely moved, but a hard cutoff sells it anyway,
  and the mirror image (a name just outside steps just inside) buys another.
  This is the source a buffer can remove without discarding information;
* **universe exit / missing observation** — a name leaves the eligible set
  (monthly reconstitution) or has no prediction at a date. These exits are
  forced; no portfolio rule can avoid them;
* **re-weighting** — retained names change weight only because the leg's
  size moved (0.5 / n).

Everything here is computed from predictions and the held sets. **No forward
return is read**, so this analysis cannot be tuned on outcomes; the only
outcome-dependent quantities (gross Sharpe, net Sharpe, cost share) are taken
from the same backtest engine that produced EXP-006.

The weight construction is re-derived here with plain rank arithmetic (not
`pd.qcut`), and `independent_turnover` must agree with the engine's own
turnover to floating-point precision. Two implementations agreeing is the
verification that "20.15x" is a property of the predictions and the rule, not
of one code path.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.backtest.engine import _apply_execution_lag

QUINTILES = 5

#: Categories, most information-destroying first. Names are used verbatim in the
#: report so a reader can grep for them.
EXIT_CATEGORIES = (
    "full_reversal",
    "deep_drift",
    "mid_drift",
    "adjacent_band",
    "universe_exit",
    "missing_observation",
    "no_price_row",
)


def lagged_frame(
    predictions: pd.DataFrame,
    returns_panel: pd.DataFrame,
    *,
    lag: int = 1,
    forward_column: str = "fwd_ret_5",
) -> pd.DataFrame:
    """Predictions after the engine's execution lag, joined to the returns panel.

    The join and lag are the engine's (`_apply_execution_lag`, inner merge) so
    the rows analysed here are exactly the rows the backtest traded.
    """
    shifted = _apply_execution_lag(
        predictions, lag, prediction_column="prediction", date_column="date", symbol_column="symbol"
    )
    columns = ["date", "symbol", forward_column]
    if "dollar_volume" in returns_panel.columns:
        columns.append("dollar_volume")
    return shifted.merge(returns_panel[columns], on=["date", "symbol"], how="inner")


def _usable(frame: pd.DataFrame, forward_column: str, min_names: int = 10):
    """Yield (date, cross-section) exactly as the engine's loop admits them."""
    for day, group in frame.groupby("date", sort=True):
        usable = group.dropna(subset=["prediction", forward_column])
        if len(usable) >= min_names:
            yield day, usable.set_index("symbol")


def _rank_sets(scores: pd.Series) -> tuple[pd.Series, set, set, pd.Series]:
    """Extreme-quintile membership exactly as the engine assigns it (`pd.qcut`).

    Returns (percentile, longs, shorts, bucket 0..4). The decomposition uses the
    engine's own bucket definition so that it decomposes the book the backtest
    actually traded, not a nearby one.
    """
    ranks = scores.rank(method="first")
    n = len(scores)
    bucket = pd.Series(pd.qcut(ranks, QUINTILES, labels=False), index=scores.index)
    percentile = (ranks - 1.0) / max(n - 1, 1)
    longs = set(bucket.index[bucket == QUINTILES - 1])
    shorts = set(bucket.index[bucket == 0])
    return percentile, longs, shorts, bucket


def _exact_rank_sets(scores: pd.Series) -> tuple[set, set]:
    """Membership from exact integer rank arithmetic, with no floating-point edges.

    Ranks are 1..N. The top quintile is `rank > 1 + 0.8 (N-1)` and the bottom
    `rank <= 1 + 0.2 (N-1)`; multiplying through by 5 keeps every comparison in
    integers, so no cutoff can be moved by rounding. `pd.qcut` interpolates the
    same quantiles in floating point, which can move a knife-edge rank across a
    cutoff when `0.8 (N-1)` is an integer — the two agree except there, and the
    difference is counted rather than hidden (see `independent_turnover`).
    """
    ranks = scores.rank(method="first").astype(int)
    n = len(scores)
    top = ranks.index[5 * ranks > 5 + 4 * (n - 1)]
    bottom = ranks.index[5 * ranks <= 5 + (n - 1)]
    return set(top), set(bottom)


#: The engine's per-name cap (`BacktestConfig.max_weight`). It binds only on a
#: thin cross-section: with 3 names per leg the equal weight is 0.167 and is cut
#: to 0.10, so gross exposure falls below 1 on that date. Omitting it makes this
#: independent derivation disagree with the engine on exactly those dates.
MAX_WEIGHT = 0.10


def _weights(longs: set, shorts: set) -> dict:
    out = {name: min(0.5 / len(longs), MAX_WEIGHT) for name in longs}
    out.update({name: -min(0.5 / len(shorts), MAX_WEIGHT) for name in shorts})
    return out


def independent_turnover(
    frame: pd.DataFrame, *, forward_column: str = "fwd_ret_5", periods_per_year: float = 50.4
) -> dict[str, Any]:
    """One-way turnover from first principles, without `pd.qcut`.

    It is an independent re-derivation of the baseline book (exact integer rank
    arithmetic, its own turnover loop), reported next to the engine's figure. The
    two can differ only where `pd.qcut`'s floating-point cutoff and the exact
    integer cutoff disagree about a knife-edge rank; `dates_with_different_book`
    counts those dates so the residual is a measured quantity.
    """
    previous: dict = {}
    one_way: list[float] = []
    differing = 0
    for _, cross in _usable(frame, forward_column):
        _, q_longs, q_shorts, _ = _rank_sets(cross["prediction"])
        longs, shorts = _exact_rank_sets(cross["prediction"])
        if not longs or not shorts:
            continue
        differing += int(longs != q_longs or shorts != q_shorts)
        current = _weights(longs, shorts)
        union = set(previous) | set(current)
        change = sum(abs(current.get(k, 0.0) - previous.get(k, 0.0)) for k in union)
        one_way.append(change / 2.0)
        previous = current
    mean = float(np.mean(one_way))
    return {
        "periods": len(one_way),
        "mean_one_way_turnover": mean,
        "annualised_one_way_turnover": mean * periods_per_year,
        "annualised_round_trip_turnover": 2.0 * mean * periods_per_year,
        "round_trip_turns_per_month": 2.0 * mean * periods_per_year / 12.0,
        "dates_with_different_book_than_qcut": differing,
        "first_period_included": True,
        "note": "the first period establishes the book from cash (one-way turnover 0.5) and is "
                "included, as in the engine's mean",
    }


def decompose_turnover(
    frame: pd.DataFrame,
    *,
    forward_column: str = "fwd_ret_5",
    universe_flag: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    """Split baseline one-way turnover by cause; report retention and rank stability.

    `universe_flag` is an optional frame `(date, symbol, in_universe)` used only
    to distinguish a universe exit from a missing observation for names that
    disappear from the traded cross-section.
    """
    in_universe = None
    if universe_flag is not None:
        in_universe = {
            (d, s): bool(v)
            for d, s, v in zip(universe_flag["date"], universe_flag["symbol"], universe_flag["in_universe"])
        }

    previous_cross: Optional[pd.Series] = None
    previous_pct: Optional[pd.Series] = None
    previous_bucket: Optional[pd.Series] = None
    previous_sets: Optional[tuple[set, set]] = None
    previous_w: dict = {}
    previous_day = None

    per_date: list[dict[str, Any]] = []
    exit_cutoff_distance: list[float] = []      # percentile points from the entry cutoff
    exit_weight_for_distance: list[float] = []
    rank_corr: list[float] = []
    abs_pct_move: list[float] = []
    pct_moves_all: list[np.ndarray] = []

    for day, cross in _usable(frame, forward_column):
        pct, longs, shorts, bucket = _rank_sets(cross["prediction"])
        if not longs or not shorts:
            continue
        current_w = _weights(longs, shorts)

        if previous_cross is not None:
            row: dict[str, Any] = {"date": day}
            row["exit_weight"] = {c: 0.0 for c in EXIT_CATEGORIES}
            row["entry_weight"] = {"new_to_cross_section": 0.0, "from_adjacent_band": 0.0,
                                   "from_mid": 0.0, "from_deep": 0.0, "from_opposite": 0.0}
            row["reweight"] = 0.0
            row["changed"] = {}

            for side, prev_set, cur_set in (
                ("long", previous_sets[0], longs),
                ("short", previous_sets[1], shorts),
            ):
                exits = prev_set - cur_set
                entries = cur_set - prev_set
                retained = prev_set & cur_set
                row["changed"][side] = len(exits) / len(prev_set)
                entry_bucket = 4 if side == "long" else 0
                cutoff = 0.8 if side == "long" else 0.2

                for name in exits:
                    weight = abs(previous_w[name])
                    if name not in cross.index:
                        flag = None if in_universe is None else in_universe.get((day, name))
                        if in_universe is None:
                            category = "universe_exit"
                        elif flag is None:
                            category = "no_price_row"
                        elif flag is False:
                            category = "universe_exit"
                        else:
                            category = "missing_observation"
                    else:
                        gap = abs(int(bucket[name]) - entry_bucket)
                        category = ("adjacent_band", "mid_drift", "deep_drift", "full_reversal")[gap - 1]
                        exit_cutoff_distance.append(abs(float(pct[name]) - cutoff) * 100.0)
                        exit_weight_for_distance.append(weight)
                    row["exit_weight"][category] += weight

                for name in entries:
                    weight = abs(current_w[name])
                    if name not in previous_cross.index:
                        key = "new_to_cross_section"
                    else:
                        gap = abs(int(previous_bucket[name]) - entry_bucket)
                        key = ("from_adjacent_band", "from_mid", "from_deep", "from_opposite")[gap - 1]
                    row["entry_weight"][key] += weight

                for name in retained:
                    row["reweight"] += abs(current_w[name] - previous_w[name])

            total = (sum(row["exit_weight"].values()) + sum(row["entry_weight"].values())
                     + row["reweight"])
            row["one_way_turnover"] = total / 2.0
            per_date.append(row)

            common = cross.index.intersection(previous_pct.index)
            if len(common) >= 10:
                rank_corr.append(float(np.corrcoef(
                    previous_pct.reindex(common).rank(), pct.reindex(common).rank())[0, 1]))
                moves = (pct.reindex(common) - previous_pct.reindex(common)).to_numpy()
                pct_moves_all.append(moves)
                abs_pct_move.append(float(np.mean(np.abs(moves))))

        previous_cross = cross["prediction"]
        previous_pct = pct
        previous_bucket = bucket
        previous_sets = (longs, shorts)
        previous_w = current_w
        previous_day = day

    if not per_date:
        raise ValueError("no consecutive tradable dates to decompose")

    turnover = np.array([r["one_way_turnover"] for r in per_date])
    total = float(turnover.sum())

    def share(numerators: list[float]) -> float:
        return float(np.sum(numerators) / 2.0 / total) if total else float("nan")

    exit_share = {
        c: share([r["exit_weight"][c] for r in per_date]) for c in EXIT_CATEGORIES
    }
    entry_share = {
        k: share([r["entry_weight"][k] for r in per_date])
        for k in per_date[0]["entry_weight"]
    }
    reweight_share = share([r["reweight"] for r in per_date])

    distances = np.asarray(exit_cutoff_distance)
    weights = np.asarray(exit_weight_for_distance)

    def within(points: float) -> float:
        return float(weights[distances <= points].sum() / weights.sum()) if weights.sum() > 0 else float("nan")

    all_moves = np.concatenate(pct_moves_all)
    changed_long = float(np.mean([r["changed"]["long"] for r in per_date]))
    changed_short = float(np.mean([r["changed"]["short"] for r in per_date]))

    return {
        "periods": len(per_date),
        "mean_one_way_turnover": float(turnover.mean()),
        "share_of_turnover": {
            "exits": exit_share,
            "entries": entry_share,
            "reweighting_of_retained": reweight_share,
            "check_sums_to_one": float(sum(exit_share.values()) + sum(entry_share.values()) + reweight_share),
        },
        "names_replaced_per_rebalance": {
            "long_leg_fraction": changed_long,
            "short_leg_fraction": changed_short,
            "both_legs_fraction": (changed_long + changed_short) / 2.0,
            "retention_rate": 1.0 - (changed_long + changed_short) / 2.0,
        },
        "exit_distance_from_entry_cutoff": {
            "weighted_share_within_5_percentile_points": within(5.0),
            "within_10": within(10.0),
            "within_20": within(20.0),
            "within_30": within(30.0),
            "definition": "share of EXIT turnover from names still ranked in the traded "
                          "cross-section whose current percentile is within k points of the "
                          "quintile cutoff they crossed",
        },
        "rank_stability": {
            "mean_spearman_between_consecutive_rebalances": float(np.mean(rank_corr)),
            "min_spearman": float(np.min(rank_corr)),
            "mean_abs_percentile_move": float(np.mean(abs_pct_move)),
            "sd_percentile_move": float(all_moves.std()),
            "share_of_names_moving_less_than_5_points": float(np.mean(np.abs(all_moves) < 0.05)),
            "share_moving_less_than_10_points": float(np.mean(np.abs(all_moves) < 0.10)),
            "share_moving_more_than_30_points": float(np.mean(np.abs(all_moves) > 0.30)),
        },
        "per_date_one_way_turnover": {
            "p10": float(np.percentile(turnover, 10)),
            "median": float(np.median(turnover)),
            "p90": float(np.percentile(turnover, 90)),
            "max": float(turnover.max()),
        },
    }


def breakeven_half_spread(
    periods: pd.DataFrame, *, commission_bps: float = 1.0, capital: float = 1_000_000.0
) -> dict[str, Any]:
    """The half-spread (bp) at which mean net period return is zero, impact held fixed.

    Cost per period is `turnover_round_trip * (commission + half_spread) / 1e4`
    plus a square-root impact term that does not depend on the spread, so the
    break-even solves in closed form from the backtest's own per-period rows.
    Reported with the gross edge per unit of turnover: the quantity that decides
    whether a signal can pay for the trading it causes.

    A negative break-even means the strategy loses money net of commission and
    impact even with a zero spread.
    """
    gross = float(periods["gross_return"].mean())
    round_trip = float(periods["turnover_round_trip"].mean())
    impact = float(periods["impact"].mean()) / capital
    commission = float(periods["commission"].mean()) / capital
    spread = float(periods["spread"].mean()) / capital
    cost = float(periods["cost_return"].mean())
    breakeven = (
        ((gross - impact) / round_trip) * 1e4 - commission_bps if round_trip > 0 else None
    )
    return {
        "mean_gross_return_per_period_bp": gross * 1e4,
        "mean_round_trip_turnover_per_period": round_trip,
        "gross_bp_per_unit_round_trip_turnover": gross * 1e4 / round_trip if round_trip else None,
        "gross_bp_per_unit_one_way_turnover": gross * 1e4 / (round_trip / 2.0) if round_trip else None,
        "mean_cost_per_period_bp": cost * 1e4,
        "cost_components_share": {
            "commission": commission / cost if cost else None,
            "spread": spread / cost if cost else None,
            "impact": impact / cost if cost else None,
        },
        "breakeven_half_spread_bp": breakeven,
        "breakeven_definition": (
            "half-spread at which mean(gross) - mean(round_trip_turnover)*(commission+h)/1e4 "
            "- mean(impact) = 0; impact held at its 10bp-run value"
        ),
    }
