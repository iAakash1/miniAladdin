"""EXP-010B — horizon / rebalance-cadence study on the frozen EXP-010A predictions.

The model predicts a 21-session ranking but EXP-006..010A trade it every 5
sessions.  This study changes only the *dates on which the book is rebuilt*:

* B0 — every 5th session (the frozen EXP-010A cadence);
* B1 — every 21st session, counted on the global trading calendar.

Nothing is refit.  Both arms read the same ten frozen prediction files, the same
universe, the same top-k-dropout portfolio rule, the same costs and the same
engine; only the schedule (and the forward-return column that matches the holding
period) differs.  Every seed is reported; no seed is selected; the sealed holdout
is armed before any data is read.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from datetime import date as Date
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.backtest.costs import SimpleCostModel
from src.quant.backtest.engine import TRADING_DAYS, BacktestConfig, BacktestResult, run_backtest
from src.quant.backtest.rules import rule_from_spec
from src.quant.models.registry import dependency_versions
from src.quant.pit.calendar import TradingCalendar
from src.quant.study import exp009a, exp009b, exp010a, prereg
from src.quant.study.firewall import FIREWALL, HoldoutBreach

EXPERIMENT_ID = "EXP-010B"
PARENT_EXPERIMENT = "EXP-010A"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_010B_PREREGISTRATION.md")
PARENT_DIR = Path("experiments") / "EXP-010A"
DAILY_PANEL_CACHE = Path("data/research/derived/exp010b_daily_panel.parquet")
CALENDAR_CACHE = Path("data/research/derived/exp010b_calendar.json")

SEEDS = exp010a.SEEDS
COSTS = exp010a.COSTS
PRIMARY_BPS = 10.0
PORTFOLIO = dict(exp010a.PORTFOLIO)
INFORMATION_DELAY_SESSIONS = 5
GRID_STEP_SESSIONS = 5
ARMS: dict[str, dict[str, Any]] = {
    "B0": {"step_sessions": 5, "forward_return_column": "fwd_ret_5"},
    "B1": {"step_sessions": 21, "forward_return_column": "fwd_ret_21"},
}
FIRST_PREDICTION_DATE = Date(2017, 5, 5)
LAST_PREDICTION_DATE = Date(2025, 5, 9)
EXPECTED_REBALANCES = {"B0": 403, "B1": 96}
EXPECTED_FIRST_REBALANCE = "2017-05-12"
EXPECTED_LAST_REBALANCE = {"B0": "2025-05-09", "B1": "2025-04-17"}

# EXP-010A results, used only as descriptive context (they define no threshold of significance).
NOISE_FLOOR = {
    "mean_rank_ic": {"sample_std": 0.001583, "p95_minus_p05": 0.004156},
    "net_sharpe_10bp": {"sample_std": 0.081651, "p95_minus_p05": 0.219416},
    "annualised_turnover": {"sample_std": 0.019217, "p95_minus_p05": 0.050376},
}
EXP010A_MEAN_FOLD_IC = [-0.0146, 0.0402, 0.0545, 0.0315, -0.0074, 0.0324, 0.0396, 0.0811]

PARENT_ARTIFACT_SHA256 = {
    "definition.json": "a5dc4f6dec1bf7ec97039252a645599e1c92ea6ebfa79f0b32262b698e81c8ca",
    "config.json": "0565e0d9af7e5b4a53bd11f1a3ef09e00bda5e2c9d207540c35bd3e79a40c67f",
    "manifest.json": "46a569adc94afd7ed52dd560baaa2c95979ee9ea31684dcf969fe6e756f942d9",
    "metrics.json": "a7663e9c61f6f5a80654c037e0b279ff2caa317e7ea61c52d410120235c40025",
    "per_seed_metrics.csv": "81296585f20d9d6d68d9568e7bc99483b21b1669bcd18c3e691ac90900c28d7c",
    "fold_metrics.csv": "f2c4c2c954f662415bdbf27be15a6881d460693f14e57dc974fdf91844a4b4d9",
    "prediction_hashes.json": "1ab4e9f285f702b0c5009444ca4f1b6a3a6aae7e87a6d102a8578b8088b88a26",
}
PARENT_PREDICTION_SHA256 = {
    0: "127555e4ab24152b6fe266ea98310b18799a605b099ebe590852052c314cf945",
    1: "ea4eeda09baa745cc34ba04455ea44c68ed28581b9e7153cd939cdc98948718b",
    2: "c83c0e96a307db62d15e146dc1020a4527eab57a538c9fcd449618a9ee0bcd9e",
    3: "5fcc520c209b2e8c39af4cf2000f2935a74bc9105a79e387919d2841aec2367e",
    4: "8dccd3c6e43ef42b1f5295d2bb3844c420223226be04ac110c7a0dd02a22fa05",
    5: "d63cb41f7426a075f7573e7e027a9e7aada9ae2e6ec47e94e1ec26637918b5c9",
    6: "7fcb0d76935ef1f25d282a22c49457dadef39f3b029284f0ae9ad110259fc9a4",
    7: "ae7813459def634b8cc59f773a07283090d0d55ed8f6d5ff932e3e2400549104",
    8: "f3bf17f7d012e04dfe7f72dc89df003c54706b783217f49f8202ee7d2c442e0d",
    9: "f50289c57e893e9046e00628b582b7648c6ec22885af57c6fddea24619ffeb0e",
}
PARENT_DEFINITION_FINGERPRINT = "0b18e0ad7d90905988988a8cdd8d9251522000d7503d41045096c639bf64bba0"
STEP5_RETURNS_PANEL_SHA256 = exp009b.DEFINITION["data"]["returns_panel_sha256"]
# Pinned once from the first deterministic build, then verified on every load.
DAILY_PANEL_SHA256 = "5f00d3dfc0e6b624d231dc86d52e001aab34c0be313a9226cb91f279057e3001"
CALENDAR_SHA256 = "b39ca1cdd13415b48a598270a56fcade03638286b5ba421d9a718e588327f538"

PRIMARY_PAIRED_METRICS = (
    "net_sharpe_10bp", "annualised_turnover", "gross_sharpe", "net_max_drawdown", "cost_share_of_gross",
)
INTERPRETATION = {
    "unit": "EXP-010A net-Sharpe seed sample SD (0.081651): a scale for 'material', not a significance test",
    "turnover_materially_reduced": {
        "median_relative_change_at_most": -0.25, "seeds_with_lower_turnover_at_least": 10,
    },
    "net_sharpe_status": {
        "IMPROVED": "median paired difference >= unit AND at least 9 of 10 seeds positive",
        "DEGRADED": "median paired difference <= -unit",
        "PRESERVED": "otherwise",
    },
    "gross_equivalence": "absolute median paired gross-Sharpe difference < unit",
    "fold_reliance": (
        "for every fold f, the seed-median paired net-Sharpe difference recomputed on the pooled periods with fold f "
        "removed must stay > 0 when the status is IMPROVED and > -unit when PRESERVED"
    ),
    "labels": {
        "ECONOMICALLY_IMPROVED": "turnover materially reduced AND net status IMPROVED or PRESERVED AND fold-robust",
        "TURNOVER_REDUCED_SIGNAL_LOST": "turnover materially reduced AND net status DEGRADED",
        "CADENCE_EQUIVALENT": "turnover NOT materially reduced AND net status PRESERVED AND gross equivalent",
        "NO_STABLE_ECONOMIC_GAIN": "every other outcome, including a gain that depends on a single fold",
    },
    "promotion": "NOT ASSESSED",
}
UNIT = NOISE_FLOOR["net_sharpe_10bp"]["sample_std"]

DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "parent_experiment": PARENT_EXPERIMENT,
    "status": "EXPERIMENTAL - CADENCE STUDY - NO RETRAINING - PROMOTION NOT ASSESSED",
    "question": (
        "Does rebuilding the book every 21 sessions, the horizon the model was trained to rank, improve net economics "
        "or reduce turnover relative to the frozen 5-session cadence, using identical predictions and portfolio rules?"
    ),
    "inputs": {
        "parent_experiment": PARENT_EXPERIMENT,
        "parent_definition_fingerprint": PARENT_DEFINITION_FINGERPRINT,
        "parent_artifact_sha256": PARENT_ARTIFACT_SHA256,
        "prediction_sha256_by_seed": {str(seed): value for seed, value in PARENT_PREDICTION_SHA256.items()},
        "prediction_hash_function": "EXP-010A _prediction_hash over [date, symbol, fold, fwd_rank_21, prediction] sorted by date, symbol",
        "prediction_rows_per_seed": 100_246, "prediction_dates": 404,
        "first_prediction_date": str(FIRST_PREDICTION_DATE), "last_prediction_date": str(LAST_PREDICTION_DATE),
        "dataset_id": exp010a.DEFINITION["data"]["dataset_id"],
        "dataset_content_hash": exp010a.DEFINITION["data"]["dataset_content_hash"],
        "step5_returns_panel_sha256": STEP5_RETURNS_PANEL_SHA256,
        "daily_returns_panel_sha256": DAILY_PANEL_SHA256,
        "calendar_sha256": CALENDAR_SHA256,
        "regeneration": "only if a checkpoint is missing or fails its hash: rerun the unmodified EXP-010A runner; never edit EXP-010A",
        "retraining": "none",
    },
    "arms": {"B0": dict(ARMS["B0"]), "B1": dict(ARMS["B1"])},
    "calendar": {
        "source": "global observed trading calendar (sessions on which any ingested price bar exists), capped at the last prediction date",
        "information_delay_sessions": INFORMATION_DELAY_SESSIONS,
        "first_rebalance": "first prediction date + 5 sessions (same first date for both arms)",
        "schedule": "sessions[i0 + k * step_sessions] while the session <= last prediction date",
        "not_used": "month-end, approximate 4-week jumps, random dates, per-symbol row counts",
        "expected_rebalances": dict(EXPECTED_REBALANCES),
        "expected_first_rebalance": EXPECTED_FIRST_REBALANCE, "expected_last_rebalance": dict(EXPECTED_LAST_REBALANCE),
        "missing_tickers": "a missing name is absent from that date's book; it never shifts the schedule",
    },
    "signal_alignment": {
        "rule": (
            "the signal for a name at rebalance t is that name's latest frozen prediction dated <= t - 5 sessions "
            "(the same one-period, 5-session information delay B0 already has through the engine's lag)"
        ),
        "eligibility": (
            "a name is tradable at t if it is in the point-in-time universe at t, was scored at the latest prediction date "
            "<= t, has a signal under the rule above, and has a finite forward return for the arm's horizon"
        ),
        "engine_lag": "execution_lag_periods = 0 (the delay is applied by the alignment, identically for both arms)",
        "b0_reproduces_exp010a": "B0 metrics must equal the committed EXP-010A per-seed metrics to 1e-9 or the run aborts",
    },
    "portfolio": {
        **PORTFOLIO, "long_short": True, "engine": "EXP-009A engine settings unchanged except the two cadence fields",
        "changed_between_arms": ["rebalance_step_sessions", "forward_return_column"],
        "cost_half_spread_bps": list(COSTS), "primary_cost_bps": PRIMARY_BPS,
        "note": "the drop budget is per rebalance, so 10% of the book per 21 sessions is a lower per-session churn than per 5",
    },
    "metrics": {
        "per_seed_per_arm": [
            "gross Sharpe", "net Sharpe at 1/3/5/10/20 bp", "annualised one-way turnover", "cost share of gross",
            "net and gross maximum drawdown", "average completed holding duration (rebalances and sessions)",
            "names changed per rebalance", "number of rebalances", "gross and net total return and CAGR",
            "top and bottom leg membership retention", "effective number of names and maximum weight",
            "signal age and eligible names",
        ],
        "paired": {
            "definition": "B1 - B0 for the same seed", "primary": list(PRIMARY_PAIRED_METRICS),
            "statistics": ["mean", "median", "sample_std", "min", "max", "p05", "p95"],
            "sign_note": "net_max_drawdown is negative, so a positive difference is a shallower drawdown",
        },
        "folds": {
            "attribution": "a rebalance belongs to the fold of the latest frozen prediction date <= it",
            "reported": ["periods", "annualised gross and net return", "net Sharpe", "annualised turnover"],
            "leave_one_fold_out": "pooled paired net Sharpe with one fold removed, per seed",
        },
    },
    "noise_context": {
        "source": "EXP-010A ten-seed noise floor", **NOISE_FLOOR, "exp010a_mean_fold_rank_ic": EXP010A_MEAN_FOLD_IC,
        "use": "descriptive context only; no threshold of significance is derived from it",
    },
    "interpretation": INTERPRETATION,
    "known_limits": [
        "the seed distribution captures model-seed noise only, not date-sampling uncertainty",
        "one phase of the 21-session cycle is evaluated (fixed by the frozen first date); no phase or cadence sweep",
        "B1 has 96 rebalances against 403, so its Sharpe and drawdown are estimated from far fewer, coarser observations",
        "drawdown measured on 21-session periods cannot see the intra-period path",
        "completed-spell holding duration excludes spells still open at the last date",
    ],
    "no_sweep": "exactly two arms; no 10/15/20/22/42-session cadence is run or evaluated",
    "outputs": [
        "definition.json", "config.json", "manifest.json", "metrics.json", "per_seed_cadence.csv",
        "fold_cadence.csv", "paired_differences.csv",
    ],
    "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
}

METHOD_SOURCES = (
    "src/quant/backtest/engine.py", "src/quant/backtest/rules.py", "src/quant/backtest/costs.py",
    "src/quant/pit/calendar.py", "src/quant/study/firewall.py", "src/quant/study/exp009a.py",
    "src/quant/study/exp009b.py", "src/quant/study/exp010a.py", "src/quant/study/exp010b.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    return prereg.check(document=PREREG_DOC, expected_fingerprint=definition_fingerprint(root),
                        method_sources=METHOD_SOURCES, root=root, fetch=fetch)


# ── inputs ───────────────────────────────────────────────────────────────────

def _atomic_json(path: Path, payload: Any) -> None:
    exp010a._atomic_json(path, payload)


def verify_parent_artifacts(root: Path = Path(".")) -> dict[str, Any]:
    """The committed EXP-010A artifacts must be byte-identical to what this study registered."""
    checks = {}
    for name, expected in PARENT_ARTIFACT_SHA256.items():
        path = Path(root) / PARENT_DIR / name
        checks[name] = path.exists() and prereg.sha256_file(path) == expected
    committed = json.loads((Path(root) / PARENT_DIR / "prediction_hashes.json").read_text())
    checks["prediction_hashes_match_registered"] = {
        str(k): v for k, v in PARENT_PREDICTION_SHA256.items()
    } == committed
    return {"passed": all(checks.values()), "checks": checks}


def load_seed_predictions(seed: int, root: Path = Path(".")) -> pd.DataFrame:
    """One frozen seed, refused unless its hash equals the registered EXP-010A hash."""
    path = Path(root) / PARENT_DIR / "checkpoints" / f"seed_{seed:02d}_predictions.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Regenerate it only with the unmodified EXP-010A runner "
            "(python -m scripts.quant.exp010a run); EXP-010B never refits."
        )
    frame = pd.read_parquet(path)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    digest = exp010a._prediction_hash(frame)
    if digest != PARENT_PREDICTION_SHA256[seed]:
        raise RuntimeError(
            f"seed {seed} prediction hash {digest} != registered {PARENT_PREDICTION_SHA256[seed]}; "
            "move the file aside and regenerate it with the unmodified EXP-010A runner"
        )
    FIREWALL.assert_clear(frame, context=f"EXP-010B seed {seed} predictions")
    return frame


def _daily_panel_hash(panel: pd.DataFrame) -> str:
    cols = panel[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]].copy()
    cols["date"] = pd.to_datetime(cols["date"]).dt.strftime("%Y-%m-%d")
    cols = cols.sort_values(["date", "symbol"], kind="mergesort")
    return prereg.sha256_bytes(pd.util.hash_pandas_object(cols, index=False).to_numpy().tobytes())


def _calendar_hash(sessions: Sequence[Date]) -> str:
    return prereg.sha256_bytes(json.dumps([str(day) for day in sessions]).encode())


def build_daily_panel(root: Path = Path("."), *, use_cache: bool = True) -> tuple[pd.DataFrame, TradingCalendar]:
    """Daily forward 5- and 21-session returns and dollar volume, capped at the last prediction date.

    Built with the same `DatasetBuilder` EXP-009A used, at a one-session step.  The builder reads
    prices past the cap internally (a forward return needs them; the latest one ends 2025-06-10,
    before the holdout); no row dated after the cap is returned or cached, and neither is any
    session after it.
    """
    start, _ = exp009b.arm_firewall(root)
    if LAST_PREDICTION_DATE >= start:
        raise HoldoutBreach(f"panel end {LAST_PREDICTION_DATE} is not before the holdout start {start}")
    cache, calendar_cache = Path(root) / DAILY_PANEL_CACHE, Path(root) / CALENDAR_CACHE
    if use_cache and cache.exists() and calendar_cache.exists():
        panel = pd.read_parquet(cache)
        sessions = tuple(Date.fromisoformat(day) for day in json.loads(calendar_cache.read_text())["sessions"])
    else:
        from src.quant.datasets.store import RawStore
        from src.quant.features.registry import REGISTRY
        from src.quant.pit.dataset import DatasetBuilder
        from src.quant.pit.universe import UniverseHistory

        store = RawStore(Path(root) / "data/research")
        universe = UniverseHistory.load(Path(root) / "data/research" / "universe")
        dataset = DatasetBuilder(store, universe).build(
            start=Date(2014, 4, 1), end=LAST_PREDICTION_DATE,
            features=REGISTRY.per_symbol_names()[:3], labels=["fwd_ret_5", "fwd_ret_21"],
            step_sessions=1, workers=6, run_guards=False,
        )
        panel = dataset.frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
        sessions = tuple(day for day in dataset.calendar.sessions if day <= LAST_PREDICTION_DATE)
        cache.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(cache, compression="zstd")
        calendar_cache.write_text(json.dumps({"sessions": [str(day) for day in sessions]}) + "\n")
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel[panel["date"].dt.date <= LAST_PREDICTION_DATE].reset_index(drop=True)
    FIREWALL.assert_clear(panel, context="EXP-010B daily returns panel")
    return panel, TradingCalendar.from_dates(sessions)


def verify_panel(panel: pd.DataFrame, calendar: TradingCalendar) -> dict[str, Any]:
    """The daily panel must be the frozen panel EXP-010A traded on, plus the off-grid sessions."""
    sessions = set(calendar.sessions)
    panel_days = set(panel["date"].dt.date.unique())
    grid_days = set(calendar.sample(GRID_STEP_SESSIONS))
    grid = panel[panel["date"].dt.date.isin(grid_days)]
    step5 = grid[["date", "symbol", "dollar_volume", "fwd_ret_5"]].copy()
    step5["date"] = step5["date"].dt.date
    checks = {
        "daily_panel_sha256": _daily_panel_hash(panel) == DEFINITION["inputs"]["daily_returns_panel_sha256"],
        "calendar_sha256": _calendar_hash(calendar.sessions) == DEFINITION["inputs"]["calendar_sha256"],
        "panel_days_are_sessions": panel_days <= sessions,
        "grid_rows_equal_frozen_step5_panel": exp009a.panel_content_hash(step5) == STEP5_RETURNS_PANEL_SHA256,
        "panel_ends_at_cap": max(panel_days) == LAST_PREDICTION_DATE,
    }
    return {"passed": all(checks.values()), "checks": checks}


# ── calendar schedule ────────────────────────────────────────────────────────

def rebalance_schedule(
    calendar: TradingCalendar, step_sessions: int, *,
    first_prediction: Optional[Date] = None, last_prediction: Optional[Date] = None,
    delay: int = INFORMATION_DELAY_SESSIONS,
) -> list[Date]:
    """Every `step_sessions`-th session on the global calendar, from first prediction + `delay` sessions."""
    if step_sessions < 1:
        raise ValueError("step_sessions must be >= 1")
    first_prediction = first_prediction or FIRST_PREDICTION_DATE
    last_prediction = last_prediction or LAST_PREDICTION_DATE
    start = calendar.index_of(first_prediction) + delay
    sessions = calendar.sessions
    out: list[Date] = []
    position = start
    while position < len(sessions) and sessions[position] <= last_prediction:
        out.append(sessions[position])
        position += step_sessions
    return out


def grid_report(predictions: pd.DataFrame, calendar: TradingCalendar) -> dict[str, Any]:
    dates = sorted(predictions["date"].unique())
    positions = [calendar.index_of(day) for day in dates]
    gaps = sorted({b - a for a, b in zip(positions[:-1], positions[1:])})
    return {"dates": len(dates), "first": str(dates[0]), "last": str(dates[-1]), "gaps_sessions": gaps,
            "on_calendar_5_grid": bool(all(p % GRID_STEP_SESSIONS == positions[0] % GRID_STEP_SESSIONS for p in positions))}


def schedule_report(calendar: TradingCalendar) -> dict[str, Any]:
    out = {}
    for arm, spec in ARMS.items():
        dates = rebalance_schedule(calendar, spec["step_sessions"])
        positions = [calendar.index_of(day) for day in dates]
        out[arm] = {
            "rebalances": len(dates), "first": str(dates[0]), "last": str(dates[-1]),
            "session_gaps": sorted({b - a for a, b in zip(positions[:-1], positions[1:])}),
        }
    return out


# ── alignment ────────────────────────────────────────────────────────────────

def align_signals(
    predictions: pd.DataFrame, universe: pd.DataFrame, calendar: TradingCalendar,
    schedule: Sequence[Date], *, delay: int = INFORMATION_DELAY_SESSIONS,
) -> pd.DataFrame:
    """The (rebalance date, name, signal) rows a book could actually have traded.

    `predictions`: date (python date), symbol, prediction.  `universe`: the point-in-time in-universe
    rows (date as datetime64, symbol).  The result carries the date of the prediction used and its
    age in sessions.  Names lacking a signal are absent, never filled.
    """
    sessions = pd.DatetimeIndex(pd.to_datetime(list(calendar.sessions)))
    position = {day: i for i, day in enumerate(calendar.sessions)}
    grid = pd.DatetimeIndex(sorted(pd.to_datetime(predictions["date"]).unique()))

    rows = pd.DataFrame({"rebalance": pd.to_datetime(list(schedule))})
    indices = np.array([position[day] for day in schedule])
    if (indices - delay < 0).any():
        raise ValueError("a rebalance date has fewer than `delay` sessions before it")
    rows["signal_cutoff"] = sessions[indices - delay]
    grid_pos = grid.searchsorted(rows["rebalance"], side="right") - 1
    if (grid_pos < 0).any():
        raise ValueError("a rebalance date precedes the first prediction date")
    rows["scored_on"] = grid[grid_pos]

    tradable = universe[["date", "symbol"]].rename(columns={"date": "rebalance"})
    left = tradable.merge(rows, on="rebalance", how="inner")

    right = predictions[["date", "symbol", "prediction"]].copy()
    right["date"] = pd.to_datetime(right["date"])
    scored = right[["date", "symbol"]].rename(columns={"date": "scored_on"})
    left = left.merge(scored, on=["scored_on", "symbol"], how="inner")

    right = right.rename(columns={"date": "signal_date"}).sort_values("signal_date", kind="mergesort")
    left = left.sort_values("signal_cutoff", kind="mergesort")
    merged = pd.merge_asof(left, right, left_on="signal_cutoff", right_on="signal_date", by="symbol",
                           direction="backward")
    merged = merged.dropna(subset=["prediction"])
    merged["signal_age_sessions"] = (
        sessions.searchsorted(merged["rebalance"]) - sessions.searchsorted(merged["signal_date"])
    )
    out = merged[["rebalance", "symbol", "prediction", "signal_date", "signal_age_sessions", "scored_on"]]
    out = out.rename(columns={"rebalance": "date"}).sort_values(["date", "symbol"], kind="mergesort")
    return out.reset_index(drop=True)


# ── portfolio ────────────────────────────────────────────────────────────────

def arm_config(arm: str, half_spread_bps: float, *, record_weights: bool = False) -> BacktestConfig:
    engine = exp009a.DEFINITION["engine"]
    return BacktestConfig(
        quantiles=engine["quantiles"], long_short=engine["long_short"], capital=engine["capital"],
        rebalance_step_sessions=ARMS[arm]["step_sessions"],
        cost_model=SimpleCostModel(commission_bps=engine["commission_bps"], half_spread_bps=half_spread_bps,
                                   impact_coefficient=engine["impact_coefficient"]),
        max_weight=engine["max_weight"], min_names=engine["min_names"], execution_lag_periods=0,
        weight_rule=rule_from_spec(PORTFOLIO), record_weights=record_weights,
    )


def _engine_inputs(aligned: pd.DataFrame, universe: pd.DataFrame, arm: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    column = ARMS[arm]["forward_return_column"]
    days = set(aligned["date"].unique())
    panel = universe[universe["date"].isin(days)][["date", "symbol", "dollar_volume", column]].copy()
    signals = aligned[["date", "symbol", "prediction"]].copy()
    for frame in (panel, signals):
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return signals, panel


def run_arm(aligned: pd.DataFrame, universe: pd.DataFrame, arm: str, half_spread_bps: float, *,
            record_weights: bool = False) -> tuple[BacktestResult, pd.DataFrame, pd.DataFrame]:
    signals, panel = _engine_inputs(aligned, universe, arm)
    result = run_backtest(signals, panel, config=arm_config(arm, half_spread_bps, record_weights=record_weights),
                          forward_return_column=ARMS[arm]["forward_return_column"])
    return result, signals, panel


def _sharpe(values: np.ndarray, periods_per_year: float) -> Optional[float]:
    if len(values) < 3 or np.std(values, ddof=1) <= 0:
        return None
    return float(np.mean(values) / np.std(values, ddof=1) * np.sqrt(periods_per_year))


def membership_stats(weights: pd.DataFrame) -> dict[str, float]:
    dates = sorted(weights["date"].unique())
    by_date = {day: group.set_index("symbol")["weight"] for day, group in weights.groupby("date")}
    changed, retain_long, retain_short = [], [], []
    for previous, current in zip(dates[:-1], dates[1:]):
        p, c = by_date[previous], by_date[current]
        p_long, c_long, p_short, c_short = set(p[p > 0].index), set(c[c > 0].index), set(p[p < 0].index), set(c[c < 0].index)
        changed.append(len(c_long - p_long) + len(c_short - p_short))
        retain_long.append(len(p_long & c_long) / max(len(p_long), 1))
        retain_short.append(len(p_short & c_short) / max(len(p_short), 1))
    return {
        "names_changed_per_rebalance": float(np.mean(changed)),
        "long_leg_retention": float(np.mean(retain_long)), "short_leg_retention": float(np.mean(retain_short)),
    }


def fold_table(periods: pd.DataFrame, fold_of: dict[Date, int], periods_per_year: float) -> list[dict[str, Any]]:
    frame = periods.assign(fold=[fold_of[day] for day in periods["date"]])
    rows = []
    for fold, group in frame.groupby("fold"):
        net = group["net_return"].to_numpy()
        rows.append({
            "fold": int(fold), "periods": int(len(group)),
            "first_date": str(group["date"].min()), "last_date": str(group["date"].max()),
            "gross_return_annualised": float(group["gross_return"].mean() * periods_per_year),
            "net_return_annualised": float(net.mean() * periods_per_year),
            "net_sharpe": _sharpe(net, periods_per_year),
            "annualised_turnover": float(group["turnover"].mean() * periods_per_year),
            "mean_cost_bp": float(group["cost_return"].mean() * 1e4),
        })
    return rows


def rebalance_folds(aligned: pd.DataFrame, fold_by_grid: dict[Date, int]) -> dict[Date, int]:
    """Fold of each rebalance = fold of the latest frozen prediction date at or before it."""
    scored = aligned.groupby("date")["scored_on"].first()
    return {pd.Timestamp(day).date(): fold_by_grid[pd.Timestamp(day_scored).date()] for day, day_scored in scored.items()}


def arm_report(seed: int, arm: str, aligned: pd.DataFrame, universe: pd.DataFrame,
               fold_by_grid: dict[Date, int]) -> tuple[dict[str, Any], list[dict[str, Any]], pd.DataFrame, dict[Date, int]]:
    step = ARMS[arm]["step_sessions"]
    per_year = TRADING_DAYS / step
    costs: dict[str, dict[str, Any]] = {}
    primary: Optional[tuple[BacktestResult, pd.DataFrame, pd.DataFrame]] = None
    for bps in COSTS:
        record = bps == PRIMARY_BPS
        result, signals, panel = run_arm(aligned, universe, arm, bps, record_weights=record)
        if record:
            primary = (result, signals, panel)
        m = result.metrics
        costs[f"{int(bps)}bp"] = {
            key: m.get(key) for key in (
                "gross_sharpe", "net_sharpe", "annualised_turnover", "cost_share_of_gross", "net_max_drawdown",
                "gross_max_drawdown", "gross_total_return", "net_total_return", "gross_cagr", "net_cagr",
                "total_cost_return", "periods",
            )
        }
    assert primary is not None
    result, signals, panel = primary
    holdings = exp009a.holdings_metrics(result, signals, panel, exp009a.DEFINITION["engine"]["capital"])
    membership = membership_stats(result.weights)
    spells = holdings["holding_duration_periods"]
    nominal = INFORMATION_DELAY_SESSIONS + (GRID_STEP_SESSIONS - 1 if step != GRID_STEP_SESSIONS else 0)
    ages = aligned["signal_age_sessions"].to_numpy()
    scheduled = aligned.groupby("date").size()
    fold_of = rebalance_folds(aligned, fold_by_grid)
    folds = fold_table(result.periods, fold_of, per_year)
    p10 = costs[f"{int(PRIMARY_BPS)}bp"]
    report = {
        "seed": seed, "arm": arm, "step_sessions": step, "rebalances": int(p10["periods"]),
        "scheduled_rebalances": int(scheduled.shape[0]),
        "gross_sharpe": p10["gross_sharpe"], "net_sharpe_10bp": p10["net_sharpe"],
        "annualised_turnover": p10["annualised_turnover"], "cost_share_of_gross": p10["cost_share_of_gross"],
        "net_max_drawdown": p10["net_max_drawdown"], "gross_max_drawdown": p10["gross_max_drawdown"],
        "gross_total_return": p10["gross_total_return"], "net_total_return": p10["net_total_return"],
        "gross_cagr": p10["gross_cagr"], "net_cagr": p10["net_cagr"],
        "holding_duration_rebalances": spells["mean_completed_spell"],
        "holding_duration_sessions": None if spells["mean_completed_spell"] is None else spells["mean_completed_spell"] * step,
        **membership,
        "names_replaced_both_legs_fraction": holdings["names_replaced_per_rebalance"]["both_legs_fraction"],
        "effective_n_long": holdings["breadth"]["mean_effective_n_long"],
        "effective_n_short": holdings["breadth"]["mean_effective_n_short"],
        "max_abs_weight": holdings["breadth"]["max_abs_weight"],
        "mean_eligible_names": float(scheduled.mean()),
        "signal_age_median_sessions": float(np.median(ages)), "signal_age_p95_sessions": float(np.percentile(ages, 95)),
        "signal_age_max_sessions": int(ages.max()),
        "share_signals_older_than_nominal": float(np.mean(ages > nominal)), "nominal_max_signal_age": nominal,
        "costs": costs,
    }
    for label, values in costs.items():
        report[f"net_sharpe_{label}"] = values["net_sharpe"]
        report[f"cost_share_of_gross_{label}"] = values["cost_share_of_gross"]
    return report, folds, result.periods, fold_of


# ── paired comparison ────────────────────────────────────────────────────────

def distribution(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)), "median": float(np.median(array)), "sample_std": float(np.std(array, ddof=1)),
        "min": float(np.min(array)), "max": float(np.max(array)),
        "p05": float(np.quantile(array, 0.05)), "p95": float(np.quantile(array, 0.95)),
    }


def paired_metric_names(report: dict[str, Any]) -> list[str]:
    skip = {"seed", "arm", "costs", "step_sessions", "nominal_max_signal_age"}
    return [k for k, v in report.items() if k not in skip and isinstance(v, (int, float)) and v is not None]


def paired_rows(b0: Sequence[dict[str, Any]], b1: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """B1 - B0, seed by seed.  Both lists must cover every seed, in order."""
    if [r["seed"] for r in b0] != list(SEEDS) or [r["seed"] for r in b1] != list(SEEDS):
        raise ValueError("paired comparison needs all ten seeds, in order, in both arms")
    rows = []
    for left, right in zip(b0, b1):
        for metric in paired_metric_names(left):
            x, y = left.get(metric), right.get(metric)
            if x is None or y is None:
                continue
            rows.append({"seed": left["seed"], "metric": metric, "b0": float(x), "b1": float(y), "difference_b1_minus_b0": float(y) - float(x)})
    return rows


def paired_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    out: dict[str, Any] = {}
    for metric, group in frame.groupby("metric"):
        diff = group["difference_b1_minus_b0"].to_numpy()
        out[metric] = {
            **distribution(diff), "seeds": int(len(diff)), "seeds_positive": int((diff > 0).sum()),
            "seeds_negative": int((diff < 0).sum()),
            "b0_mean": float(group["b0"].mean()), "b1_mean": float(group["b1"].mean()),
            "relative_change_median": float(np.median(diff / group["b0"].to_numpy())) if (group["b0"] != 0).all() else None,
        }
    return out


def context_units(summary: dict[str, Any]) -> dict[str, Any]:
    """Median paired differences expressed against EXP-010A noise: description only."""
    out = {}
    for metric, floor in (("net_sharpe_10bp", NOISE_FLOOR["net_sharpe_10bp"]),
                          ("annualised_turnover", NOISE_FLOOR["annualised_turnover"])):
        median = summary[metric]["median"]
        out[metric] = {"median_difference": median, "in_exp010a_seed_sds": median / floor["sample_std"],
                       "in_exp010a_p95_p05_spans": median / floor["p95_minus_p05"],
                       "note": "descriptive; EXP-010A defines no pass threshold"}
    return out


def leave_one_fold_out(periods: dict[tuple[int, str], pd.DataFrame], fold_maps: dict[tuple[int, str], dict[Date, int]],
                       n_folds: int = 8) -> list[dict[str, Any]]:
    """Pooled paired net-Sharpe difference recomputed with one fold removed, per seed."""
    rows = []
    for removed in range(n_folds):
        diffs = []
        for seed in SEEDS:
            sharpes = {}
            for arm in ARMS:
                frame = periods[(seed, arm)]
                keep = np.array([fold_maps[(seed, arm)][day] != removed for day in frame["date"]])
                sharpes[arm] = _sharpe(frame["net_return"].to_numpy()[keep], TRADING_DAYS / ARMS[arm]["step_sessions"])
            diffs.append(sharpes["B1"] - sharpes["B0"])
        rows.append({"fold_removed": removed, "median_difference": float(np.median(diffs)),
                     "mean_difference": float(np.mean(diffs)), "seeds_positive": int(sum(d > 0 for d in diffs))})
    return rows


def classify(summary: dict[str, Any], lofo: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The preregistered rule, applied mechanically."""
    rule = INTERPRETATION
    turnover = summary["annualised_turnover"]
    reduced = bool(
        turnover["relative_change_median"] is not None
        and turnover["relative_change_median"] <= rule["turnover_materially_reduced"]["median_relative_change_at_most"]
        and turnover["seeds_negative"] >= rule["turnover_materially_reduced"]["seeds_with_lower_turnover_at_least"]
    )
    net = summary["net_sharpe_10bp"]
    if net["median"] >= UNIT and net["seeds_positive"] >= 9:
        status = "IMPROVED"
    elif net["median"] <= -UNIT:
        status = "DEGRADED"
    else:
        status = "PRESERVED"
    floor = 0.0 if status == "IMPROVED" else -UNIT
    fold_robust = bool(all(row["median_difference"] > floor for row in lofo))
    gross_equivalent = bool(abs(summary["gross_sharpe"]["median"]) < UNIT)
    if reduced:
        if status == "DEGRADED":
            label = "TURNOVER_REDUCED_SIGNAL_LOST"
        elif fold_robust:
            label = "ECONOMICALLY_IMPROVED"
        else:
            label = "NO_STABLE_ECONOMIC_GAIN"
    else:
        label = "CADENCE_EQUIVALENT" if status == "PRESERVED" and gross_equivalent else "NO_STABLE_ECONOMIC_GAIN"
    return {
        "label": label, "turnover_materially_reduced": reduced, "net_sharpe_status": status,
        "fold_robust": fold_robust, "gross_equivalent": gross_equivalent, "unit": UNIT,
        "worst_leave_one_fold_out_median_difference": float(min(row["median_difference"] for row in lofo)),
        "promotion": "NOT ASSESSED", "best_seed_selected": False,
    }


