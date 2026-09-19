"""
Portfolio-construction rules — how a cross-section of scores becomes weights.

## Why this module exists

The baseline backtest (`engine._quantile_weights`) holds exactly the top and
bottom quintile at every rebalance. A name one rank inside the cutoff is held; a
name one rank outside is sold, and it can be bought back at the next
rebalance. EXP-006 shows what that costs: about 40% of each leg is replaced at
every weekly rebalance, which is 20.15x annualised one-way turnover, and the
transaction costs it triggers are 126.6% of the gross return.

The rules here change *only* which names are held. They do not touch the
predictions, the forward returns, the cost model or the turnover accounting —
all of that stays in `engine.run_backtest`, so a number produced under any rule
is directly comparable to the baseline. There is one backtester.

## The four constructions

`QuantileRule`
    The baseline, restated as a rule. Exists so the rule interface can be
    tested against the engine's own weights, and as an explicit control.

`RankHysteresisRule`
    An sS ("buy/hold spread") rule. A name *enters* a leg when it is in the
    top (bottom) quintile; it is *retained* until it leaves the top (bottom)
    `retain_fraction` of the cross-section. Novy-Marx & Velikov (2016) describe
    the technique: names that fall just outside the entry cutoff are close
    substitutes for the ones just inside, so selling and re-buying them
    only pays spread.

`TopKDropoutRule`
    Hold a fixed number of names per leg and replace at most `drop_fraction` of
    them per rebalance — the worst-ranked incumbents, and only if a better
    non-held candidate exists. The idea is public (Microsoft Qlib's
    `TopkDropoutStrategy`, MIT); this is an independent re-implementation of
    the logic inside OmniSignal's own long/short accounting. No Qlib code is
    imported or copied.

`MinimumHoldRule`
    Baseline quintile entry, but a name that has been held for fewer than
    `min_hold_periods` rebalances cannot be sold on rank alone. The signal is a
    21-session forecast; re-deciding a name before that horizon has elapsed is
    not something the target supports.

## Conventions shared by every rule

* Entry uses exactly the baseline's bucket definition (`pd.qcut` on
  `rank(method="first")`), so an entering name is one the baseline would also
  hold. A rule differs from the baseline only in what it *retains*.
* Each leg is equal-weighted at 0.5 gross, 0.5 gross short; the max-weight cap
  is applied exactly as in the engine.
* A held name that is absent from the current cross-section (no prediction, no
  forward return, left the universe) is a **forced exit**. It is never carried.
  Forced exits do not count against a drop budget.
* Ties are broken by `rank(method="first")`, which is deterministic for a
  fixed input order.
* Rules are stateful only through what the engine hands them (`previous`
  weights) plus, for `MinimumHoldRule`, a holding-age table. `reset()` clears
  state; the engine calls it before every backtest.
* Nothing here reads a return. A rule sees scores and prior weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

#: Equal split of unit gross between the legs, as in the baseline.
LEG_GROSS = 0.5


def _scores(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").dropna()


def _baseline_buckets(values: pd.Series, quantiles: int) -> Optional[pd.Series]:
    """The baseline's bucket assignment, or None where it would decline to trade."""
    if len(values) < quantiles * 2 or values.nunique() < quantiles:
        return None
    try:
        return pd.qcut(values.rank(method="first"), quantiles, labels=False)
    except ValueError:
        return None


def _entry_sets(values: pd.Series, quantiles: int) -> Optional[tuple[list, list]]:
    buckets = _baseline_buckets(values, quantiles)
    if buckets is None:
        return None
    top = list(values.index[buckets == quantiles - 1])
    bottom = list(values.index[buckets == 0])
    if not top or not bottom:
        return None
    return top, bottom


def _equal_weights(longs: list, shorts: list, max_weight: float) -> Optional[pd.Series]:
    """0.5 gross per leg, equal within the leg, capped like the engine."""
    if not longs or not shorts:
        return None
    weights = pd.Series(
        {**{name: LEG_GROSS / len(longs) for name in longs},
         **{name: -LEG_GROSS / len(shorts) for name in shorts}},
        dtype=float,
    )
    over = weights.abs() > max_weight
    if over.any():
        weights[over] = np.sign(weights[over]) * max_weight
    return weights[weights != 0.0]


def _held(previous: pd.Series) -> tuple[list, list]:
    if previous is None or len(previous) == 0:
        return [], []
    return list(previous.index[previous > 0]), list(previous.index[previous < 0])


