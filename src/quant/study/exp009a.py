"""
EXP-009A — does a turnover-aware portfolio rule rescue EXP-006's frozen signal?

## The question, and what it is not

EXP-006 found a weak but statistically detectable cross-sectional ranking signal
(Rank IC 0.029, Newey-West t 2.66) that failed economically: 20.15x annualised
turnover, transaction costs equal to 126.6% of the gross return, net Sharpe -0.10
at a 10 bp half-spread. The failure has two ingredients — the signal is weak, and
the portfolio trades it too hard. This study isolates the second ingredient.

**It changes only how the frozen predictions are turned into a book.** No model is
refit. No prediction is altered. No feature is added. The same 100,246
out-of-sample gradient-boosting predictions, the same forward returns, the same
cost model, the same turnover accounting (`engine.run_backtest`). Four
construction rules are compared with the immediate-replacement control:

    B  rank hysteresis  (Novy-Marx & Velikov sS rule; two band widths)
    C  top-k dropout    (public Qlib idea, re-implemented; k, n_drop from its benchmark)
    D  minimum hold     (one 21-session label horizon)

Because the inputs are frozen and pre-holdout, the sealed 252-session holdout is
not read, scored or touched. The firewall is armed for the run and the run is
refused if any input reaches it.

## Why the answer is not "turnover falls, therefore success"

A turnover-reducing rule lowers cost *by construction*: any rule that trades less
pays less. A "net improvement" is therefore close to guaranteed and says nothing
about the signal. What is genuinely uncertain — and what decides whether the
mechanism is real — is **how much of the gross edge survives holding stale
names**. The preregistered criteria therefore test the turnover cut, the gross
retention, and the *paired uncertainty of the net difference*, separately.

## Governance

`prereg_gate` refuses to run unless the preregistration document (a) exists,
(b) embeds this module's definition fingerprint, (c) is committed unchanged, and
(d) its commit is already an ancestor of `origin/main`. The fingerprint covers
the frozen definition plus the source of `rules.py` and `engine.py`, so the
method cannot drift after registration without the gate failing.

Nothing here promotes a model. Results are labelled EXPERIMENTAL / PROMOTION NOT
ASSESSED.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import time
from datetime import date as Date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.backtest.attribution import attribute_returns
from src.quant.backtest.costs import SimpleCostModel
from src.quant.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from src.quant.backtest.rules import rule_from_spec
from src.quant.backtest.turnover_diagnostics import (
    breakeven_half_spread,
    decompose_turnover,
    independent_turnover,
    lagged_frame,
)
from src.quant.labels.geometry import LabelGeometry
from src.quant.study.firewall import FIREWALL, HoldoutBreach  # noqa: F401 - re-exported for callers
from src.quant.validation.significance import deflated_sharpe_ratio

EXPERIMENT_ID = "EXP-009A"
PARENT_EXPERIMENT = "EXP-006"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_009A_TURNOVER_PREREGISTRATION.md")
FROZEN_PREDICTIONS = Path("experiments/EXP-006/predictions_fwd_rank_21.parquet")
FROZEN_METRICS = Path("experiments/EXP-006/metrics.json")
RETURNS_PANEL_CACHE = Path("data/research/derived/exp009a_returns_panel.parquet")

PERIODS_PER_YEAR = 252 / 5

#: The frozen definition. Every number below was fixed before any treatment
#: cell was evaluated. `docs/EXP_009A_TURNOVER_PREREGISTRATION.md` embeds the
#: fingerprint of this dictionary plus the method source files.
DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "parent_experiment": PARENT_EXPERIMENT,
    "status": "EXPERIMENTAL - PROMOTION NOT ASSESSED",
    "input": {
        "predictions_file": str(FROZEN_PREDICTIONS),
        "model": "gradient_boosting",
        "target": "fwd_rank_21",
        "first_prediction_date": "2017-05-05",
        "last_prediction_date": "2025-05-09",
        "rows": 100246,
        "refit": False,
        "note": "frozen out-of-sample predictions; never refit, never altered",
    },
    "engine": {
        "rebalance_step_sessions": 5,
        "execution_lag_periods": 1,
        "quantiles": 5,
        "long_short": True,
        "leg_gross": 0.5,
        "max_weight": 0.10,
        "min_names": 10,
        "capital": 1_000_000.0,
        "commission_bps": 1.0,
        "impact_coefficient": 0.1,
        "forward_return_column": "fwd_ret_5",
        "turnover_convention": "one-way = sum|delta_w| / 2, annualised x 50.4",
    },
    "costs": {"primary_half_spread_bps": 10.0, "sweep_half_spread_bps": [1.0, 3.0, 5.0, 10.0, 20.0]},
    "cells": [
        {"id": "A_immediate", "role": "control", "rule": "baseline"},
        {
            "id": "B_hysteresis_40", "role": "treatment", "family": "B",
            "rule": "rank_hysteresis", "quantiles": 5, "retain_fraction": 0.40,
            "anchor": "Novy-Marx & Velikov (2016) sS rule 10%/20% on deciles, scaled 2:1 to quintiles: enter top 20%, retain to top 40%",
        },
        {
            "id": "B_hysteresis_30", "role": "treatment", "family": "B",
            "rule": "rank_hysteresis", "quantiles": 5, "retain_fraction": 0.30,
            "anchor": "milder 3:2 band (enter top 20%, retain to top 30%); dose-response companion",
        },
        {
            "id": "C_topk_dropout_10", "role": "treatment", "family": "C",
            "rule": "topk_dropout", "quantiles": 5, "drop_fraction": 0.10,
            "anchor": "Qlib benchmark topk=50, n_drop=5 (10% of k) on a 250-name universe where a quintile is 50 names",
        },
        {
            "id": "D_min_hold_4", "role": "treatment", "family": "D",
            "rule": "minimum_hold", "quantiles": 5, "min_hold_periods": 4,
            "anchor": "4 rebalances x 5 sessions = 20 sessions ~ the 21-session label horizon",
        },
    ],
    "criteria": {
        "validity": {
            "control_must_reproduce_exp006": True,
            "tolerance_relative": 1e-9,
            "compared": [
                "periods", "mean_turnover", "annualised_turnover", "gross_sharpe",
                "net_sharpe", "cost_share_of_gross", "net_cagr", "total_cost_return",
            ],
            "on_failure": "INVALID - no treatment result is reported",
        },
        "T1_turnover_cut": "annualised one-way turnover <= 0.70 x control (a cut of at least 30%)",
        "T2_gross_retention": "mean gross period return >= 0.75 x control's",
        "T3_net_gain": (
            "paired moving-block bootstrap of (net Sharpe at 10 bp, treatment - control): the "
            "one-sided lower bound at level 1 - 0.05/4 is > 0"
        ),
        "T4_fold_consistency": "mean net period return exceeds control's in at least 6 of the 8 folds",
        "classification": {
            "MECHANISM_CONFIRMED": "T1 and T2 and T3 and T4",
            "EDGE_LOST": "T1 and not T2",
            "INSUFFICIENT_TURNOVER_CUT": "not T1",
            "NO_RELIABLE_NET_GAIN": "T1 and T2 and (not T3 or not T4)",
        },
        "carry_forward": (
            "if more than one cell is MECHANISM_CONFIRMED, the one with the highest T2 gross-retention "
            "ratio is the mechanism frozen for EXP-009B/C; ties by fewer parameters"
        ),
        "descriptive_only": [
            "net Sharpe > 0 at 10 bp", "cost share of gross", "break-even half-spread",
            "max drawdown", "factor-alpha t-statistic", "deflated Sharpe", "capacity proxy",
        ],
        "promotion": "NOT ASSESSED - this study cannot promote a model",
    },
    "inference": {
        "hac_newey_west_lags": 4,
        "bootstrap": "circular moving-block, paired across cells",
        "block_length_periods": 8,
        "draws": 10000,
        "seed": 0,
        "family_alpha": 0.05,
        "n_treatments": 4,
        "note": "overlap: 21-session labels every 5 sessions give ~4.2 periods of dependence",
    },
    "trials": {
        "declared_treatments": 4,
        "prior_cumulative_evaluations": 156,
        "cumulative_evaluations": 160,
        "not_run_in_this_study": ["exponential score smoother", "rebalance-cadence change", "any refit"],
    },
    "holdout": {"read": False, "cutoff": "the sealed window in experiments/EXP-006/metrics.json is never read"},
}


class PreregistrationError(RuntimeError):
    """Raised when the run is attempted without a valid, pushed preregistration."""


# ── fingerprint and gate ─────────────────────────────────────────────────────

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


METHOD_SOURCES = ("src/quant/backtest/rules.py", "src/quant/backtest/engine.py")


def definition_fingerprint(root: Path = Path(".")) -> str:
    """sha256 over the canonical definition and the method source files."""
    payload = {
        "definition": DEFINITION,
        "method_sources": {p: _sha256_file(Path(root) / p) for p in METHOD_SOURCES},
    }
    return _sha256_bytes(json.dumps(payload, sort_keys=True, default=str).encode())


def _git(*args: str, root: Path = Path(".")) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    """Refuse to run unless the preregistration is committed, unchanged and pushed."""
    doc = Path(root) / PREREG_DOC
    if not doc.exists():
        raise PreregistrationError(f"{PREREG_DOC} does not exist; write and push it before running")
    expected = definition_fingerprint(root)
    if f"Definition fingerprint: `{expected}`" not in doc.read_text(encoding="utf-8"):
        raise PreregistrationError(
            "the preregistration does not embed this definition's fingerprint "
            f"({expected[:16]}...): the definition or the method sources changed after "
            "registration, or the document was not updated. Nothing is run."
        )
    if _git("ls-files", "--error-unmatch", str(PREREG_DOC), root=root).returncode != 0:
        raise PreregistrationError("the preregistration is not tracked by git")
    tracked = [str(PREREG_DOC), *METHOD_SOURCES]
    dirty = _git("status", "--porcelain", "--", *tracked, root=root).stdout.strip()
    if dirty:
        raise PreregistrationError(f"registered files have uncommitted changes:\n{dirty}")
    commit = _git("log", "-1", "--format=%H", "--", str(PREREG_DOC), root=root).stdout.strip()
    if not commit:
        raise PreregistrationError("no commit contains the preregistration")
    if fetch:
        _git("fetch", "origin", "main", "--quiet", root=root)
    pushed = _git("merge-base", "--is-ancestor", commit, "origin/main", root=root).returncode == 0
    if not pushed:
        raise PreregistrationError(
            f"preregistration commit {commit[:12]} is not an ancestor of origin/main: "
            "push it before executing. This is mandatory."
        )
    return {
        "preregistration_document": str(PREREG_DOC),
        "preregistration_sha256": _sha256_file(doc),
        "preregistration_commit": commit,
        "pushed_to_origin_main": True,
        "definition_fingerprint": expected,
    }


# ── inputs and the firewall ──────────────────────────────────────────────────

def holdout_window(root: Path = Path(".")) -> tuple[Date, Date]:
    """The sealed window, read from EXP-006's own recorded plan."""
    holdout = json.loads((Path(root) / FROZEN_METRICS).read_text())["holdout"]
    return Date.fromisoformat(holdout["start"]), Date.fromisoformat(holdout["end"])