def check_b0_reproduces_parent(reports: Sequence[dict[str, Any]], root: Path = Path("."), *, tolerance: float = 1e-9,
                               cost_labels: Optional[Sequence[str]] = None) -> dict[str, Any]:
    """B0 through the new alignment must equal the committed EXP-010A per-seed economics."""
    parent = json.loads((Path(root) / PARENT_DIR / "metrics.json").read_text())["per_seed"]
    by_seed = {row["seed"]: row for row in parent}
    worst, failures = 0.0, []
    for report in reports:
        if report["arm"] != "B0":
            continue
        for label, values in report["costs"].items():
            if cost_labels is not None and label not in cost_labels:
                continue
            for key in ("gross_sharpe", "net_sharpe", "annualised_turnover", "net_max_drawdown", "cost_share_of_gross"):
                gap = abs(float(values[key]) - float(by_seed[report["seed"]]["costs"][label][key]))
                worst = max(worst, gap)
                if gap > tolerance:
                    failures.append({"seed": report["seed"], "cost": label, "metric": key, "gap": gap})
    return {"passed": not failures, "max_abs_gap": worst, "tolerance": tolerance, "failures": failures[:10]}


# ── dry run ──────────────────────────────────────────────────────────────────

def holdout_guard(root: Path = Path(".")) -> dict[str, Any]:
    start, end = exp009b.arm_firewall(root)
    status = FIREWALL.status()
    if status.get("holdout_state") != "SEALED":
        raise HoldoutBreach(f"holdout is not sealed: {status}")
    return {"start": str(start), "end": str(end), "touched": False, "firewall": status}


