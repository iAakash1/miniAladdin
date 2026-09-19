"""Portfolio-construction rules: what they hold, what they never touch.

These assert the mechanical guarantees the EXP-009A preregistration relies on
*before* any rule is scored on data: entry sets equal the baseline's, retained
bands never overlap, forced exits are honoured, a drop budget is a budget, and
no rule reads a return. A rule that passed only on results would not be
evidence of anything.
"""

import numpy as np
import pandas as pd
import pytest

from src.quant.backtest.costs import SimpleCostModel
from src.quant.backtest.engine import BacktestConfig, _quantile_weights, run_backtest
from src.quant.backtest.rules import (
    MinimumHoldRule,
    QuantileRule,
    RankHysteresisRule,
    TopKDropoutRule,
    rule_from_spec,
)

MAX_W = 0.10


def cross_section(n=100, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(size=n), index=[f"S{i:03d}" for i in range(n)])


def panel(n_symbols=100, n_dates=60, rho=0.8, seed=1):
    """Persistent latent score plus noise; returns independent of the score."""
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:03d}" for i in range(n_symbols)]
    latent = rng.normal(size=n_symbols)
    dates = pd.date_range("2020-01-03", periods=n_dates, freq="7D").date
    rows = []
    for day in dates:
        latent = rho * latent + np.sqrt(1 - rho**2) * rng.normal(size=n_symbols)
        for i, s in enumerate(symbols):
            rows.append((day, s, latent[i] + 0.3 * rng.normal(), rng.normal(0, 0.03),
                         1e8 + rng.uniform(0, 1e7)))
    frame = pd.DataFrame(rows, columns=["date", "symbol", "prediction", "fwd_ret_5", "dollar_volume"])
    return frame[["date", "symbol", "prediction"]], frame[["date", "symbol", "fwd_ret_5", "dollar_volume"]]


def held(weights):
    return set(weights.index[weights > 0]), set(weights.index[weights < 0])


def check_book(weights):
    assert weights is not None
    assert weights[weights > 0].sum() == pytest.approx(0.5)
    assert weights[weights < 0].sum() == pytest.approx(-0.5)
    longs, shorts = held(weights)
    assert not longs & shorts


# ── the baseline, restated ──────────────────────────────────────────────────

def test_quantile_rule_equals_the_engines_own_weights():
    for seed in range(5):
        scores = cross_section(seed=seed)
        theirs = _quantile_weights(scores, quantiles=5, long_short=True, max_weight=MAX_W)
        mine = QuantileRule().weights(scores, pd.Series(dtype=float), max_weight=MAX_W)
        pd.testing.assert_series_equal(mine.sort_index(), theirs.sort_index())


def test_engine_with_quantile_rule_reproduces_the_default_path_exactly():
    pred, ret = panel()
    base = run_backtest(pred, ret, config=BacktestConfig(execution_lag_periods=1))
    ruled = run_backtest(
        pred, ret, config=BacktestConfig(execution_lag_periods=1, weight_rule=QuantileRule())
    )
    pd.testing.assert_frame_equal(base.periods, ruled.periods)


def test_default_config_serialisation_is_unchanged_by_the_hook():
    assert "weight_rule" not in BacktestConfig().as_dict()
    assert "weight_rule" in BacktestConfig(weight_rule=QuantileRule()).as_dict()


# ── rank hysteresis ─────────────────────────────────────────────────────────

def test_hysteresis_entrants_are_exactly_the_baseline_extremes():
    scores = cross_section()
    weights = RankHysteresisRule(retain_fraction=0.4).weights(
        scores, pd.Series(dtype=float), max_weight=MAX_W
    )
    base = _quantile_weights(scores, quantiles=5, long_short=True, max_weight=MAX_W)
    assert held(weights) == held(base)          # no incumbents -> baseline entry


def test_hysteresis_retains_incumbents_inside_the_band_and_drops_those_outside():
    scores = cross_section(n=100)
    order = list(scores.sort_values(ascending=False).index)          # best first
    previous = pd.Series({order[25]: 0.02, order[30]: 0.02, order[45]: 0.02,   # inside 40% band? 25,30 yes; 45 no
                          order[-26]: -0.02, order[-46]: -0.02})
    weights = RankHysteresisRule(retain_fraction=0.4).weights(scores, previous, max_weight=MAX_W)
    longs, shorts = held(weights)
    assert order[25] in longs and order[30] in longs       # ranks 26, 31 of 100: inside the top 40
    assert order[45] not in longs                          # rank 46: outside
    assert order[-26] in shorts
    assert order[-46] not in shorts
    check_book(weights)


def test_hysteresis_holds_a_superset_of_the_baseline_and_never_overlaps():
    rng = np.random.default_rng(3)
    rule = RankHysteresisRule(retain_fraction=0.4)
    previous = pd.Series(dtype=float)
    for _ in range(30):
        scores = pd.Series(rng.normal(size=120), index=[f"S{i}" for i in range(120)])
        weights = rule.weights(scores, previous, max_weight=MAX_W)
        base = _quantile_weights(scores, quantiles=5, long_short=True, max_weight=MAX_W)
        longs, shorts = held(weights)
        blongs, bshorts = held(base)
        assert blongs <= longs and bshorts <= shorts
        check_book(weights)
        previous = weights