def arm_firewall(root: Path = Path(".")) -> tuple[Date, Date]:
    start, end = holdout_window(root)
    FIREWALL.arm_window(start, end)
    return start, end


def load_frozen_predictions(root: Path = Path(".")) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The frozen gradient-boosting predictions, checked against the definition."""
    path = Path(root) / FROZEN_PREDICTIONS
    raw = pd.read_parquet(path)
    spec = DEFINITION["input"]
    frame = raw[raw["model"] == spec["model"]].copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    FIREWALL.assert_clear(frame, context="EXP-009A frozen predictions")
    if len(frame) != spec["rows"]:
        raise ValueError(f"expected {spec['rows']} frozen rows for {spec['model']}, found {len(frame)}")
    if (str(frame["date"].min()), str(frame["date"].max())) != (
        spec["first_prediction_date"], spec["last_prediction_date"]
    ):
        raise ValueError("frozen prediction date range differs from the definition")
    ordered = frame.sort_values(["date", "symbol"])[["date", "symbol", "prediction"]]
    rows_hash = _sha256_bytes(
        pd.util.hash_pandas_object(ordered.astype({"date": str}), index=False).to_numpy().tobytes()
    )
    return frame, {
        "file": str(FROZEN_PREDICTIONS),
        "file_sha256": _sha256_file(path),
        "model": spec["model"],
        "rows": int(len(frame)),
        "symbols": int(frame["symbol"].nunique()),
        "first_date": str(frame["date"].min()),
        "last_date": str(frame["date"].max()),
        "model_rows_sha256": rows_hash,
    }


def build_returns_panel(
    last_date: Date, *, root: Path = Path("."), use_cache: bool = True
) -> pd.DataFrame:
    """Forward 5-session returns and dollar volume, capped before the holdout.

    Rebuilt with the same `DatasetBuilder` EXP-006 used, from the local raw
    store, but requesting only the labels needed here and cutting the frame at
    `last_date`. The builder reads prices past `last_date` internally (a forward
    return needs them); no row dated after it leaves this function, and none
    reaches the holdout.
    """
    start, _ = arm_firewall(root)
    if last_date >= start:
        raise HoldoutBreach(f"panel end {last_date} is not before the holdout start {start}")
    cache = Path(root) / RETURNS_PANEL_CACHE
    if use_cache and cache.exists():
        panel = pd.read_parquet(cache)
    else:
        from src.quant.datasets.store import RawStore
        from src.quant.features.registry import REGISTRY
        from src.quant.pit.dataset import DatasetBuilder
        from src.quant.pit.universe import UniverseHistory

        store = RawStore(Path(root) / "data/research")
        universe = UniverseHistory.load(Path(root) / "data/research" / "universe")
        dataset = DatasetBuilder(store, universe).build(
            start=Date(2014, 4, 1), end=last_date,
            features=REGISTRY.per_symbol_names()[:3],
            labels=["fwd_ret_5", "fwd_ret_21"],
            step_sessions=5, workers=6, run_guards=False,
        )
        panel = dataset.frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
        cache.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(cache, compression="zstd")
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    panel = panel[panel["date"] <= last_date].reset_index(drop=True)
    FIREWALL.assert_clear(panel, context="EXP-009A returns panel")
    return panel


def panel_content_hash(panel: pd.DataFrame) -> str:
    cols = panel[["date", "symbol", "dollar_volume", "fwd_ret_5"]].astype({"date": str})
    ordered = cols.sort_values(["date", "symbol"])
    return _sha256_bytes(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes())


def panel_integrity(predictions: pd.DataFrame, panel: pd.DataFrame) -> dict[str, Any]:
    """The rebuilt panel must be the panel EXP-006 traded on.

    Every prediction row must find a forward return, and the within-date rank of
    the rebuilt 21-session return must equal the label stored with the
    predictions. `fwd_ret_21` is used *only* here, as an identity check — never
    in a metric.
    """
    from scipy.stats import spearmanr

    merged = predictions.merge(
        panel[["date", "symbol", "fwd_ret_5", "fwd_ret_21"]], on=["date", "symbol"], how="left"
    )
    unmatched = int(merged["fwd_ret_5"].isna().sum())
    correlations = [
        spearmanr(g["fwd_ret_21"], g["fwd_rank_21"])[0]
        for _, g in merged.dropna(subset=["fwd_ret_21"]).groupby("date")
    ]
    return {
        "prediction_rows_without_return": unmatched,
        "label_rank_agreement_mean_spearman": float(np.nanmean(correlations)),
        "label_rank_agreement_min_spearman": float(np.nanmin(correlations)),
        "dates_checked": len(correlations),
        "passed": bool(unmatched == 0 and np.nanmin(correlations) > 1 - 1e-9),
    }


# ── the cells ────────────────────────────────────────────────────────────────

def _backtest(
    predictions: pd.DataFrame, panel: pd.DataFrame, cell: dict[str, Any],
    half_spread_bps: float, *, record_weights: bool = False,
) -> BacktestResult:
    engine = DEFINITION["engine"]
    return run_backtest(
        predictions[["date", "symbol", "prediction"]],
        panel[["date", "symbol", "dollar_volume", engine["forward_return_column"]]],
        config=BacktestConfig(
            quantiles=engine["quantiles"],
            long_short=engine["long_short"],
            capital=engine["capital"],
            rebalance_step_sessions=engine["rebalance_step_sessions"],
            cost_model=SimpleCostModel(
                commission_bps=engine["commission_bps"], half_spread_bps=half_spread_bps,
                impact_coefficient=engine["impact_coefficient"],
            ),
            max_weight=engine["max_weight"],
            min_names=engine["min_names"],
            execution_lag_periods=engine["execution_lag_periods"],
            weight_rule=rule_from_spec(cell),
            record_weights=record_weights,
        ),
        forward_return_column=engine["forward_return_column"],
    )


def verify_baseline_reproduction(control: BacktestResult, root: Path = Path(".")) -> dict[str, Any]:
    """The control must reproduce EXP-006's recorded gradient-boosting backtest."""
    recorded = json.loads((Path(root) / FROZEN_METRICS).read_text())["labels"]["fwd_rank_21"][
        "backtests"]["gradient_boosting"]["metrics"]
    spec = DEFINITION["criteria"]["validity"]
    rows, ok = [], True
    for key in spec["compared"]:
        mine, theirs = control.metrics.get(key), recorded.get(key)
        close = (
            mine == theirs if key == "periods"
            else theirs is not None and mine is not None
            and math.isclose(mine, theirs, rel_tol=spec["tolerance_relative"], abs_tol=1e-12)
        )
        ok &= bool(close)
        rows.append({"metric": key, "reproduced": mine, "recorded_exp006": theirs, "match": bool(close)})
    return {"passed": ok, "compared": rows}