def dry_run(root: Path = Path("."), *, reproduce_parent: bool = True) -> dict[str, Any]:
    """Inputs, calendar, hashes and B0 reproduction.  No B1 economics are computed."""
    began = time.perf_counter()
    root = Path(root)
    guard = holdout_guard(root)
    parent = verify_parent_artifacts(root)
    panel, calendar = build_daily_panel(root)
    panel_check = verify_panel(panel, calendar)
    universe = panel[panel["in_universe"]]
    hashes, grid, fold_maps = {}, None, {}
    reports: list[dict[str, Any]] = []
    for seed in SEEDS:
        predictions = load_seed_predictions(seed, root)
        hashes[str(seed)] = exp010a._prediction_hash(predictions)
        grid = grid or grid_report(predictions, calendar)
        fold_maps[seed] = predictions.groupby("date")["fold"].first().astype(int).to_dict()
        if reproduce_parent:
            schedule = rebalance_schedule(calendar, ARMS["B0"]["step_sessions"])
            aligned = align_signals(predictions[["date", "symbol", "prediction"]], universe, calendar, schedule)
            result, _, _ = run_arm(aligned, universe, "B0", PRIMARY_BPS)
            m = result.metrics
            reports.append({"seed": seed, "arm": "B0", "costs": {"10bp": {
                k: m[k] for k in ("gross_sharpe", "net_sharpe", "annualised_turnover", "net_max_drawdown", "cost_share_of_gross")}}})
    schedules = schedule_report(calendar)
    reproduction = check_b0_reproduces_parent(reports, root, cost_labels=["10bp"]) if reproduce_parent else None
    checks = {
        "parent_artifacts": parent["passed"],
        "prediction_hashes_all_ten": hashes == {str(k): v for k, v in PARENT_PREDICTION_SHA256.items()},
        "daily_panel_and_calendar": panel_check["passed"],
        "grid_is_5_session": grid["gaps_sessions"] == [GRID_STEP_SESSIONS] and grid["dates"] == 404,
        "fold_labels_identical_across_seeds": all(fold_maps[s] == fold_maps[0] for s in SEEDS),
        "schedule_counts": all(schedules[a]["rebalances"] == EXPECTED_REBALANCES[a] for a in ARMS),
        "schedule_gaps_exact": all(schedules[a]["session_gaps"] == [ARMS[a]["step_sessions"]] for a in ARMS),
        "schedule_first_last": all(schedules[a]["first"] == EXPECTED_FIRST_REBALANCE and schedules[a]["last"] == EXPECTED_LAST_REBALANCE[a] for a in ARMS),
        "b0_reproduces_exp010a_10bp": None if reproduction is None else reproduction["passed"],
    }
    return {
        "experiment_id": EXPERIMENT_ID, "real_evaluation_executed": False, "retraining": False,
        "seeds": list(SEEDS), "seed_count": len(SEEDS), "prediction_hashes_verified": hashes,
        "parent_artifact_checks": parent["checks"], "panel_checks": panel_check["checks"],
        "prediction_grid": grid, "schedules": schedules,
        "b0_reproduction_10bp": reproduction, "checks": checks,
        "all_checks_passed": all(v for v in checks.values() if v is not None),
        "holdout": guard, "wall_seconds": round(time.perf_counter() - began, 1),
    }