def test_a_retain_band_equal_to_the_entry_band_is_the_baseline():
    rule = RankHysteresisRule(retain_fraction=0.2)
    scores = cross_section(n=100)
    previous = QuantileRule().weights(cross_section(n=100, seed=9), pd.Series(dtype=float), max_weight=MAX_W)
    weights = rule.weights(scores, previous, max_weight=MAX_W)
    base = _quantile_weights(scores, quantiles=5, long_short=True, max_weight=MAX_W)
    assert held(weights) == held(base)


def test_hysteresis_rejects_bands_that_would_sell_what_the_baseline_buys():
    with pytest.raises(ValueError):
        RankHysteresisRule(retain_fraction=0.1)
    with pytest.raises(ValueError):
        RankHysteresisRule(retain_fraction=0.5)


def test_a_held_name_missing_from_the_cross_section_is_a_forced_exit():
    scores = cross_section(n=100)
    ghost = "GONE"
    previous = pd.Series({ghost: 0.02, scores.idxmax(): 0.02})
    weights = RankHysteresisRule().weights(scores, previous, max_weight=MAX_W)
    assert ghost not in weights.index


# ── top-k dropout ───────────────────────────────────────────────────────────

def test_dropout_first_rebalance_is_the_baseline_book():
    scores = cross_section()
    weights = TopKDropoutRule().weights(scores, pd.Series(dtype=float), max_weight=MAX_W)
    base = _quantile_weights(scores, quantiles=5, long_short=True, max_weight=MAX_W)
    assert held(weights) == held(base)


def test_dropout_replaces_at_most_the_drop_budget_per_leg():
    rng = np.random.default_rng(4)
    rule = TopKDropoutRule(drop_fraction=0.10)                       # k=20 -> 2 per leg
    names = [f"S{i}" for i in range(100)]
    previous = rule.weights(pd.Series(rng.normal(size=100), index=names), pd.Series(dtype=float), max_weight=MAX_W)
    for _ in range(25):
        scores = pd.Series(rng.normal(size=100), index=names)         # a full reshuffle
        weights = rule.weights(scores, previous, max_weight=MAX_W)
        (pl, ps), (nl, ns) = held(previous), held(weights)
        assert len(nl - pl) <= 2 and len(ns - ps) <= 2
        assert len(nl) == 20 and len(ns) == 20
        check_book(weights)
        previous = weights


def test_dropout_never_sells_an_incumbent_that_outranks_every_candidate():
    names = [f"S{i:03d}" for i in range(100)]
    scores = pd.Series(np.arange(100, 0, -1, dtype=float), index=names)   # S000 best ... S099 worst
    rule = TopKDropoutRule(drop_fraction=0.10)
    weights = rule.weights(scores, pd.Series(dtype=float), max_weight=MAX_W)
    again = rule.weights(scores, weights, max_weight=MAX_W)               # nothing changed
    assert held(again) == held(weights)
    assert (again.reindex(weights.index).fillna(0) - weights).abs().sum() == pytest.approx(0.0)


def test_dropout_forced_exits_are_refilled_and_do_not_use_the_budget():
    names = [f"S{i:03d}" for i in range(100)]
    scores = pd.Series(np.arange(100, 0, -1, dtype=float), index=names)
    rule = TopKDropoutRule(drop_fraction=0.10)
    weights = rule.weights(scores, pd.Series(dtype=float), max_weight=MAX_W)
    longs, _ = held(weights)
    gone = sorted(longs)[:5]                                              # 5 incumbents vanish
    shrunk = scores.drop(gone)
    after = rule.weights(shrunk, weights, max_weight=MAX_W)
    nl, _ = held(after)
    assert not set(gone) & nl
    assert len(nl) == len(_entry_size(shrunk))                            # refilled to k
    check_book(after)


def _entry_size(scores):
    base = _quantile_weights(scores, quantiles=5, long_short=True, max_weight=MAX_W)
    return held(base)[0]


def test_dropout_cannot_put_one_name_on_both_sides():
    rng = np.random.default_rng(6)
    rule = TopKDropoutRule(drop_fraction=0.5)
    names = [f"S{i}" for i in range(60)]
    previous = pd.Series(dtype=float)
    for _ in range(40):
        scores = pd.Series(rng.normal(size=60), index=names)
        previous = rule.weights(scores, previous, max_weight=MAX_W)
        check_book(previous)


# ── minimum hold ────────────────────────────────────────────────────────────

