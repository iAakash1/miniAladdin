"""
OmniSignal quantitative scoring engine (v2).

Implements docs/SCORING.md constant-for-constant. Pure functions over a
daily OHLCV DataFrame (~252 bars) plus point-in-time fundamentals,
sentiment and the SRM. Emits an explainable ScoreCard whose per-factor
contribution rows sum exactly to the raw score.

No fitting, no deep learning: robust statistics + literature-anchored
priors, all named and documented.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from src.models import SignalVerdict
from src.scoring.fomc_calendar import business_days_to_next_fomc

logger = logging.getLogger(__name__)

# ── Constants (docs/SCORING.md §1–§5) ─────────────────────────────────────────

MAD_CONSISTENCY = 1.4826          # MAD → σ under normality
WINSOR_Z = 3.0                    # ±3σ outlier fence
SQUASH_SCALE = 2.0                # s = tanh(z / 2)
MIN_BARS = 60                     # below this the caller falls back to v1

# Family weights ∝ IR² (Grinold–Kahn), IRs from the factor literature (§3)
BASE_WEIGHTS = {"momentum": 0.45, "fundamental": 0.30, "news": 0.25}

# Regime multipliers (§3)
HIGH_VOL_PERCENTILE = 0.80
HIGH_VOL_MOMENTUM_MULT = 0.5      # Daniel–Moskowitz momentum-crash regimes
EARNINGS_WINDOW_DAYS = 5
EARNINGS_TARGET_MULT = 0.5        # stale consensus into the print
EARNINGS_NEWS_MULT = 1.5          # information concentrates in news
FOMC_WINDOW_DAYS = 3
FOMC_CONFIDENCE_MULT = 0.85
FOMC_GATE_CENTER_SHIFT = 0.05     # gate center 1.10 → 1.05 near FOMC

# Macro gate (§2): g = 1 − λ·max(0, tanh((SRM − center)/scale)), bullish only
GATE_CENTER = 1.10
GATE_SCALE = 0.15
GATE_LAMBDA = 0.5

# News shrinkage prior (§2): N = mean · n/(n+n0)
NEWS_PRIOR_STRENGTH = 6

# Point-in-time fundamental priors (no per-name history exists for these;
# scales are long-run cross-sectional dispersions, stated in §2)
TARGET_UPSIDE_SIGMA = 0.10        # 10 % upside ≈ one sigma of typical consensus upside
EARNINGS_YIELD_CENTER = 0.05      # long-run equity earnings yield
EARNINGS_YIELD_SIGMA = 0.025
PE_GAP_SIGMA = 0.15
ANALYST_COUNT_PRIOR = 5           # shrinkage prior when analyst count known
ANALYST_DEFAULT_SHRINK = 0.6      # count unknown → fixed shrink toward 0

# Verdict cut points in composite units (≈ 0.5 σ_A and 1.4 σ_A, §4)
CUT_STRONG = 0.40
CUT_ACTION = 0.15

# Uncertainty floors (§5)
EVENT_U_EARNINGS = 0.25
EVENT_U_FOMC = 0.15
CONFIDENCE_FLOOR, CONFIDENCE_CAP = 5.0, 95.0

# Risk score blend (§5)
RISK_WEIGHTS = {"volatility": 0.40, "drawdown": 0.25, "beta": 0.20, "srm": 0.15}


# ── Output models ─────────────────────────────────────────────────────────────

class FactorRow(BaseModel):
    name: str
    family: str
    value: Optional[float] = None      # raw factor value
    z: Optional[float] = None          # robust z (post-winsor)
    score: Optional[float] = None      # tanh-squashed, sign = bullish
    contribution: float = 0.0          # w_family · score / n_family


class ConfidenceLoss(BaseModel):
    component: str
    points: int                        # losses sum to 100 − confidence


class ScoreCard(BaseModel):
    raw_score: float                   # A (gated)
    ungated_score: float               # A0
    verdict: str
    raw_verdict: str                   # mapping of A0 (pre-gate)
    confidence: int = Field(..., ge=0, le=100)
    confidence_losses: list[ConfidenceLoss]
    uncertainty: float
    uncertainty_components: dict[str, float]
    conflict_index: float
    momentum_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    news_score: Optional[float] = None
    macro_gate: float
    risk_score: int = Field(..., ge=0, le=100)
    risk_components: dict[str, float]
    weights_used: dict[str, float]
    regimes: list[str]
    factors: list[FactorRow]
    data_completeness: float
    model_version: str = "scoring-v2"


# ── Robust normalization (§1) ─────────────────────────────────────────────────

def robust_z(history: pd.Series) -> Optional[float]:
    """Robust z of the last value against its own trailing distribution."""
    clean = history.dropna()
    if len(clean) < 20:
        return None
    median = float(clean.median())
    mad = float((clean - median).abs().median())
    if mad <= 1e-12:
        return None
    z = (float(clean.iloc[-1]) - median) / (MAD_CONSISTENCY * mad)
    return float(np.clip(z, -WINSOR_Z, WINSOR_Z))


def squash(z: Optional[float]) -> Optional[float]:
    return None if z is None else float(math.tanh(z / SQUASH_SCALE))


def _prior_z(value: float, center: float, sigma: float) -> float:
    return float(np.clip((value - center) / sigma, -WINSOR_Z, WINSOR_Z))


# ── Factor computation (§2) ───────────────────────────────────────────────────

def _rsi_series(closes: pd.Series, window: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd_hist_series(closes: pd.Series) -> pd.Series:
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return (macd - signal) / closes  # price-normalized


def momentum_factors(frame: pd.DataFrame, spy: Optional[pd.DataFrame]) -> list[FactorRow]:
    closes = frame["Close"]
    rows: list[FactorRow] = []

    def add(name: str, history: pd.Series, sign: float = 1.0, value: Optional[float] = None):
        z = robust_z(history)
        s = squash(z if z is None else z * sign)
        rows.append(FactorRow(
            name=name, family="momentum",
            value=value if value is not None else (float(history.dropna().iloc[-1]) if len(history.dropna()) else None),
            z=z, score=s,
        ))

    add("r21", closes.pct_change(21))
    add("r63", closes.pct_change(63))
    add("rsi_dev", _rsi_series(closes), sign=-1.0)          # contrarian (§2)
    add("macd_hist", _macd_hist_series(closes))
    add("rev5", closes.pct_change(5), sign=-1.0)            # short-term reversal

    if "Volume" in frame.columns and frame["Volume"].fillna(0).sum() > 0:
        volume = frame["Volume"].astype(float)
        ratio = volume.rolling(21).mean() / volume.rolling(63).mean()
        r21_latest = closes.pct_change(21).dropna()
        direction = 1.0 if (len(r21_latest) and r21_latest.iloc[-1] >= 0) else -1.0
        add("vol_confirm", ratio, sign=direction)

    add("high52_prox", closes / closes.rolling(252, min_periods=120).max())

    if spy is not None and len(spy) >= 63:
        stock_r21 = closes.pct_change(21)
        spy_r21 = spy["Close"].pct_change(21)
        aligned = (stock_r21 - spy_r21.reindex(stock_r21.index)).dropna()
        if len(aligned) >= 20:
            add("rel21_vs_spy", aligned)

    return rows


def fundamental_factors(
    price: Optional[float],
    pe_ratio: Optional[float],
    forward_pe: Optional[float],
    analyst_target: Optional[float],
    analyst_count: Optional[int],
) -> list[FactorRow]:
    rows: list[FactorRow] = []

    if analyst_target and price and price > 0:
        upside = (analyst_target - price) / price
        shrink = (
            analyst_count / (analyst_count + ANALYST_COUNT_PRIOR)
            if analyst_count else ANALYST_DEFAULT_SHRINK
        )
        z = _prior_z(upside * shrink, 0.0, TARGET_UPSIDE_SIGMA)
        rows.append(FactorRow(name="target_upside", family="fundamental",
                              value=round(upside, 4), z=z, score=squash(z)))

    if pe_ratio and pe_ratio > 0:
        earnings_yield = 1.0 / pe_ratio
        z = _prior_z(earnings_yield, EARNINGS_YIELD_CENTER, EARNINGS_YIELD_SIGMA)
        rows.append(FactorRow(name="earnings_yield", family="fundamental",
                              value=round(earnings_yield, 4), z=z, score=squash(z)))

    if pe_ratio and forward_pe and pe_ratio > 0 and forward_pe > 0:
        gap = float(np.clip((pe_ratio - forward_pe) / pe_ratio, -1, 1))
        z = _prior_z(gap, 0.0, PE_GAP_SIGMA)
        rows.append(FactorRow(name="pe_gap", family="fundamental",
                              value=round(gap, 4), z=z, score=squash(z)))

    return rows


def news_factor(avg_score: Optional[float], headline_count: int) -> list[FactorRow]:
    if avg_score is None or headline_count <= 0:
        return []
    shrunk = avg_score * headline_count / (headline_count + NEWS_PRIOR_STRENGTH)
    return [FactorRow(name="sentiment", family="news",
                      value=round(avg_score, 4), z=None, score=round(shrunk, 4))]


# ── Regimes (§3) ──────────────────────────────────────────────────────────────

def detect_regimes(
    frame: pd.DataFrame,
    days_to_earnings: Optional[int],
    today: Optional[date] = None,
) -> list[str]:
    regimes: list[str] = []
    closes = frame["Close"]
    daily = closes.pct_change().dropna()
    if len(daily) >= 120:
        rolling_vol = daily.rolling(21).std().dropna()
        if len(rolling_vol) >= 60:
            current = rolling_vol.iloc[-1]
            if current >= rolling_vol.quantile(HIGH_VOL_PERCENTILE):
                regimes.append("high_volatility")
    if days_to_earnings is not None and 0 <= days_to_earnings <= EARNINGS_WINDOW_DAYS:
        regimes.append("earnings_window")
    fomc_days = business_days_to_next_fomc(today or date.today())
    if fomc_days is not None and fomc_days <= FOMC_WINDOW_DAYS:
        regimes.append("fomc_window")
    return regimes


def regime_weights(regimes: list[str]) -> dict[str, float]:
    weights = dict(BASE_WEIGHTS)
    if "high_volatility" in regimes:
        weights["momentum"] *= HIGH_VOL_MOMENTUM_MULT
    if "earnings_window" in regimes:
        weights["news"] *= EARNINGS_NEWS_MULT
    total = sum(weights.values())
    return {family: w / total for family, w in weights.items()}


# ── Composite pieces (§4–§5) ──────────────────────────────────────────────────

def macro_gate(srm: float, regimes: list[str]) -> float:
    center = GATE_CENTER - (FOMC_GATE_CENTER_SHIFT if "fomc_window" in regimes else 0.0)
    return 1.0 - GATE_LAMBDA * max(0.0, math.tanh((srm - center) / GATE_SCALE))


def conflict_index(family_scores: dict[str, float], weights: dict[str, float]) -> float:
    names = [name for name, value in family_scores.items() if value is not None]
    numerator = denominator = 0.0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pair_weight = weights.get(a, 0) * weights.get(b, 0)
            denominator += pair_weight
            if family_scores[a] * family_scores[b] < 0:
                numerator += pair_weight * min(abs(family_scores[a]), abs(family_scores[b]))
    return numerator / denominator if denominator > 0 else 0.0


def map_verdict(score: float) -> SignalVerdict:
    if score >= CUT_STRONG:
        return SignalVerdict.STRONG_BUY
    if score >= CUT_ACTION:
        return SignalVerdict.BUY
    if score <= -CUT_STRONG:
        return SignalVerdict.STRONG_SELL
    if score <= -CUT_ACTION:
        return SignalVerdict.SELL
    return SignalVerdict.HOLD


def risk_score_components(
    frame: pd.DataFrame, beta: Optional[float], srm: float
) -> tuple[int, dict[str, float]]:
    closes = frame["Close"]
    daily = closes.pct_change().dropna()
    components: dict[str, float] = {}

    if len(daily) >= 60:
        rolling_vol = daily.rolling(21).std().dropna()
        components["volatility"] = float((rolling_vol <= rolling_vol.iloc[-1]).mean() * 100)
        peak = closes.cummax()
        drawdowns = ((closes - peak) / peak).abs()
        components["drawdown"] = float((drawdowns <= drawdowns.iloc[-1]).mean() * 100)
    else:
        components["volatility"] = 50.0
        components["drawdown"] = 50.0

    components["beta"] = float(np.clip((beta - 1.0) * 100, 0, 100)) if beta is not None else 50.0
    components["srm"] = float(np.clip((srm - 0.5) / 1.1 * 100, 0, 100))

    total = sum(RISK_WEIGHTS[key] * components[key] for key in RISK_WEIGHTS)
    return int(round(total)), {key: round(value, 1) for key, value in components.items()}


# ── Main entry point ──────────────────────────────────────────────────────────

def score_ticker(
    frame: pd.DataFrame,
    srm: float,
    price: Optional[float] = None,
    pe_ratio: Optional[float] = None,
    forward_pe: Optional[float] = None,
    analyst_target: Optional[float] = None,
    analyst_count: Optional[int] = None,
    beta: Optional[float] = None,
    sentiment_avg: Optional[float] = None,
    headline_count: int = 0,
    spy_frame: Optional[pd.DataFrame] = None,
    days_to_earnings: Optional[int] = None,
    data_confidence: float = 1.0,
    today: Optional[date] = None,
) -> Optional[ScoreCard]:
    """Compute the full explainable ScoreCard. Returns None below MIN_BARS."""
    if frame is None or len(frame) < MIN_BARS:
        return None

    regimes = detect_regimes(frame, days_to_earnings, today)
    weights = regime_weights(regimes)

    rows = momentum_factors(frame, spy_frame)
    fundamental_rows = fundamental_factors(price, pe_ratio, forward_pe, analyst_target, analyst_count)
    if "earnings_window" in regimes:
        for row in fundamental_rows:
            if row.name == "target_upside" and row.score is not None:
                row.score = round(row.score * EARNINGS_TARGET_MULT, 4)  # §3: stale consensus
    rows += fundamental_rows
    rows += news_factor(sentiment_avg, headline_count)

    # Within-momentum reweighting in high-vol regimes: contrarian members double (§3)
    contrarian = {"rsi_dev", "rev5"}
    family_members: dict[str, list[FactorRow]] = {"momentum": [], "fundamental": [], "news": []}
    for row in rows:
        if row.score is not None:
            family_members[row.family].append(row)

    family_scores: dict[str, Optional[float]] = {}
    for family, members in family_members.items():
        if not members:
            family_scores[family] = None
            continue
        if family == "momentum" and "high_volatility" in regimes:
            member_weights = [2.0 if member.name in contrarian else 1.0 for member in members]
        else:
            member_weights = [1.0] * len(members)
        total_weight = sum(member_weights)
        family_scores[family] = sum(
            weight * member.score for weight, member in zip(member_weights, members)
        ) / total_weight
        for weight, member in zip(member_weights, members):
            member.contribution = round(weights[family] * member.score * weight / total_weight, 4)

    active = {family: value for family, value in family_scores.items() if value is not None}
    if not active:
        return None

    # Renormalize weights over families that actually produced a score
    active_weight_total = sum(weights[family] for family in active)
    effective_weights = {family: weights[family] / active_weight_total for family in active}
    ungated = sum(effective_weights[family] * active[family] for family in active)

    gate = macro_gate(srm, regimes)
    gated = ungated * gate if ungated > 0 else ungated

    conflict = conflict_index(active, effective_weights)

    # Uncertainty (§5)
    weighted_var = sum(
        effective_weights[family] * (active[family] - ungated) ** 2 for family in active
    )
    u_disp = min(1.0, math.sqrt(weighted_var))  # family scores live in [−1,1]
    total_possible = len(rows) if rows else 1
    computable = sum(1 for row in rows if row.score is not None)
    u_data = 1.0 - (computable / max(total_possible, 1)) * max(0.0, min(1.0, data_confidence))
    u_event = 0.0
    if "earnings_window" in regimes:
        u_event = 1.0 - (1.0 - u_event) * (1.0 - EVENT_U_EARNINGS)
    if "fomc_window" in regimes:
        u_event = 1.0 - (1.0 - u_event) * (1.0 - EVENT_U_FOMC)
    uncertainty = 1.0 - (1.0 - u_disp) * (1.0 - u_data) * (1.0 - u_event)

    # Confidence with exact additive loss attribution (§5/§6)
    losses: list[ConfidenceLoss] = []
    confidence = 100.0
    for label, factor in (
        ("Family dispersion", 1.0 - u_disp),
        ("Data completeness", 1.0 - u_data),
        ("Event proximity", 1.0 - u_event),
        ("Conflicting signals", 1.0 - conflict / 2.0),
    ):
        after = confidence * factor
        if round(confidence - after) != 0:
            losses.append(ConfidenceLoss(component=label, points=round(confidence - after)))
        confidence = after
    if "fomc_window" in regimes:
        after = confidence * FOMC_CONFIDENCE_MULT
        losses.append(ConfidenceLoss(component="FOMC caution", points=round(confidence - after)))
        confidence = after
    confidence = float(np.clip(confidence, CONFIDENCE_FLOOR, CONFIDENCE_CAP))

    risk, risk_parts = risk_score_components(frame, beta, srm)

    return ScoreCard(
        raw_score=round(gated, 4),
        ungated_score=round(ungated, 4),
        verdict=map_verdict(gated).value,
        raw_verdict=map_verdict(ungated).value,
        confidence=int(round(confidence)),
        confidence_losses=losses,
        uncertainty=round(uncertainty, 4),
        uncertainty_components={
            "dispersion": round(u_disp, 4),
            "data": round(u_data, 4),
            "event": round(u_event, 4),
        },
        conflict_index=round(conflict, 4),
        momentum_score=None if family_scores["momentum"] is None else round(family_scores["momentum"], 4),
        fundamental_score=None if family_scores["fundamental"] is None else round(family_scores["fundamental"], 4),
        news_score=None if family_scores["news"] is None else round(family_scores["news"], 4),
        macro_gate=round(gate, 4),
        risk_score=risk,
        risk_components=risk_parts,
        weights_used={family: round(weight, 4) for family, weight in effective_weights.items()},
        regimes=regimes,
        factors=rows,
        data_completeness=round(computable / max(total_possible, 1), 4),
    )