def fold_of_dates(predictions: pd.DataFrame) -> dict[Date, int]:
    return predictions.groupby("date")["fold"].first().astype(int).to_dict()


def newey_west_mean_t(values: np.ndarray, lags: int) -> dict[str, float]:
    """t-statistic of the mean with a Bartlett-kernel HAC standard error."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    centred = x - x.mean()
    variance = float(centred @ centred) / n
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1.0)
        variance += 2.0 * weight * float(centred[lag:] @ centred[:-lag]) / n
    se = math.sqrt(max(variance, 0.0) / n)
    return {"mean": float(x.mean()), "hac_se": se, "hac_t": float(x.mean() / se) if se > 0 else float("nan"),
            "lags": lags}


def paired_block_bootstrap_sharpe_diff(
    treatment: np.ndarray, control: np.ndarray, *, block: int, draws: int, seed: int,
    periods_per_year: float, one_sided_level: float,
) -> dict[str, Any]:
    """Circular moving-block bootstrap of (Sharpe_treatment - Sharpe_control), paired."""
    t, c = np.asarray(treatment, float), np.asarray(control, float)
    n = len(t)
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    starts = rng.integers(0, n, size=(draws, n_blocks))
    index = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(draws, -1)[:, :n]

    def sharpe(matrix: np.ndarray) -> np.ndarray:
        std = matrix.std(axis=1, ddof=1)
        return np.where(std > 0, matrix.mean(axis=1) / std, np.nan) * math.sqrt(periods_per_year)

    diff = sharpe(t[index]) - sharpe(c[index])
    point = float(
        (t.mean() / t.std(ddof=1) - c.mean() / c.std(ddof=1)) * math.sqrt(periods_per_year)
    )
    lower = float(np.nanquantile(diff, 1.0 - one_sided_level))
    return {
        "point_estimate": point,
        "bootstrap_mean": float(np.nanmean(diff)),
        "bootstrap_sd": float(np.nanstd(diff, ddof=1)),
        "one_sided_lower_bound": lower,
        "one_sided_level": one_sided_level,
        "share_of_draws_at_or_below_zero": float(np.nanmean(diff <= 0.0)),
        "ci95_two_sided": [float(np.nanquantile(diff, 0.025)), float(np.nanquantile(diff, 0.975))],
        "block_length": block,
        "draws": draws,
    }


def fold_table(periods: pd.DataFrame, fold_map: dict[Date, int]) -> list[dict[str, Any]]:
    frame = periods.assign(fold=[fold_map.get(d) for d in periods["date"]])
    out = []
    for fold, g in frame.groupby("fold"):
        net = g["net_return"].to_numpy()
        out.append({
            "fold": int(fold),
            "periods": int(len(g)),
            "first_date": str(g["date"].min()),
            "last_date": str(g["date"].max()),
            "mean_gross_return_bp": float(g["gross_return"].mean() * 1e4),
            "mean_net_return_bp": float(net.mean() * 1e4),
            "net_sharpe": float(net.mean() / net.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR))
            if len(net) > 2 and net.std(ddof=1) > 0 else None,
            "mean_one_way_turnover": float(g["turnover"].mean()),
            "mean_cost_bp": float(g["cost_return"].mean() * 1e4),
        })
    return out


def holdings_metrics(
    result: BacktestResult, lagged: pd.DataFrame, panel: pd.DataFrame, capital: float
) -> dict[str, Any]:
    """Membership, holding duration, concentration, rank capture and capacity proxy."""
    weights = result.weights
    if weights is None:
        raise ValueError("backtest was run without record_weights")
    dates = sorted(weights["date"].unique())
    by_date = {d: g.set_index("symbol")["weight"] for d, g in weights.groupby("date")}

    changed_long, changed_short, retained_share = [], [], []
    for previous, current in zip(dates[:-1], dates[1:]):
        p, c = by_date[previous], by_date[current]
        for series_p, series_c, bucket in ((p[p > 0], c[c > 0], changed_long),
                                           (p[p < 0], c[c < 0], changed_short)):
            bucket.append(len(set(series_p.index) - set(series_c.index)) / max(len(series_p), 1))

    # Completed holding spells per name and side, in rebalance periods.
    spells: list[int] = []
    open_spell: dict[tuple[str, int], int] = {}
    for d in dates:
        current = {(s, int(np.sign(w))) for s, w in by_date[d].items()}
        for key in list(open_spell):
            if key not in current:
                spells.append(open_spell.pop(key))
        for key in current:
            open_spell[key] = open_spell.get(key, 0) + 1
    completed = np.asarray(spells, dtype=float)

    longs = [(s > 0).sum() for s in by_date.values()]
    shorts = [(s < 0).sum() for s in by_date.values()]
    eff_long = [1.0 / float((s[s > 0] ** 2).sum() / (s[s > 0].sum() ** 2)) for s in by_date.values()]
    eff_short = [1.0 / float((s[s < 0] ** 2).sum() / (s[s < 0].sum() ** 2)) for s in by_date.values()]

    # Rank capture: predicted percentile of the names actually held.
    pct = lagged.copy()
    pct["pct"] = pct.groupby("date")["prediction"].rank(pct=True)
    pct_lookup = pct.set_index(["date", "symbol"])["pct"]
    joined = weights.join(pct_lookup, on=["date", "symbol"])
    long_pct = float(joined.loc[joined["weight"] > 0, "pct"].mean())
    short_pct = float(joined.loc[joined["weight"] < 0, "pct"].mean())

    # Capacity proxy: participation of each traded name in its own daily dollar volume.
    volume = panel.set_index(["date", "symbol"])["dollar_volume"]
    participation = []
    for previous, current in zip(dates[:-1], dates[1:]):
        delta = (by_date[current].reindex(by_date[current].index.union(by_date[previous].index)).fillna(0.0)
                 - by_date[previous].reindex(by_date[current].index.union(by_date[previous].index)).fillna(0.0)).abs()
        traded = delta[delta > 0]
        for symbol, amount in traded.items():
            dv = volume.get((current, symbol))
            if dv is not None and np.isfinite(dv) and dv > 0:
                participation.append(amount * capital / dv)
    p = np.asarray(participation)
    p95 = float(np.percentile(p, 95)) if len(p) else None

    return {
        "names_replaced_per_rebalance": {
            "long_leg_fraction": float(np.mean(changed_long)),
            "short_leg_fraction": float(np.mean(changed_short)),
            "both_legs_fraction": float((np.mean(changed_long) + np.mean(changed_short)) / 2.0),
        },
        "holding_duration_periods": {
            "mean_completed_spell": float(completed.mean()) if len(completed) else None,
            "median_completed_spell": float(np.median(completed)) if len(completed) else None,
            "share_of_spells_one_period": float(np.mean(completed == 1)) if len(completed) else None,
            "completed_spells": int(len(completed)),
            "note": "spells still open at the last date are excluded",
        },
        "breadth": {
            "mean_long_names": float(np.mean(longs)), "mean_short_names": float(np.mean(shorts)),
            "mean_effective_n_long": float(np.mean(eff_long)),
            "mean_effective_n_short": float(np.mean(eff_short)),
            "max_abs_weight": float(weights["weight"].abs().max()),
        },
        "rank_capture": {
            "mean_predicted_percentile_of_longs": long_pct,
            "mean_predicted_percentile_of_shorts": short_pct,
            "note": "how deep into the predicted ranking the held names sit; buffers hold names "
                    "below the entry cutoff, so this falls by design",
        },
        "capacity_proxy": {
            "median_participation_of_traded_names": float(np.median(p)) if len(p) else None,
            "p95_participation": p95,
            "capital": capital,
            "capital_at_1pct_p95_participation": (capital * 0.01 / p95) if p95 else None,
            "note": "trade size / same-day dollar volume at the reference capital; a scale "
                    "indicator, not a market-impact model",
        },
    }


def classify_cell(
    cell: dict[str, Any], control_metrics: dict[str, Any], metrics: dict[str, Any],
    gross_retention: float, bootstrap: dict[str, Any], folds_improved: int,
) -> dict[str, Any]:
    """Apply the preregistered criteria. Pure function of the numbers passed in."""
    t1 = bool(metrics["annualised_turnover"] <= 0.70 * control_metrics["annualised_turnover"])
    t2 = bool(gross_retention >= 0.75)
    t3 = bool(bootstrap["one_sided_lower_bound"] > 0.0)
    t4 = bool(folds_improved >= 6)
    if t1 and t2 and t3 and t4:
        label = "MECHANISM_CONFIRMED"
    elif t1 and not t2:
        label = "EDGE_LOST"
    elif not t1:
        label = "INSUFFICIENT_TURNOVER_CUT"
    else:
        label = "NO_RELIABLE_NET_GAIN"
    return {
        "T1_turnover_cut": t1,
        "T1_turnover_ratio_to_control": metrics["annualised_turnover"] / control_metrics["annualised_turnover"],
        "T2_gross_retention": t2,
        "T2_retention_ratio": gross_retention,
        "T3_net_gain_paired_bootstrap": t3,
        "T4_fold_consistency": t4,
        "T4_folds_improved": folds_improved,
        "classification": label,
        "promotion": "NOT ASSESSED",
    }


def _git_state(root: Path) -> dict[str, Any]:
    sha = _git("rev-parse", "HEAD", root=root).stdout.strip()
    dirty = _git("status", "--porcelain", root=root).stdout.strip()
    return {"git_commit": sha, "git_dirty": bool(dirty)}


def run_study(root: Path = Path("."), *, output: Optional[Path] = None) -> dict[str, Any]:
    """Execute EXP-009A. Refuses to run without a pushed preregistration."""
    began = time.perf_counter()
    root = Path(root)
    output = output or (root / OUTPUT_DIR)
    gate = prereg_gate(root)                                    # mandatory, before anything is read

    start, end = arm_firewall(root)
    predictions, input_info = load_frozen_predictions(root)
    last = Date.fromisoformat(DEFINITION["input"]["last_prediction_date"])
    panel = build_returns_panel(last, root=root)
    integrity = panel_integrity(predictions, panel)
    if not integrity["passed"]:
        raise RuntimeError(f"rebuilt returns panel does not match EXP-006's labels: {integrity}")

    engine = DEFINITION["engine"]
    primary_bps = DEFINITION["costs"]["primary_half_spread_bps"]
    sweep = DEFINITION["costs"]["sweep_half_spread_bps"]
    fold_map = fold_of_dates(predictions)
    lagged = lagged_frame(predictions[["date", "symbol", "prediction"]],
                          panel[["date", "symbol", "dollar_volume", "fwd_ret_5"]],
                          lag=engine["execution_lag_periods"])
    factors = _read_factors(root)

    results: dict[str, BacktestResult] = {}
    for cell in DEFINITION["cells"]:
        results[cell["id"]] = _backtest(predictions, panel, cell, primary_bps, record_weights=True)

    control = results["A_immediate"]
    reproduction = verify_baseline_reproduction(control, root)
    manifest: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID, "parent": PARENT_EXPERIMENT,
        "status": DEFINITION["status"], **gate, **_git_state(root),
        "input": input_info, "returns_panel_sha256": panel_content_hash(panel),
        "panel_integrity": integrity, "baseline_reproduction": reproduction,
        "holdout": {"start": str(start), "end": str(end), "touched": False,
                    "firewall": FIREWALL.status()},
    }
    if not reproduction["passed"]:
        manifest["decision"] = "INVALID - control did not reproduce EXP-006; no treatment reported"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    control_net = control.periods["net_return"].to_numpy()
    control_gross_mean = float(control.periods["gross_return"].mean())
    control_fold = fold_table(control.periods, fold_map)
    n_treat = DEFINITION["inference"]["n_treatments"]
    level = 1.0 - DEFINITION["inference"]["family_alpha"] / n_treat

    cell_out: dict[str, Any] = {}
    trial_sharpes = []
    for cell in DEFINITION["cells"]:
        result = results[cell["id"]]
        periods = result.periods
        sweeps = [
            {"half_spread_bps": bps,
             **{k: _backtest(predictions, panel, cell, bps).metrics.get(k) for k in
                ("gross_sharpe", "net_sharpe", "net_cagr", "annualised_turnover",
                 "cost_share_of_gross", "net_max_drawdown")}}
            for bps in sweep
        ]
        entry: dict[str, Any] = {
            "cell": cell,
            "rule_description": result.config.get("weight_rule", {"rule": "baseline quantile"}),
            "backtest_metrics_at_10bp": result.metrics,
            "gross_total_return_compounded": float(np.prod(1.0 + periods["gross_return"]) - 1.0),
            "cost_sweep": sweeps,
            "breakeven": breakeven_half_spread(periods),
            "fold_metrics": fold_table(periods, fold_map),
            "holdings": holdings_metrics(result, lagged, panel, engine["capital"]),
            "one_way_turnover_check_independent": independent_turnover(lagged) if cell["id"] == "A_immediate" else None,
        }
        if factors is not None:
            entry["factor_attribution"] = attribute_returns(
                result.net_returns, factors, periods_per_year=PERIODS_PER_YEAR,
                holding_periods=LabelGeometry(target="fwd_rank_21", horizon_sessions=21,
                                              step_sessions=5, embargo_sessions=0).block_length,
            ).as_dict()
        net = periods["net_return"].to_numpy()
        if net.std(ddof=1) > 0:
            trial_sharpes.append(float(net.mean() / net.std(ddof=1)))

        if cell["role"] == "treatment":
            ppy = PERIODS_PER_YEAR
            bootstrap = paired_block_bootstrap_sharpe_diff(
                net, control_net, block=DEFINITION["inference"]["block_length_periods"],
                draws=DEFINITION["inference"]["draws"], seed=DEFINITION["inference"]["seed"],
                periods_per_year=ppy, one_sided_level=level,
            )
            net_diff = net - control_net
            gross_diff = periods["gross_return"].to_numpy() - control.periods["gross_return"].to_numpy()
            cost_diff = periods["cost_return"].to_numpy() - control.periods["cost_return"].to_numpy()
            lags = DEFINITION["inference"]["hac_newey_west_lags"]
            fold_now = entry["fold_metrics"]
            improved = sum(
                1 for a, b in zip(fold_now, control_fold) if a["mean_net_return_bp"] > b["mean_net_return_bp"]
            )
            dnet_by_fold = [a["mean_net_return_bp"] * a["periods"] - b["mean_net_return_bp"] * b["periods"]
                            for a, b in zip(fold_now, control_fold)]
            total_gain = sum(dnet_by_fold)
            retention = float(periods["gross_return"].mean() / control_gross_mean)
            entry["versus_control"] = {
                "gross_retention_ratio": retention,
                "annualised_turnover_ratio": result.metrics["annualised_turnover"]
                / control.metrics["annualised_turnover"],
                "delta_net_sharpe_10bp": result.metrics["net_sharpe"] - control.metrics["net_sharpe"],
                "delta_gross_sharpe": result.metrics["gross_sharpe"] - control.metrics["gross_sharpe"],
                "paired_bootstrap_net_sharpe": bootstrap,
                "hac_mean_net_difference": newey_west_mean_t(net_diff, lags),
                "hac_mean_gross_difference": newey_west_mean_t(gross_diff, lags),
                "hac_mean_cost_difference": newey_west_mean_t(cost_diff, lags),
                "folds_where_net_mean_improved": improved,
                "largest_single_fold_share_of_total_net_gain": (
                    float(max(dnet_by_fold) / total_gain) if total_gain > 0 else None
                ),
            }
            entry["criteria"] = classify_cell(cell, control.metrics, result.metrics,
                                              retention, bootstrap, improved)
        cell_out[cell["id"]] = entry

    trials = DEFINITION["trials"]["cumulative_evaluations"]
    for cell_id, entry in cell_out.items():
        entry["deflated_sharpe"] = deflated_sharpe_ratio(
            results[cell_id].periods["net_return"].to_numpy(), trials=trials,
            periods_per_year=PERIODS_PER_YEAR, trial_sharpes=trial_sharpes,
        ).as_dict()

    confirmed = {
        cid: e["versus_control"]["gross_retention_ratio"]
        for cid, e in cell_out.items()
        if e.get("criteria", {}).get("classification") == "MECHANISM_CONFIRMED"
    }
    carried = max(confirmed, key=confirmed.get) if confirmed else None
    decision = {
        "confirmed_cells": sorted(confirmed),
        "carried_forward": carried,
        "summary": (
            f"{carried} carried forward as the frozen turnover mechanism" if carried
            else "no cell met all four preregistered criteria; no mechanism is frozen"
        ),
        "promotion": "NOT ASSESSED",
    }

    manifest.update({
        "compute": {
            "wall_seconds": round(time.perf_counter() - began, 1),
            "cpu_count": os.cpu_count(), "platform": platform.platform(),
            "python": platform.python_version(), "seed": DEFINITION["inference"]["seed"],
            "bootstrap_draws": DEFINITION["inference"]["draws"],
            "trials_counted_for_deflation": trials,
        },
        "definition_sha256": _sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
        "module_sha256": _sha256_file(Path(__file__)),
        "rules_sha256": _sha256_file(root / "src/quant/backtest/rules.py"),
        "decision": decision,
    })
    payload = {"definition": DEFINITION, "cells": cell_out, "decision": decision}

    output.mkdir(parents=True, exist_ok=True)
    _write(output, "definition.json", DEFINITION)
    _write(output, "manifest.json", manifest)
    _write(output, "metrics.json", payload)
    for cell_id, result in results.items():
        FIREWALL.assert_clear(result.periods, context=f"EXP-009A {cell_id} periods")
        result.periods.to_parquet(output / f"periods_{cell_id}.parquet", compression="zstd")
        FIREWALL.assert_clear(result.weights, context=f"EXP-009A {cell_id} membership")
        result.weights.to_parquet(output / f"membership_{cell_id}.parquet", compression="zstd")
    pd.DataFrame([
        {"cell": cid, **{k: v for k, v in e["backtest_metrics_at_10bp"].items()
                         if not isinstance(v, (dict, list))}}
        for cid, e in cell_out.items()
    ]).to_parquet(output / "summary.parquet", compression="zstd")
    return {"manifest": manifest, "metrics": payload}


def run_diagnostics(root: Path = Path("."), *, output: Optional[Path] = None) -> dict[str, Any]:
    """Phase-2 turnover forensics on the frozen baseline. Reads no forward return.

    Not gated by the preregistration: it evaluates no treatment, computes no
    comparative metric and cannot influence any threshold; the baseline's own
    numbers were recorded in EXP-006 before it ran.
    """
    root = Path(root)
    output = output or (root / OUTPUT_DIR)
    arm_firewall(root)
    predictions, input_info = load_frozen_predictions(root)
    panel = build_returns_panel(Date.fromisoformat(DEFINITION["input"]["last_prediction_date"]), root=root)
    integrity = panel_integrity(predictions, panel)
    if not integrity["passed"]:
        raise RuntimeError(f"rebuilt returns panel does not match EXP-006's labels: {integrity}")

    engine = DEFINITION["engine"]
    control_cell = DEFINITION["cells"][0]
    sweep = {}
    for bps in DEFINITION["costs"]["sweep_half_spread_bps"]:
        r = _backtest(predictions, panel, control_cell, bps)
        sweep[str(bps)] = {k: r.metrics.get(k) for k in (
            "gross_sharpe", "net_sharpe", "net_cagr", "annualised_turnover",
            "cost_share_of_gross", "net_max_drawdown", "total_cost_return")}
        if bps == DEFINITION["costs"]["primary_half_spread_bps"]:
            primary = r
    reproduction = verify_baseline_reproduction(primary, root)

    lagged = lagged_frame(predictions[["date", "symbol", "prediction"]],
                          panel[["date", "symbol", "dollar_volume", "fwd_ret_5"]],
                          lag=engine["execution_lag_periods"])
    independent = independent_turnover(lagged)
    universe_flag = panel[["date", "symbol", "in_universe"]]
    decomposition = decompose_turnover(lagged, universe_flag=universe_flag)
    gross = primary.periods["gross_return"].to_numpy()
    payload = {
        "experiment_id": EXPERIMENT_ID, "phase": "turnover forensics on the frozen baseline",
        "reads_forward_returns_for_decomposition": False,
        "input": input_info, "panel_integrity": integrity,
        "baseline_reproduction": reproduction,
        "engine_turnover": {k: primary.metrics[k] for k in (
            "mean_turnover", "annualised_turnover", "mean_turnover_round_trip",
            "annualised_turnover_round_trip", "mean_names")},
        "independent_turnover": independent,
        "independent_vs_engine_relative_difference": abs(
            independent["mean_one_way_turnover"] / primary.metrics["mean_turnover"] - 1.0),
        "independent_vs_engine_note": (
            "independent derivation (exact integer rank cutoffs, its own turnover loop, the engine's "
            "max-weight cap) vs the engine; agreement is to floating-point precision"),
        "cost_sweep_baseline": sweep,
        "gross_total_return_arithmetic_sum": float(gross.sum()),
        "gross_total_return_compounded": float(np.prod(1.0 + gross) - 1.0),
        "breakeven": breakeven_half_spread(primary.periods),
        "decomposition": decomposition,
    }
    output.mkdir(parents=True, exist_ok=True)
    _write(output, "turnover_diagnostics.json", payload)
    return payload


def run_robustness(root: Path = Path("."), *, output: Optional[Path] = None) -> dict[str, Any]:
    """Post-hoc, NON-preregistered robustness of the recorded results.

    Reads the saved period and membership files and the returns panel; fits
    nothing, adds no cell, and changes no classification. It exists because a
    preregistered result can be right for the wrong reason, and the reader should
    see where the gross difference came from: which leg, whether two thin dates
    or one strong fold carry it, and whether exposure changed. Everything here is
    exploratory and is labelled so in the output.
    """
    root = Path(root)
    output = output or (root / OUTPUT_DIR)
    arm_firewall(root)
    predictions, _ = load_frozen_predictions(root)
    panel = build_returns_panel(Date.fromisoformat(DEFINITION["input"]["last_prediction_date"]), root=root)
    fold_map = fold_of_dates(predictions)
    thin = {Date(2019, 9, 17), Date(2020, 2, 17)}
    returns = panel.set_index(["date", "symbol"])["fwd_ret_5"]

    def _sharpe(x: np.ndarray) -> Optional[float]:
        return float(x.mean() / x.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR)) if len(x) > 2 and x.std(ddof=1) > 0 else None

    out: dict[str, Any] = {
        "label": "EXPLORATORY - not preregistered - changes no classification",
        "thin_dates_excluded_in_variant": sorted(str(d) for d in thin),
        "cells": {},
    }
    for cell in DEFINITION["cells"]:
        cid = cell["id"]
        periods = pd.read_parquet(output / f"periods_{cid}.parquet")
        weights = pd.read_parquet(output / f"membership_{cid}.parquet")
        weights["fwd"] = returns.reindex(pd.MultiIndex.from_frame(weights[["date", "symbol"]])).to_numpy()
        weights["contribution"] = weights["weight"] * weights["fwd"].fillna(0.0)
        by_leg = weights.assign(leg=np.where(weights["weight"] > 0, "long", "short")).groupby(
            ["date", "leg"])["contribution"].sum().unstack(fill_value=0.0)
        frame = periods.assign(fold=[fold_map.get(d) for d in periods["date"]]).merge(
            by_leg.reset_index(), on="date", how="left")
        keep_thin = ~frame["date"].isin(thin)
        keep_fold5 = frame["fold"] != 5
        out["cells"][cid] = {
            "mean_gross_bp": float(frame["gross_return"].mean() * 1e4),
            "long_leg_contribution_bp": float(frame["long"].mean() * 1e4),
            "short_leg_contribution_bp": float(frame["short"].mean() * 1e4),
            "mean_gross_exposure": float(frame["gross_exposure"].mean()),
            "mean_net_exposure": float(frame["net_exposure"].mean()),
            "net_sharpe_all": _sharpe(frame["net_return"].to_numpy()),
            "net_sharpe_excluding_thin_dates": _sharpe(frame.loc[keep_thin, "net_return"].to_numpy()),
            "net_sharpe_excluding_fold_5": _sharpe(frame.loc[keep_fold5, "net_return"].to_numpy()),
            "gross_sharpe_excluding_thin_dates": _sharpe(frame.loc[keep_thin, "gross_return"].to_numpy()),
            "gross_sharpe_excluding_fold_5": _sharpe(frame.loc[keep_fold5, "gross_return"].to_numpy()),
            "mean_gross_bp_excluding_thin_dates": float(frame.loc[keep_thin, "gross_return"].mean() * 1e4),
            "mean_gross_bp_excluding_fold_5": float(frame.loc[keep_fold5, "gross_return"].mean() * 1e4),
            "share_of_periods_with_positive_gross": float((frame["gross_return"] > 0).mean()),
        }
    control = out["cells"]["A_immediate"]
    for cid, entry in out["cells"].items():
        entry["gross_bp_excluding_thin_dates_vs_control_ratio"] = (
            entry["mean_gross_bp_excluding_thin_dates"] / control["mean_gross_bp_excluding_thin_dates"])
        entry["gross_bp_excluding_fold_5_vs_control_ratio"] = (
            entry["mean_gross_bp_excluding_fold_5"] / control["mean_gross_bp_excluding_fold_5"])
    _write(output, "robustness_exploratory.json", out)
    return out


def _read_factors(root: Path):
    try:
        from src.quant.datasets.store import RawStore

        return RawStore(Path(root) / "data/research").read("french_factors_daily")
    except Exception:  # noqa: BLE001 - attribution is descriptive; absence is recorded, not faked
        return None


def _write(directory: Path, name: str, payload: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