def test_minimum_hold_locks_a_name_until_the_release_period():
    names = [f"S{i:03d}" for i in range(100)]
    good = pd.Series(np.arange(100, 0, -1, dtype=float), index=names)        # S000 best
    rule = MinimumHoldRule(min_hold_periods=3)
    rule.reset()
    w1 = rule.weights(good, pd.Series(dtype=float), max_weight=MAX_W)
    assert "S000" in held(w1)[0]
    flipped = good.copy()
    flipped["S000"] = -1e9                                                    # now the worst name
    w2 = rule.weights(flipped, w1, max_weight=MAX_W)                          # held 1 period: locked
    w3 = rule.weights(flipped, w2, max_weight=MAX_W)                          # held 2: locked
    assert "S000" in held(w2)[0] and "S000" in held(w3)[0]
    assert "S000" not in held(w3)[1]                                          # not also short
    w4 = rule.weights(flipped, w3, max_weight=MAX_W)                          # held 3: released
    assert "S000" not in held(w4)[0]
    assert "S000" in held(w4)[1]                                              # baseline now shorts it
    check_book(w4)


def test_minimum_hold_still_honours_forced_exits():
    names = [f"S{i:03d}" for i in range(100)]
    scores = pd.Series(np.arange(100, 0, -1, dtype=float), index=names)
    rule = MinimumHoldRule(min_hold_periods=10)
    rule.reset()
    w1 = rule.weights(scores, pd.Series(dtype=float), max_weight=MAX_W)
    after = rule.weights(scores.drop("S000"), w1, max_weight=MAX_W)
    assert "S000" not in after.index


def test_minimum_hold_state_does_not_leak_between_backtests():
    pred, ret = panel()
    rule = MinimumHoldRule(min_hold_periods=4)
    config = BacktestConfig(weight_rule=rule)
    first = run_backtest(pred, ret, config=config)
    second = run_backtest(pred, ret, config=config)
    pd.testing.assert_frame_equal(first.periods, second.periods)


# ── engine integration and what a rule may not see ──────────────────────────

@pytest.mark.parametrize("rule", [
    RankHysteresisRule(retain_fraction=0.4),
    RankHysteresisRule(retain_fraction=0.3),
    TopKDropoutRule(drop_fraction=0.10),
    MinimumHoldRule(min_hold_periods=4),
])
def test_no_rule_reads_a_return(rule):
    """Weights must be a function of scores and prior weights only."""
    pred, ret = panel()
    real = run_backtest(pred, ret, config=BacktestConfig(weight_rule=rule, record_weights=True))
    shuffled = ret.copy()
    shuffled["fwd_ret_5"] = np.random.default_rng(99).permutation(shuffled["fwd_ret_5"].to_numpy())
    other = run_backtest(pred, shuffled, config=BacktestConfig(weight_rule=rule, record_weights=True))
    pd.testing.assert_frame_equal(real.weights, other.weights)
    assert not np.allclose(real.periods["gross_return"], other.periods["gross_return"])


@pytest.mark.parametrize("rule", [
    RankHysteresisRule(retain_fraction=0.4),
    RankHysteresisRule(retain_fraction=0.3),
    TopKDropoutRule(drop_fraction=0.10),
    MinimumHoldRule(min_hold_periods=4),
])
def test_every_rule_lowers_turnover_on_a_persistent_signal(rule):
    pred, ret = panel(rho=0.8)
    base = run_backtest(pred, ret, config=BacktestConfig())
    ruled = run_backtest(pred, ret, config=BacktestConfig(weight_rule=rule))
    assert ruled.metrics["annualised_turnover"] < base.metrics["annualised_turnover"]
    assert ruled.metrics["mean_gross_exposure"] == pytest.approx(1.0)


def test_rules_keep_the_baselines_cost_accounting():
    pred, ret = panel()
    cfg = BacktestConfig(weight_rule=RankHysteresisRule(), cost_model=SimpleCostModel(half_spread_bps=10.0),
                         record_weights=True)
    result = run_backtest(pred, ret, config=cfg)
    p = result.periods
    rate = (1.0 + 10.0) / 10000.0
    # Impact is non-linear, so the linear reconciliation is a lower bound.
    assert (p["cost_return"] + 1e-12 >= p["turnover_round_trip"] * rate).all()


def test_rules_reject_a_long_only_book():
    pred, ret = panel()
    with pytest.raises(ValueError):
        run_backtest(pred, ret, config=BacktestConfig(weight_rule=TopKDropoutRule(), long_short=False))


def test_rule_from_spec_round_trips_and_rejects_unknowns():
    assert rule_from_spec({"rule": "baseline"}) is None
    assert isinstance(rule_from_spec({"rule": "rank_hysteresis", "retain_fraction": 0.4}), RankHysteresisRule)
    assert isinstance(rule_from_spec({"rule": "topk_dropout", "drop_fraction": 0.1}), TopKDropoutRule)
    assert isinstance(rule_from_spec({"rule": "minimum_hold", "min_hold_periods": 4}), MinimumHoldRule)
    with pytest.raises(ValueError):
        rule_from_spec({"rule": "nonsense"})
