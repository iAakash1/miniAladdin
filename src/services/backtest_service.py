"""
Walk-forward validation of the v2 scoring engine — Phase 4.

Scientific scope, stated up front (and echoed in the API response):
  * Point-in-time fundamentals, news and macro series are not available in
    free data, so the walk-forward evaluates the MOMENTUM FAMILY of the
    engine, ungated (SRM=1.0). It validates the price-derived alpha core —
    not the full production pipeline. Nothing is simulated or faked.
  * Signals recompute every 5 trading days on an expanding window with a
    252-bar minimum; forward return horizon is 21 trading days (the
    engine's design horizon). No look-ahead: the score at t uses bars ≤ t.
  * The strategy test is long/flat (long when score ≥ CUT_ACTION), daily
    returns, no costs — a signal-quality diagnostic, not a track record.

Outputs: IC (Spearman) + rolling IC, hit rate, confusion matrix,
confidence calibration (reliability bins), score/verdict distributions,
long/flat equity vs buy & hold with Sharpe/Sortino/Calmar/max drawdown/
volatility/win rate/average holding period, monthly returns.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Optional

import numpy as np
import pandas as pd

from src import providers
from src.scoring.engine import CUT_ACTION, MIN_BARS, map_verdict, score_ticker

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 3600.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()

STEP = 5                # recompute signal weekly (5 trading days)
HORIZON = 21            # forward-return horizon (engine design horizon)
MIN_WINDOW = 252        # first signal needs a year of history
ROLLING_IC_WINDOW = 26  # ~ half a year of weekly signals
TRADING_DAYS = 252


def _spearman(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if len(a) < 8:
        return None
    rank = lambda x: np.argsort(np.argsort(x)).astype(float)  # noqa: E731
    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _annualized(daily: np.ndarray) -> dict[str, Optional[float]]:
    if len(daily) < 20:
        return {"return": None, "volatility": None, "sharpe": None,
                "sortino": None, "max_drawdown": None, "calmar": None}
    mean, std = daily.mean(), daily.std(ddof=1)
    downside = daily[daily < 0].std(ddof=1) if (daily < 0).sum() > 2 else None
    equity = np.cumprod(1 + daily)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity / peak - 1).min()
    ann_return = float((1 + mean) ** TRADING_DAYS - 1)
    return {
        "return": round(ann_return * 100, 2),
        "volatility": round(std * math.sqrt(TRADING_DAYS) * 100, 2),
        "sharpe": round(mean / std * math.sqrt(TRADING_DAYS), 2) if std > 0 else None,
        "sortino": round(mean / downside * math.sqrt(TRADING_DAYS), 2) if downside else None,
        "max_drawdown": round(float(drawdown) * 100, 2),
        "calmar": round(ann_return / abs(drawdown), 2) if drawdown < -1e-9 else None,
    }


def run_backtest(ticker: str) -> dict[str, Any]:
    """Never raises; {'error': ...} when history is insufficient."""
    ticker = ticker.upper()
    now = time.time()
    with _lock:
        entry = _cache.get(ticker)
        if entry and entry[0] > now:
            return {**entry[1], "cached": True}

    series_result = providers.market_data.get_series(ticker, "5y")
    if not series_result.ok or len(series_result.data.bars) < MIN_WINDOW + HORIZON + STEP:
        return {"ticker": ticker,
                "error": "Insufficient price history for walk-forward validation "
                         f"(need ≥ {MIN_WINDOW + HORIZON + STEP} daily bars)."}

    bars = series_result.data.bars
    frame = pd.DataFrame(
        {
            "Open": [b.open for b in bars], "High": [b.high for b in bars],
            "Low": [b.low for b in bars], "Close": [b.close for b in bars],
            "Volume": [b.volume or 0 for b in bars],
        },
        index=pd.to_datetime([b.date for b in bars]),
    )
    closes = frame["Close"].to_numpy()
    started = time.time()

    # ── Walk forward ─────────────────────────────────────────────────────────
    signal_dates: list[str] = []
    scores: list[float] = []
    confidences: list[int] = []
    verdicts: list[str] = []
    forwards: list[float] = []
    factor_series: dict[str, dict[int, float]] = {}  # factor -> step index -> score

    for t in range(MIN_WINDOW, len(bars) - HORIZON, STEP):
        window = frame.iloc[:t + 1]
        card = score_ticker(window, srm=1.0, price=float(closes[t]),
                            today=window.index[-1].date())
        if card is None:
            continue
        step = len(scores)
        signal_dates.append(bars[t].date)
        scores.append(card.ungated_score)
        confidences.append(card.confidence)
        verdicts.append(card.raw_verdict)
        forwards.append(float(closes[t + HORIZON] / closes[t] - 1))
        for row in card.factors:
            if row.score is not None:
                factor_series.setdefault(row.name, {})[step] = row.score

    if len(scores) < 12:
        return {"ticker": ticker, "error": "Too few valid walk-forward samples."}

    score_arr = np.array(scores)
    fwd_arr = np.array(forwards)

    # ── IC ───────────────────────────────────────────────────────────────────
    ic = _spearman(score_arr, fwd_arr)
    rolling_ic = [
        {"date": signal_dates[i],
         "ic": round(_spearman(score_arr[i - ROLLING_IC_WINDOW:i], fwd_arr[i - ROLLING_IC_WINDOW:i]) or 0, 3)}
        for i in range(ROLLING_IC_WINDOW, len(scores))
    ]

    # ── Directional accuracy & confusion matrix ─────────────────────────────
    def direction(verdict: str) -> str:
        return "long" if "Buy" in verdict else "short" if "Sell" in verdict else "flat"

    directional = [(direction(v), f) for v, f in zip(verdicts, forwards) if direction(v) != "flat"]
    hits = sum(1 for d, f in directional if (f > 0) == (d == "long"))
    hit_rate = round(hits / len(directional) * 100, 1) if directional else None

    confusion = {row: {"up": 0, "down": 0} for row in ("long", "flat", "short")}
    for v, f in zip(verdicts, forwards):
        confusion[direction(v)]["up" if f > 0 else "down"] += 1

    # ── Confidence calibration (reliability diagram) ─────────────────────────
    calibration = []
    conf_arr = np.array(confidences)
    for low in range(40, 100, 10):
        mask = (conf_arr >= low) & (conf_arr < low + 10)
        rows = [(direction(verdicts[i]), forwards[i]) for i in np.where(mask)[0] if direction(verdicts[i]) != "flat"]
        if len(rows) >= 3:
            wins = sum(1 for d, f in rows if (f > 0) == (d == "long"))
            calibration.append({
                "bin": f"{low}–{low + 9}",
                "expected": low + 5,
                "actual": round(wins / len(rows) * 100, 1),
                "n": len(rows),
            })

    # ── Long/flat strategy vs buy & hold (daily, no costs) ───────────────────
    daily_returns = np.diff(closes) / closes[:-1]
    positions = np.zeros(len(daily_returns))
    position_value = 0.0
    signal_at: dict[int, float] = {}
    cursor = 0
    for t in range(MIN_WINDOW, len(bars) - HORIZON, STEP):
        if cursor < len(scores) and bars[t].date == signal_dates[cursor]:
            signal_at[t] = scores[cursor]
            cursor += 1
    for day in range(MIN_WINDOW, len(daily_returns)):
        if day in signal_at:
            position_value = 1.0 if signal_at[day] >= CUT_ACTION else 0.0
        positions[day] = position_value

    strategy_daily = positions * daily_returns
    active = strategy_daily[MIN_WINDOW:]
    hold_daily = daily_returns[MIN_WINDOW:]

    equity_curve = []
    strategy_equity = 1.0
    hold_equity = 1.0
    for i in range(MIN_WINDOW, len(daily_returns)):
        strategy_equity *= 1 + strategy_daily[i]
        hold_equity *= 1 + daily_returns[i]
        if (i - MIN_WINDOW) % 5 == 0:
            equity_curve.append({
                "date": bars[i + 1].date,
                "strategy": round(strategy_equity, 4),
                "buy_hold": round(hold_equity, 4),
            })

    invested_days = active[positions[MIN_WINDOW:] > 0]
    win_rate = round(float((invested_days > 0).mean() * 100), 1) if len(invested_days) else None

    runs, run_length = [], 0
    for p in positions[MIN_WINDOW:]:
        if p > 0:
            run_length += 1
        elif run_length:
            runs.append(run_length)
            run_length = 0
    if run_length:
        runs.append(run_length)
    avg_holding = round(float(np.mean(runs)), 1) if runs else None

    monthly: dict[str, float] = {}
    month_index = frame.index[MIN_WINDOW + 1:]
    strategy_series = pd.Series(active, index=month_index[:len(active)])
    for month, value in ((1 + strategy_series).groupby(strategy_series.index.to_period("M")).prod() - 1).items():
        monthly[str(month)] = round(float(value) * 100, 2)

    # ── Distributions ─────────────────────────────────────────────────────────
    hist_counts, hist_edges = np.histogram(score_arr, bins=np.arange(-0.6, 0.65, 0.1))
    score_distribution = [
        {"bin": f"{hist_edges[i]:+.1f}", "count": int(hist_counts[i])}
        for i in range(len(hist_counts))
    ]
    verdict_counts: dict[str, int] = {}
    for v in verdicts:
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    # ── Factor-level diagnostics (validation v2) ─────────────────────────────
    # Per-factor IC, sign-stability across rolling windows, and pairwise
    # correlations — the raw material of the KEEP/MODIFY/REMOVE audit.
    factor_diagnostics: dict[str, Any] = {}
    for name, values in factor_series.items():
        indexes = sorted(values.keys())
        if len(indexes) < 12:
            continue
        f_scores = np.array([values[i] for i in indexes])
        f_forwards = np.array([forwards[i] for i in indexes])
        f_ic = _spearman(f_scores, f_forwards)
        # Sign stability: fraction of rolling windows whose IC shares the
        # overall sign (1.0 = the factor never flips its relationship).
        window_ics = []
        for start in range(0, len(indexes) - ROLLING_IC_WINDOW, max(1, ROLLING_IC_WINDOW // 2)):
            chunk_ic = _spearman(f_scores[start:start + ROLLING_IC_WINDOW],
                                 f_forwards[start:start + ROLLING_IC_WINDOW])
            if chunk_ic is not None:
                window_ics.append(chunk_ic)
        stability = (
            round(sum(1 for w in window_ics if (w > 0) == ((f_ic or 0) > 0)) / len(window_ics), 2)
            if window_ics and f_ic is not None else None
        )
        factor_diagnostics[name] = {
            "ic": round(f_ic, 3) if f_ic is not None else None,
            "sign_stability": stability,
            "samples": len(indexes),
        }

    factor_correlations: dict[str, float] = {}
    names_with_data = [n for n in factor_series if len(factor_series[n]) >= 12]
    for i, a in enumerate(names_with_data):
        for b in names_with_data[i + 1:]:
            shared = sorted(set(factor_series[a]) & set(factor_series[b]))
            if len(shared) >= 12:
                rho = _spearman(np.array([factor_series[a][s] for s in shared]),
                                np.array([factor_series[b][s] for s in shared]))
                if rho is not None:
                    factor_correlations[f"{a}~{b}"] = round(rho, 2)

    # Prediction drift: PSI of the score distribution, first half vs second
    half = len(scores) // 2
    psi = None
    if half >= 20:
        edges = np.arange(-0.6, 0.61, 0.15)
        p_counts, _ = np.histogram(score_arr[:half], bins=edges)
        q_counts, _ = np.histogram(score_arr[half:], bins=edges)
        p_frac = np.clip(p_counts / max(1, p_counts.sum()), 1e-4, None)
        q_frac = np.clip(q_counts / max(1, q_counts.sum()), 1e-4, None)
        psi = round(float(np.sum((q_frac - p_frac) * np.log(q_frac / p_frac))), 3)

    # Naive 12-1 baseline: sign of the 12-1 return, long/flat, same windows
    baseline_ic = None
    baseline = None
    if len(bars) > MIN_WINDOW + HORIZON:
        naive_scores = []
        for t in range(MIN_WINDOW, len(bars) - HORIZON, STEP):
            if t >= 252:
                naive_scores.append(closes[t - 21] / closes[t - 252] - 1)
            else:
                naive_scores.append(0.0)
        naive_arr = np.array(naive_scores[: len(forwards)])
        baseline_ic = _spearman(naive_arr, fwd_arr)
        naive_positions = np.zeros(len(daily_returns))
        naive_value = 0.0
        cursor2 = 0
        for t in range(MIN_WINDOW, len(bars) - HORIZON, STEP):
            if cursor2 < len(naive_arr):
                naive_value = 1.0 if naive_arr[cursor2] > 0 else 0.0
                cursor2 += 1
            if t < len(naive_positions):
                naive_positions[t:] = naive_value  # held until next signal
        naive_daily = (naive_positions * daily_returns)[MIN_WINDOW:]
        baseline = _annualized(naive_daily)

    # Recent-signal summary consumed by the live engine's confidence terms
    # (u_model, u_stab) — only ever read from cache, never computed inline.
    flips_last6 = sum(
        1 for a, b in zip(verdicts[-6:], verdicts[-5:]) if a != b
    ) if len(verdicts) >= 2 else 0
    recent = {
        "rolling_ic_last": rolling_ic[-1]["ic"] if rolling_ic else None,
        "verdict_flips_last6": flips_last6,
    }

    payload = {
        "ticker": ticker,
        "recent": recent,
        "scope_note": (
            "Momentum-family walk-forward, ungated (SRM=1.0): point-in-time "
            "fundamentals/news/macro are unavailable in free data, so this "
            "validates the price-derived core of the engine — not the full "
            "production pipeline. Long/flat test assumes no costs."
        ),
        "samples": len(scores),
        "period": {"start": signal_dates[0], "end": signal_dates[-1]},
        "ic": round(ic, 3) if ic is not None else None,
        "baseline_12_1_ic": round(baseline_ic, 3) if baseline_ic is not None else None,
        "baseline_12_1_strategy": baseline,
        "factor_diagnostics": factor_diagnostics,
        "factor_correlations": factor_correlations,
        "prediction_drift_psi": psi,
        "psi_note": "PSI of the score distribution, first vs second half; > 0.25 signals distribution drift.",
        "rolling_ic": rolling_ic,
        "hit_rate": hit_rate,
        "directional_samples": len(directional),
        "confusion_matrix": confusion,
        "calibration": calibration,
        "strategy": _annualized(active),
        "buy_hold": _annualized(hold_daily),
        "win_rate_invested_days": win_rate,
        "avg_holding_days": avg_holding,
        "time_invested_pct": round(float((positions[MIN_WINDOW:] > 0).mean() * 100), 1),
        "equity_curve": equity_curve,
        "monthly_strategy_returns": monthly,
        "score_distribution": score_distribution,
        "verdict_distribution": verdict_counts,
        "source": series_result.source,
        "computed_in_ms": round((time.time() - started) * 1000),
        "cached": False,
    }
    with _lock:
        _cache[ticker] = (now + CACHE_TTL_SECONDS, payload)
    logger.info("backtest %s: %d samples, IC=%s, %.0fms",
                ticker, len(scores), payload["ic"], payload["computed_in_ms"])
    return payload


def peek_cached(ticker: str) -> Optional[dict[str, Any]]:
    """Cached backtest payload or None — NEVER computes. The research path
    uses this for u_model/u_stab so a heavy walk-forward can't be triggered
    implicitly by an analyze request."""
    with _lock:
        entry = _cache.get(ticker.upper())
        if entry and entry[0] > time.time():
            return entry[1]
    return None


def reset_for_tests() -> None:
    _cache.clear()