class WeightRule:
    """Interface: scores + previous weights in, weights out (or None to skip)."""

    name: str = "rule"

    def reset(self) -> None:  # pragma: no cover - default is stateless
        return None

    def weights(
        self, scores: pd.Series, previous: pd.Series, *, max_weight: float
    ) -> Optional[pd.Series]:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class QuantileRule(WeightRule):
    """The baseline: hold exactly the extreme quantile at every rebalance."""

    quantiles: int = 5
    name: str = "quantile"

    def weights(self, scores, previous, *, max_weight):
        values = _scores(scores)
        sets = _entry_sets(values, self.quantiles)
        if sets is None:
            return None
        return _equal_weights(sets[0], sets[1], max_weight)

    def describe(self) -> dict[str, Any]:
        return {"rule": self.name, "quantiles": self.quantiles}


@dataclass
class RankHysteresisRule(WeightRule):
    """sS buy/hold spread: enter at the extreme quantile, retain to a wider band.

    `retain_fraction` is the share of the cross-section, from the top (bottom),
    inside which an incumbent is kept. It must be at least `1 / quantiles` —
    the entry band — otherwise the rule would sell names the baseline would
    buy.
    """

    quantiles: int = 5
    retain_fraction: float = 0.40
    name: str = "rank_hysteresis"

    def __post_init__(self) -> None:
        if not (1.0 / self.quantiles) <= self.retain_fraction < 0.5:
            raise ValueError(
                "retain_fraction must satisfy 1/quantiles <= retain_fraction < 0.5 so "
                "the retained bands are wider than the entry bands and cannot overlap"
            )

    def weights(self, scores, previous, *, max_weight):
        values = _scores(scores)
        sets = _entry_sets(values, self.quantiles)
        if sets is None:
            return None
        entry_long, entry_short = sets

        ranks = values.rank(method="first")
        band = max(int(round(self.retain_fraction * len(values))), 1)
        order = ranks.sort_values(ascending=False).index
        zone_long = set(order[:band])
        zone_short = set(order[-band:])

        prev_long, prev_short = _held(previous)
        longs = {n for n in prev_long if n in zone_long} | set(entry_long)
        shorts = {n for n in prev_short if n in zone_short} | set(entry_short)
        # The two bands are disjoint by construction (retain_fraction < 0.5),
        # and an entrant is inside its own retained band, so no name is in both.
        return _equal_weights(sorted(longs, key=str), sorted(shorts, key=str), max_weight)

    def describe(self) -> dict[str, Any]:
        return {
            "rule": self.name,
            "quantiles": self.quantiles,
            "enter": f"top/bottom 1/{self.quantiles} of the cross-section",
            "retain_fraction": self.retain_fraction,
        }


@dataclass
class TopKDropoutRule(WeightRule):
    """Hold k names per leg; replace at most `drop_fraction * k` per rebalance.

    k is the size of the baseline extreme bucket at the first rebalance and
    is re-read from the current cross-section thereafter, so the leg keeps
    the baseline's breadth. The drop budget is `max(1, round(drop_fraction *
    k))`.

    Per leg, per rebalance (independent re-implementation of the published
    logic):

      1. Incumbents still in the cross-section stay; the rest are forced
         exits and are not counted against the budget.
      2. `today` = the best-ranked non-held names, `n_drop + refill` of them,
         where `refill = max(k - incumbents, 0)`.
      3. Sort `incumbents + today` by score; the incumbents that fall in the
         bottom `n_drop` of that combined list are sold. An incumbent that
         out-ranks every candidate is therefore never sold.
      4. Buy the best `today` names up to `sold + refill`.
      5. If k shrank so that incumbents exceed k, sell the lowest-ranked
         extra incumbents.

    A name held on one side is not a candidate on the other side in the same
    rebalance, so a flip long -> short takes two rebalances. That is a
    deliberate simplification (it makes an overlap impossible) and it is
    conservative: it can only reduce turnover savings, never create them.
    """

    quantiles: int = 5
    drop_fraction: float = 0.10
    name: str = "topk_dropout"

    def __post_init__(self) -> None:
        if not 0.0 < self.drop_fraction <= 1.0:
            raise ValueError("drop_fraction must be in (0, 1]")

    def _leg(self, ranked: list, incumbents_all: list, other_side: set, k: int) -> list:
        """One leg. `ranked` is best-first for this leg; returns the new holding list."""
        position = {name: i for i, name in enumerate(ranked)}
        incumbent_set = set(incumbents_all)
        held = [n for n in ranked if n in incumbent_set]                  # forced exits drop out here
        n_drop = max(1, int(round(self.drop_fraction * k)))
        refill = max(k - len(held), 0)

        held_set = set(held)
        candidates = [n for n in ranked if n not in held_set and n not in other_side]
        today = candidates[: n_drop + refill]

        combined = sorted(held + today, key=position.__getitem__)         # best-first
        bottom = set(combined[-n_drop:])
        sold = {n for n in held if n in bottom}

        keep = [n for n in held if n not in sold]
        buy = today[: len(sold) + refill]
        new = keep + buy
        if len(new) > k:                                                   # k shrank
            new = sorted(new, key=position.__getitem__)[:k]
        return new

    def weights(self, scores, previous, *, max_weight):
        values = _scores(scores)
        sets = _entry_sets(values, self.quantiles)
        if sets is None:
            return None
        k_long, k_short = len(sets[0]), len(sets[1])

        prev_long, prev_short = _held(previous)
        if not prev_long and not prev_short:
            return _equal_weights(sets[0], sets[1], max_weight)

        ranks = values.rank(method="first")
        best_first = list(ranks.sort_values(ascending=False).index)
        worst_first = list(reversed(best_first))

        longs = self._leg(best_first, prev_long, set(prev_short), k_long)
        shorts = self._leg(worst_first, prev_short, set(prev_long), k_short)
        return _equal_weights(longs, shorts, max_weight)

    def describe(self) -> dict[str, Any]:
        return {
            "rule": self.name,
            "quantiles": self.quantiles,
            "k": "size of the baseline extreme bucket per leg",
            "drop_fraction": self.drop_fraction,
            "drop_count": "max(1, round(drop_fraction * k)) per leg per rebalance",
        }


