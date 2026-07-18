"""
Technical Intelligence Engine (v4.5, P0-A).

Deterministic computation of the classic technical-indicator suite from the
1-year OHLCV frame every research run already fetches — zero API calls. This
module is a PRESENTATION-layer engine: it classifies and narrates, but its
output is deliberately NOT a scoring input. The v2.1 scoring engine
(src/scoring/engine.py) and its verdicts are unchanged; this block answers
"what does the tape say, and why?" with numbers a reader can verify.

Every indicator here is the textbook construction (Wilder's smoothing for
RSI/ATR/ADX, 20/2σ Bollinger, 14-3 stochastic, 25-period Aroon), so values
match what a user sees on any charting platform.

Output contract (additive field on /api/research → `technical_intelligence`):
{
  "indicators": [{ "key", "label", "value", "detail", "state", "tone" }, ...],
  "regimes":    { "trend", "momentum", "volatility", "volume" },   # each {label, tone, note}
  "levels":     { "support", "resistance", "close", ... },
  "findings":   [{ "text", "tone" }, ...],   # deterministic sentences, tone pos|neg|neutral
  "as_of":      ISO date of last bar,
  "bars":       int,
}
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

MIN_BARS = 60  # below this the read is too thin to be honest about

Tone = str  # 'pos' | 'neg' | 'neutral'


# ── indicator math (pure, textbook) ──────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0.0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    # Degenerate windows: all-gain → 100, all-flat → neutral 50.
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    return rsi.fillna(50.0)


def _true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["Close"].shift(1)
    return pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - prev_close).abs(),
            (frame["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    return _true_range(frame).ewm(alpha=1 / period, adjust=False).mean()


def _adx(frame: pd.DataFrame, period: int = 14) -> tuple[float, float, float]:
    """Wilder ADX. Returns (adx, +di, -di) for the latest bar."""
    up = frame["High"].diff()
    down = -frame["Low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    atr = _true_range(frame).ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return (
        float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0.0,
        float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else 0.0,
        float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else 0.0,
    )


def _stochastic(frame: pd.DataFrame, period: int = 14, smooth: int = 3) -> tuple[float, float]:
    low_min = frame["Low"].rolling(period).min()
    high_max = frame["High"].rolling(period).max()
    k = 100 * (frame["Close"] - low_min) / (high_max - low_min).replace(0.0, np.nan)
    d = k.rolling(smooth).mean()
    return (
        float(k.iloc[-1]) if pd.notna(k.iloc[-1]) else 50.0,
        float(d.iloc[-1]) if pd.notna(d.iloc[-1]) else 50.0,
    )


def _obv(frame: pd.DataFrame) -> pd.Series:
    direction = np.sign(frame["Close"].diff()).fillna(0.0)
    return (direction * frame["Volume"]).cumsum()


def _mfi(frame: pd.DataFrame, period: int = 14) -> float:
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    flow = typical * frame["Volume"]
    up = flow.where(typical.diff() > 0, 0.0).rolling(period).sum()
    down = flow.where(typical.diff() < 0, 0.0).rolling(period).sum()
    ratio = up / down.replace(0.0, np.nan)
    mfi = 100 - 100 / (1 + ratio)
    return float(mfi.iloc[-1]) if pd.notna(mfi.iloc[-1]) else 50.0


def _cci(frame: pd.DataFrame, period: int = 20) -> float:
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    sma = typical.rolling(period).mean()
    mad = typical.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    cci = (typical - sma) / (0.015 * mad.replace(0.0, np.nan))
    return float(cci.iloc[-1]) if pd.notna(cci.iloc[-1]) else 0.0


def _aroon(frame: pd.DataFrame, period: int = 25) -> tuple[float, float]:
    highs = frame["High"].rolling(period + 1)
    lows = frame["Low"].rolling(period + 1)
    up = highs.apply(lambda x: 100 * float(np.argmax(x)) / period, raw=True)
    down = lows.apply(lambda x: 100 * float(np.argmin(x)) / period, raw=True)
    return (
        float(up.iloc[-1]) if pd.notna(up.iloc[-1]) else 50.0,
        float(down.iloc[-1]) if pd.notna(down.iloc[-1]) else 50.0,
    )


def _rolling_vwap(frame: pd.DataFrame, period: int = 20) -> Optional[float]:
    volume = frame["Volume"].rolling(period).sum()
    if float(volume.iloc[-1] or 0) <= 0:
        return None
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    vwap = (typical * frame["Volume"]).rolling(period).sum() / volume
    value = vwap.iloc[-1]
    return float(value) if pd.notna(value) else None


def _swing_levels(frame: pd.DataFrame, lookback: int = 40) -> tuple[float, float]:
    window = frame.iloc[-lookback:]
    return float(window["Low"].min()), float(window["High"].max())


def _cross_state(fast: pd.Series, slow: pd.Series, within: int = 60) -> Optional[dict[str, Any]]:
    """Golden/death cross of `fast` over `slow` within the last `within` bars."""
    above = fast > slow
    flips = above.ne(above.shift(1))
    recent = flips.iloc[-within:]
    if not bool(recent.any()):
        return None
    last_flip = recent[recent].index[-1]
    golden = bool(above.loc[last_flip])
    days_ago = int(len(fast.loc[last_flip:]) - 1)
    return {"type": "golden" if golden else "death", "days_ago": days_ago}


# ── assembly ─────────────────────────────────────────────────────────────────

def _row(key: str, label: str, value: str, detail: str, state: str, tone: Tone) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "detail": detail, "state": state, "tone": tone}


def build(frame: Optional[pd.DataFrame]) -> Optional[dict[str, Any]]:
    """Full technical-intelligence block, or None when history is too thin."""
    if frame is None or len(frame) < MIN_BARS:
        return None
    f = frame.dropna(subset=["Close", "High", "Low"])
    if len(f) < MIN_BARS:
        return None

    close = f["Close"]
    price = float(close.iloc[-1])
    findings: list[dict[str, str]] = []
    indicators: list[dict[str, Any]] = []

    # ── moving averages & crosses ────────────────────────────────────────────
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean() if len(f) >= 200 else None
    above50 = price > float(sma50.iloc[-1])
    sma50_rising = float(sma50.iloc[-1]) > float(sma50.iloc[-10])
    ma_state_parts = [f"price {'above' if above50 else 'below'} 50-day"]
    tone_ma: Tone = "pos" if above50 else "neg"
    if sma200 is not None and pd.notna(sma200.iloc[-1]):
        above200 = price > float(sma200.iloc[-1])
        ma_state_parts.append(f"{'above' if above200 else 'below'} 200-day")
        tone_ma = "pos" if (above50 and above200) else ("neg" if not (above50 or above200) else "neutral")
    indicators.append(_row(
        "sma", "Moving averages",
        f"20d {float(sma20.iloc[-1]):.2f} · 50d {float(sma50.iloc[-1]):.2f}"
        + (f" · 200d {float(sma200.iloc[-1]):.2f}" if sma200 is not None and pd.notna(sma200.iloc[-1]) else ""),
        ", ".join(ma_state_parts), "alignment", tone_ma,
    ))

    cross = _cross_state(sma50, sma200, within=60) if sma200 is not None else None
    if cross is not None:
        golden = cross["type"] == "golden"
        indicators.append(_row(
            "cross", "50/200 cross",
            "Golden cross" if golden else "Death cross",
            f"{cross['days_ago']} trading days ago", cross["type"],
            "pos" if golden else "neg",
        ))
        findings.append({
            "text": (
                f"A {'golden' if golden else 'death'} cross (50-day moving average crossing "
                f"{'above' if golden else 'below'} the 200-day) printed {cross['days_ago']} "
                f"trading days ago — a classic {'bullish' if golden else 'bearish'} long-term trend signal."
            ),
            "tone": "pos" if golden else "neg",
        })

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal_line = _ema(macd_line, 9)
    hist = float((macd_line - signal_line).iloc[-1])
    macd_bull = hist > 0
    indicators.append(_row(
        "macd", "MACD (12,26,9)", f"hist {hist:+.3f}",
        "momentum " + ("building" if macd_bull else "fading"),
        "bullish" if macd_bull else "bearish", "pos" if macd_bull else "neg",
    ))

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi = float(_rsi(close).iloc[-1])
    rsi_state = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"
    indicators.append(_row(
        "rsi", "RSI (14)", f"{rsi:.1f}", "14-day relative strength", rsi_state,
        "neg" if rsi > 70 else "pos" if rsi < 30 else "neutral",
    ))

    # ── ADX / trend strength ─────────────────────────────────────────────────
    adx, plus_di, minus_di = _adx(f)
    trending = adx >= 25
    direction_up = plus_di >= minus_di
    indicators.append(_row(
        "adx", "ADX (14)", f"{adx:.1f}",
        f"+DI {plus_di:.0f} / −DI {minus_di:.0f}",
        ("strong " + ("up" if direction_up else "down") + "trend") if trending else "no strong trend",
        ("pos" if direction_up else "neg") if trending else "neutral",
    ))

    # ── ATR / volatility regime ──────────────────────────────────────────────
    atr_series = _atr(f)
    atr_pct = 100 * float(atr_series.iloc[-1]) / price if price else 0.0
    atr_hist = (100 * atr_series / close).dropna()
    vol_pctile = float((atr_hist <= atr_hist.iloc[-1]).mean()) if len(atr_hist) else 0.5
    vol_state = "elevated" if vol_pctile > 0.8 else "compressed" if vol_pctile < 0.2 else "normal"
    indicators.append(_row(
        "atr", "ATR (14)", f"{atr_pct:.2f}% of price",
        f"{vol_pctile:.0%} percentile of its own year", vol_state,
        "neg" if vol_state == "elevated" else "neutral",
    ))

    # ── Bollinger ────────────────────────────────────────────────────────────
    mid = sma20
    std = close.rolling(20).std()
    upper = float((mid + 2 * std).iloc[-1])
    lower = float((mid - 2 * std).iloc[-1])
    width = upper - lower
    pct_b = (price - lower) / width if width else 0.5
    bb_state = "upper band" if pct_b > 0.95 else "lower band" if pct_b < 0.05 else "inside bands"
    indicators.append(_row(
        "bollinger", "Bollinger (20, 2σ)", f"%B {pct_b:.2f}",
        f"bandwidth {100 * width / price:.1f}% of price", bb_state,
        "neg" if pct_b > 0.95 else "pos" if pct_b < 0.05 else "neutral",
    ))

    # ── Stochastic ───────────────────────────────────────────────────────────
    k, d = _stochastic(f)
    stoch_state = "overbought" if k > 80 else "oversold" if k < 20 else "neutral"
    indicators.append(_row(
        "stoch", "Stochastic (14,3)", f"%K {k:.0f} / %D {d:.0f}", "range position", stoch_state,
        "neg" if k > 80 else "pos" if k < 20 else "neutral",
    ))

    # ── volume: OBV trend + MFI ──────────────────────────────────────────────
    has_volume = float(f["Volume"].iloc[-20:].sum()) > 0
    obv_confirms: Optional[bool] = None
    if has_volume:
        obv = _obv(f)
        obv_slope = float(obv.iloc[-1] - obv.iloc[-20])
        price_slope = float(close.iloc[-1] - close.iloc[-20])
        obv_confirms = (obv_slope > 0) == (price_slope > 0)
        indicators.append(_row(
            "obv", "On-balance volume", "rising" if obv_slope > 0 else "falling",
            "vs 20 days ago",
            "confirms price" if obv_confirms else "diverges from price",
            "pos" if obv_confirms else "neg",
        ))
        mfi = _mfi(f)
        indicators.append(_row(
            "mfi", "Money Flow Index (14)", f"{mfi:.0f}", "volume-weighted RSI",
            "overbought" if mfi > 80 else "oversold" if mfi < 20 else "neutral",
            "neg" if mfi > 80 else "pos" if mfi < 20 else "neutral",
        ))

    # ── CCI, ROC, Aroon ──────────────────────────────────────────────────────
    cci = _cci(f)
    indicators.append(_row(
        "cci", "CCI (20)", f"{cci:+.0f}", "deviation from typical price",
        "strong up-move" if cci > 100 else "strong down-move" if cci < -100 else "normal range",
        "pos" if cci > 100 else "neg" if cci < -100 else "neutral",
    ))
    roc63 = 100 * (price / float(close.iloc[-64]) - 1) if len(close) >= 64 else None
    if roc63 is not None:
        indicators.append(_row(
            "roc", "Rate of change (63d)", f"{roc63:+.1f}%", "quarterly price momentum",
            "positive" if roc63 > 0 else "negative", "pos" if roc63 > 0 else "neg",
        ))
    aroon_up, aroon_down = _aroon(f)
    indicators.append(_row(
        "aroon", "Aroon (25)", f"up {aroon_up:.0f} / down {aroon_down:.0f}",
        "time since 25-day high/low",
        "uptrend fresh" if aroon_up > 70 and aroon_down < 30
        else "downtrend fresh" if aroon_down > 70 and aroon_up < 30 else "mixed",
        "pos" if aroon_up > 70 and aroon_down < 30
        else "neg" if aroon_down > 70 and aroon_up < 30 else "neutral",
    ))

    # ── VWAP ─────────────────────────────────────────────────────────────────
    vwap = _rolling_vwap(f) if has_volume else None
    if vwap is not None:
        above_vwap = price > vwap
        indicators.append(_row(
            "vwap", "VWAP (20d rolling)", f"{vwap:.2f}",
            f"price {'above' if above_vwap else 'below'} the volume-weighted average",
            "above" if above_vwap else "below", "pos" if above_vwap else "neg",
        ))

    # ── support / resistance ─────────────────────────────────────────────────
    support, resistance = _swing_levels(f)
    dist_support = 100 * (price - support) / price if price else 0.0
    dist_resistance = 100 * (resistance - price) / price if price else 0.0
    levels = {
        "close": round(price, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "support_distance_pct": round(dist_support, 1),
        "resistance_distance_pct": round(dist_resistance, 1),
        "lookback_days": 40,
    }

    # ── regimes ──────────────────────────────────────────────────────────────
    trend_regime = (
        {"label": "Strong uptrend" if direction_up else "Strong downtrend",
         "tone": "pos" if direction_up else "neg",
         "note": f"ADX {adx:.0f} with {'+DI' if direction_up else '−DI'} leading"}
        if trending else
        {"label": "Range-bound", "tone": "neutral", "note": f"ADX {adx:.0f} — below the 25 trend threshold"}
    )
    momentum_votes = sum([macd_bull, rsi > 50, (roc63 or 0) > 0])
    momentum_regime = {
        "label": "Bullish momentum" if momentum_votes >= 2 else "Bearish momentum" if momentum_votes <= 1 else "Mixed",
        "tone": "pos" if momentum_votes >= 2 else "neg",
        "note": f"{momentum_votes}/3 of MACD, RSI, quarterly ROC point up",
    }
    volatility_regime = {
        "label": vol_state.capitalize() + " volatility",
        "tone": "neg" if vol_state == "elevated" else "neutral",
        "note": f"ATR at the {vol_pctile:.0%} percentile of its own year",
    }
    volume_regime = (
        {"label": "Volume confirms" if obv_confirms else "Volume diverges",
         "tone": "pos" if obv_confirms else "neg",
         "note": "OBV and price move together" if obv_confirms else "OBV disagrees with price — moves lack participation"}
        if obv_confirms is not None else
        {"label": "No volume data", "tone": "neutral", "note": "provider returned no volume for this window"}
    )

    # ── findings (deterministic sentences, most load-bearing first) ──────────
    findings.insert(0, {
        "text": (
            f"Trend: {trend_regime['label'].lower()} ({trend_regime['note']}); "
            f"price sits {dist_support:.1f}% above 40-day swing support ({support:.2f}) and "
            f"{dist_resistance:.1f}% below swing resistance ({resistance:.2f})."
        ),
        "tone": trend_regime["tone"],
    })
    findings.append({
        "text": f"Momentum: {momentum_regime['note']} — {momentum_regime['label'].lower()}.",
        "tone": momentum_regime["tone"],
    })
    if vol_state != "normal":
        findings.append({
            "text": (
                f"Volatility is {vol_state} — daily range is {atr_pct:.1f}% of price, the "
                f"{vol_pctile:.0%} percentile of the past year"
                + (". Position sizing matters more than usual here." if vol_state == "elevated"
                   else ". Compressed ranges often precede larger moves.")
            ),
            "tone": "neg" if vol_state == "elevated" else "neutral",
        })
    if obv_confirms is False:
        findings.append({
            "text": "On-balance volume diverges from price over the last month — the current move has weak volume sponsorship.",
            "tone": "neg",
        })
    if rsi > 70 or k > 80:
        findings.append({
            "text": f"Short-term stretched: RSI {rsi:.0f}, stochastic %K {k:.0f} — entries here have historically faced near-term pullback risk.",
            "tone": "neg",
        })
    elif rsi < 30 or k < 20:
        findings.append({
            "text": f"Short-term washed out: RSI {rsi:.0f}, stochastic %K {k:.0f} — oversold readings in an intact trend often mark tactical lows.",
            "tone": "pos",
        })

    return {
        "indicators": indicators,
        "regimes": {
            "trend": trend_regime,
            "momentum": momentum_regime,
            "volatility": volatility_regime,
            "volume": volume_regime,
        },
        "levels": levels,
        "findings": findings,
        "as_of": f.index[-1].date().isoformat(),
        "bars": int(len(f)),
    }