# ── the study ────────────────────────────────────────────────────────────────

def run_study(root: Path = Path("."), *, output: Optional[Path] = None) -> dict[str, Any]:
    began = time.perf_counter()
    root = Path(root)
    output = output or root / OUTPUT_DIR
    gate = prereg_gate(root)  # mandatory: before any data is read
    git_state = exp009a._git_state(root)
    guard = holdout_guard(root)
    parent = verify_parent_artifacts(root)
    if not parent["passed"]:
        raise RuntimeError(f"EXP-010A artifacts differ from those registered: {parent['checks']}")
    panel, calendar = build_daily_panel(root)
    panel_check = verify_panel(panel, calendar)
    if not panel_check["passed"]:
        raise RuntimeError(f"EXP-010B INVALID panel: {panel_check['checks']}")
    schedules = {arm: rebalance_schedule(calendar, spec["step_sessions"]) for arm, spec in ARMS.items()}
    if {a: len(s) for a, s in schedules.items()} != EXPECTED_REBALANCES:
        raise RuntimeError(f"unexpected schedule sizes: { {a: len(s) for a, s in schedules.items()} }")
    universe = panel[panel["in_universe"]]

    reports: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    fold_rows: list[dict[str, Any]] = []
    periods: dict[tuple[int, str], pd.DataFrame] = {}
    fold_maps: dict[tuple[int, str], dict[Date, int]] = {}
    hashes: dict[str, str] = {}
    reference_folds: Optional[dict[Date, int]] = None
    for position, seed in enumerate(SEEDS, 1):
        predictions = load_seed_predictions(seed, root)
        hashes[str(seed)] = exp010a._prediction_hash(predictions)
        fold_by_grid = predictions.groupby("date")["fold"].first().astype(int).to_dict()
        reference_folds = reference_folds or fold_by_grid
        if fold_by_grid != reference_folds:
            raise RuntimeError(f"seed {seed} fold labels differ from seed 0")
        signals = predictions[["date", "symbol", "prediction"]]
        for arm in ARMS:
            aligned = align_signals(signals, universe, calendar, schedules[arm])
            report, folds, arm_periods, fold_of = arm_report(seed, arm, aligned, universe, fold_by_grid)
            reports[arm].append(report)
            fold_rows.extend({"seed": seed, "arm": arm, **row} for row in folds)
            periods[(seed, arm)] = arm_periods
            fold_maps[(seed, arm)] = fold_of
        print(f"EXP-010B seed {position}/10 ({seed}) complete | elapsed {(time.perf_counter() - began) / 60:.1f}m", flush=True)

    reproduction = check_b0_reproduces_parent(reports["B0"], root)
    if not reproduction["passed"]:
        raise RuntimeError(f"EXP-010B INVALID: B0 does not reproduce EXP-010A: {reproduction}")

    rows = paired_rows(reports["B0"], reports["B1"])
    summary = paired_summary(rows)
    lofo = leave_one_fold_out(periods, fold_maps)
    classification = classify(summary, lofo)
    fold_frame = pd.DataFrame(fold_rows)
    by_fold = []
    for fold, group in fold_frame.groupby("fold"):
        wide = group.pivot(index="seed", columns="arm", values=["gross_return_annualised", "net_return_annualised", "annualised_turnover", "net_sharpe"])
        entry = {"fold": int(fold), "exp010a_mean_fold_rank_ic": EXP010A_MEAN_FOLD_IC[int(fold)]}
        for metric in ("gross_return_annualised", "net_return_annualised", "annualised_turnover", "net_sharpe"):
            diff = (wide[(metric, "B1")] - wide[(metric, "B0")]).dropna()
            entry[metric] = {"b0_mean": float(wide[(metric, "B0")].mean()), "b1_mean": float(wide[(metric, "B1")].mean()),
                             "difference_median": float(diff.median()), "seeds_positive": int((diff > 0).sum())}
        entry["periods_b0"] = int(group[group["arm"] == "B0"]["periods"].iloc[0])
        entry["periods_b1"] = int(group[group["arm"] == "B1"]["periods"].iloc[0])
        by_fold.append(entry)

    output.mkdir(parents=True, exist_ok=True)
    _atomic_json(output / "definition.json", DEFINITION)
    _atomic_json(output / "config.json", {
        "arms": ARMS, "portfolio": PORTFOLIO, "costs": list(COSTS), "primary_cost_bps": PRIMARY_BPS,
        "information_delay_sessions": INFORMATION_DELAY_SESSIONS, "seeds": list(SEEDS),
        "schedules": {arm: [str(day) for day in dates] for arm, dates in schedules.items()},
        "folds": [fold.as_dict() for fold in exp009b.recorded_plan(root).folds],
    })
    flat = pd.DataFrame([{k: v for k, v in r.items() if k != "costs"} for arm in ARMS for r in reports[arm]])
    flat.to_csv(output / "per_seed_cadence.csv", index=False)
    fold_frame.to_csv(output / "fold_cadence.csv", index=False)
    pd.DataFrame(rows).to_csv(output / "paired_differences.csv", index=False)
    _atomic_json(output / "metrics.json", {
        "per_seed": {arm: reports[arm] for arm in ARMS}, "paired_summary": summary,
        "noise_context": context_units(summary), "leave_one_fold_out": lofo, "fold_economics": by_fold,
        "classification": classification, "b0_reproduction": reproduction,
    })
    manifest = {
        "experiment_id": EXPERIMENT_ID, "status": DEFINITION["status"], **gate, **git_state,
        "definition_sha256": prereg.sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
        "inputs": {"prediction_sha256_by_seed": hashes, "parent_artifacts_verified": parent["passed"],
                   "daily_panel_sha256": DAILY_PANEL_SHA256, "calendar_sha256": CALENDAR_SHA256},
        "validity_checks": {"panel": panel_check["checks"], "b0_reproduces_exp010a": reproduction["passed"],
                            "schedule_counts": {a: len(s) for a, s in schedules.items()}},
        "dependency_versions": dependency_versions(),
        "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(),
                    "platform": platform.platform(), "python": platform.python_version()},
        "holdout": guard,
        "seeds": list(SEEDS), "arms": list(ARMS), "retraining": False, "parameter_sweep": False,
        "best_seed_selected": False, "classification": classification["label"], "completion": "COMPLETE",
    }
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*"))
                                 if p.is_file() and p.name != "manifest.json"}
    _atomic_json(output / "manifest.json", manifest)
    print(f"EXP-010B COMPLETE: {classification['label']}; 10/10 seeds x 2 arms; outputs: {output}", flush=True)
    return {"manifest": manifest, "classification": classification, "paired_summary": summary}


def read_summary(root: Path = Path(".")) -> dict[str, Any]:
    path = Path(root) / OUTPUT_DIR / "metrics.json"
    if not path.exists():
        return {"status": "NOT_RUN", "expected": str(path)}
    payload = json.loads(path.read_text())
    summary = payload["paired_summary"]
    return {
        "status": "COMPLETE", "classification": payload["classification"],
        "paired_b1_minus_b0": {m: summary.get(m) for m in PRIMARY_PAIRED_METRICS},
        "noise_context": payload["noise_context"], "leave_one_fold_out": payload["leave_one_fold_out"],
        "fold_economics": payload["fold_economics"], "b0_reproduction": payload["b0_reproduction"],
        "best_seed_selected": False,
    }