@dataclass
class MinimumHoldRule(WeightRule):
    """Baseline entry; a name cannot be sold on rank until held for `min_hold_periods`.

    `min_hold_periods` counts rebalances. A name entered at rebalance t is held
    through t .. t+H-1 and may first be released at t+H.
    """

    quantiles: int = 5
    min_hold_periods: int = 4
    name: str = "minimum_hold"
    _age: dict = field(default_factory=dict, repr=False)   # name -> (side, periods held)

    def __post_init__(self) -> None:
        if self.min_hold_periods < 1:
            raise ValueError("min_hold_periods must be >= 1")

    def reset(self) -> None:
        self._age = {}

    def weights(self, scores, previous, *, max_weight):
        values = _scores(scores)
        sets = _entry_sets(values, self.quantiles)
        if sets is None:
            return None
        entry_long, entry_short = set(sets[0]), set(sets[1])

        locked_long, locked_short = set(), set()
        for name, (side, age) in self._age.items():
            if name not in values.index:
                continue                                    # forced exit
            if age < self.min_hold_periods:
                (locked_long if side > 0 else locked_short).add(name)

        # A locked name keeps its side; it cannot also be entered on the other.
        longs = locked_long | (entry_long - locked_short)
        shorts = locked_short | (entry_short - locked_long)

        weights = _equal_weights(sorted(longs, key=str), sorted(shorts, key=str), max_weight)
        if weights is None:
            return None

        updated: dict = {}
        for name in longs:
            prior = self._age.get(name)
            updated[name] = (1, prior[1] + 1 if prior and prior[0] > 0 else 1)
        for name in shorts:
            prior = self._age.get(name)
            updated[name] = (-1, prior[1] + 1 if prior and prior[0] < 0 else 1)
        self._age = updated
        return weights

    def describe(self) -> dict[str, Any]:
        return {
            "rule": self.name,
            "quantiles": self.quantiles,
            "min_hold_periods": self.min_hold_periods,
            "release": "a name may first be sold min_hold_periods rebalances after entry",
        }


def rule_from_spec(spec: dict[str, Any]) -> Optional[WeightRule]:
    """Build a rule from a frozen definition. `None` means the engine baseline."""
    kind = spec.get("rule")
    if kind in (None, "baseline"):
        return None
    if kind == "quantile":
        return QuantileRule(quantiles=spec.get("quantiles", 5))
    if kind == "rank_hysteresis":
        return RankHysteresisRule(
            quantiles=spec.get("quantiles", 5),
            retain_fraction=spec["retain_fraction"],
        )
    if kind == "topk_dropout":
        return TopKDropoutRule(
            quantiles=spec.get("quantiles", 5), drop_fraction=spec["drop_fraction"]
        )
    if kind == "minimum_hold":
        return MinimumHoldRule(
            quantiles=spec.get("quantiles", 5), min_hold_periods=spec["min_hold_periods"]
        )
    raise ValueError(f"unknown portfolio rule {kind!r}")


__all__ = [
    "LEG_GROSS",
    "MinimumHoldRule",
    "QuantileRule",
    "RankHysteresisRule",
    "TopKDropoutRule",
    "WeightRule",
    "rule_from_spec",
]
