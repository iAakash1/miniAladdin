"""
OmniSignal quantitative scoring engine (v2.1).

Implements docs/SCORING.md (v2 + v2.1 amendments) constant-for-constant.
v2.1 changes, from the referee review (docs/QUANT-REVIEW.md):

  * 12-1 momentum is the anchor (Jegadeesh–Titman 1993); r21 demoted to a
    timing feature; MACD demoted (trend-collinear).
  * RSI-dev and 5d-reversal merged into ONE reversal sleeve, active only in
    high-volatility regimes (Nagel 2012); RSI remains a display statistic.
  * Macro gate is probabilistic (stress probability from term spread, NFCI,
    credit spread, VIX percentile) and applies to the MOMENTUM sleeve only —
    value/quality/news are not macro-suppressed (AFP QMJ logic).
  * New slow sleeves: quality (GP/A — Novy-Marx 2013; net issuance —
    Pontiff–Woodgate 2008; asset growth — Cooper et al. 2008) and PEAD
    (Bernard–Thomas 1989) inside fundamental.
  * Confidence gains u_fresh (data staleness), u_model (realized rolling IC
    on this name), u_stab (verdict flip rate) — every deduction itemized.
  * Risk v2: CVaR, semi-deviation, drawdown state, vol regime, beta
    stability, idiosyncratic share, Amihud liquidity, macro, sector — each
    component exposes weight × percentile = contribution.

No fitting, no deep learning: robust statistics + literature-anchored,
named constants.
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

# ── Normalization (unchanged from v2, docs/SCORING.md §1) ────────────────────

MAD_CONSISTENCY = 1.4826
WINSOR_Z = 3.0
SQUASH_SCALE = 2.0
MIN_BARS = 60

# ── Sleeves & weights (v2.1 §3) ───────────────────────────────────────────────
# IR² logic retained; quality enters at the literature's long-horizon IR≈0.45
# scaled down for our 21d horizon; reversal is regime-conditional.
BASE_WEIGHTS = {
    "momentum": 0.40,
    "fundamental": 0.20,   # value + analyst + PEAD
    "quality": 0.15,       # slow sleeve — must never dominate momentum
    "news": 0.20,
    "reversal": 0.05,      # near-zero outside high-vol regimes
}
REVERSAL_WEIGHT_HIGH_VOL = 0.20   # funded by the momentum cut below
HIGH_VOL_MOMENTUM_MULT = 0.5      # Daniel–Moskowitz momentum-crash regimes

# Within-momentum member weights (v2.1 §1): the anchor is 12-1; r21 is
# timing-only. MACD was REMOVED from scoring after the synthetic audit
# (docs/FACTOR-AUDIT.md): IC ≈ 0 in every test world while correlating
# −0.65…−0.81 with the reversal sleeve — a redundant heuristic. It remains
# a display statistic in the technicals panel via the prediction agent.
MOMENTUM_MEMBER_WEIGHTS = {
    "r12_1": 2.0,
    "r63": 1.0,
    "r21": 0.5,
    "vol_confirm": 1.0,
    "high52_prox": 1.0,
    "rel21_vs_spy": 1.0,
}

HIGH_VOL_PERCENTILE = 0.80
EARNINGS_WINDOW_DAYS = 5
EARNINGS_TARGET_MULT = 0.5
EARNINGS_NEWS_MULT = 1.5
FOMC_WINDOW_DAYS = 3
FOMC_CONFIDENCE_MULT = 0.85

# ── Probabilistic macro gate (v2.1 §9) ────────────────────────────────────────
# p_stress = logistic(B0 + B_TERM·(−term_spread) + B_NFCI·nfci + B_CREDIT·credit_z
#                     + B_VIX·(vix_pct − 0.5)·2)
# B_TERM anchors to Estrella–Mishkin (1998) probit slope ≈0.63 → logit ≈1.07.
# Other inputs are standardized; unit-scale priors 0.5 each, documented as
# such (no fitting). B0 = −2.0 puts the calm-regime baseline near p≈0.10.
GATE_B0 = -2.0
GATE_B_TERM = 1.07
GATE_B_NFCI = 0.5
GATE_B_CREDIT = 0.5
GATE_B_VIX = 0.5
GATE_LAMBDA = 0.5                  # worst case halves the momentum sleeve
FOMC_STRESS_BUMP = 0.05            # pre-FOMC caution, one small step
# Legacy fallback (SRM-only) when fast inputs are unavailable:
LEGACY_GATE_CENTER = 1.10
LEGACY_GATE_SCALE = 0.15

# News shrinkage prior — now consumes EFFECTIVE evidence (news_scoring.py)
NEWS_PRIOR_STRENGTH = 6.0

# Fundamental priors (v2 §2, unchanged)
TARGET_UPSIDE_SIGMA = 0.10
EARNINGS_YIELD_CENTER = 0.05
EARNINGS_YIELD_SIGMA = 0.025
PE_GAP_SIGMA = 0.15
ANALYST_COUNT_PRIOR = 5
ANALYST_DEFAULT_SHRINK = 0.6

# Quality priors (v2.1 §2 — cross-sectional location/scale from the cited papers)
GPA_CENTER = 0.33                  # Novy-Marx: mean gross-profits/assets ≈ 1/3
GPA_SIGMA = 0.15
ISSUANCE_SIGMA = 0.05              # ±5% share-count change ≈ 1σ (P–W 2008)
ASSET_GROWTH_CENTER = 0.08         # typical corporate asset growth
ASSET_GROWTH_SIGMA = 0.15          # Cooper et al. deciles span

# PEAD (v2.1 §8): SUE proxy scale and drift horizon
PEAD_SURPRISE_SIGMA = 5.0          # 5% EPS surprise ≈ 1σ (conservative)
PEAD_HORIZON_DAYS = 60             # Bernard–Thomas drift window
PEAD_MAX_ABS = 0.6                 # cap: an old large surprise can't dominate

# 52-week-high proximity prior (v2.1): the George–Hwang effect IS the level,
# so a prior scale replaces self-history z (which nulls out on steady trends).
# Center 0.85 ≈ median proximity for listed large-caps; σ 0.10 spans the
# effect's documented deciles.
HIGH52_CENTER = 0.85
HIGH52_SIGMA = 0.10

# Verdict cut points (unchanged, v2 §4)
CUT_STRONG = 0.40
CUT_ACTION = 0.15

# Confidence (v2 §5 + v2.1 additions)
EVENT_U_EARNINGS = 0.25
EVENT_U_FOMC = 0.15
CONFIDENCE_FLOOR, CONFIDENCE_CAP = 5.0, 95.0
FRESH_TAU_PRICE_DAYS = 5.0         # weekend + a holiday is normal; beyond → stale
FRESH_TAU_NEWS_HOURS = 72.0
MODEL_IC_REF = 0.05                # rolling IC at/above this ⇒ no model doubt
U_MODEL_MAX = 0.30                 # unmeasured/zero IC costs at most 30%
U_STAB_PER_FLIP = 0.10             # each verdict flip in last 6 signals
U_STAB_MAX = 0.30
U_MACRO_MAX = 0.30                 # maximal at p_stress = 0.5 (peak ambiguity)

# Risk v2 (v2.1 §6) — weights ordered by directness of loss measurement.
# tail_risk = percentile of the rolling 5% daily-return quantile (VaR95);
# vectorized, and CVaR of the latest window is reported as the component
# value context. All percentiles are vs the name's own history.
RISK_WEIGHTS = {
    "downside_dev": 0.20,
    "tail_risk": 0.15,
    "drawdown": 0.12,
    "vol_regime": 0.13,
    "beta": 0.10,
    "idiosyncratic": 0.10,
    "liquidity": 0.08,
    "macro": 0.07,
    "sector": 0.05,
}


# ── Output models ─────────────────────────────────────────────────────────────

class FactorRow(BaseModel):
    name: str
    family: str
    value: Optional[float] = None
    z: Optional[float] = None
    score: Optional[float] = None
    contribution: float = 0.0      # sums (post-gate) to raw_score


class ConfidenceLoss(BaseModel):
    component: str
    points: int


class RiskComponent(BaseModel):
    name: str
    percentile: float              # 0–100 within own history / prior scale
    weight: float
    contribution: float            # weight × percentile


class ScoreCard(BaseModel):
    raw_score: float
    ungated_score: float
    verdict: str
    raw_verdict: str
    confidence: int = Field(..., ge=0, le=100)
    confidence_losses: list[ConfidenceLoss]
    uncertainty: float
    uncertainty_components: dict[str, float]
    conflict_index: float
    momentum_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    quality_score: Optional[float] = None
    news_score: Optional[float] = None
    reversal_score: Optional[float] = None
    macro_gate: float              # gate applied to the momentum sleeve
    stress_probability: Optional[float] = None
    risk_score: int = Field(..., ge=0, le=100)
    risk_components: list[RiskComponent]
    weights_used: dict[str, float]
    regimes: list[str]
    factors: list[FactorRow]
    data_completeness: float
    model_version: str = "scoring-v2.1"


# ── Robust normalization (unchanged) ─────────────────────────────────────────

def robust_z(history: pd.Series) -> Optional[float]:
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


def _robust_daily_sigma(closes: pd.Series) -> Optional[float]:
    """MAD-based σ of daily returns — outlier-resistant volatility unit."""
    daily = closes.pct_change().dropna()
    if len(daily) < 40:
        return None
    mad = float((daily - daily.median()).abs().median())
    sigma = MAD_CONSISTENCY * mad
    return sigma if sigma > 1e-9 else None


def return_tstat_z(closes: pd.Series, horizon: int, skip: int = 0) -> tuple[Optional[float], Optional[float]]:
    """
    (value, z) for a return-type factor, normalized as a t-statistic:

        z = r / (σ_daily · √horizon)

    i.e. "how many multiples of its own noise is this move". Self-history
    z-scores null out on steady trends (a stock down 30% reads as 'normal
    for itself'); the t-stat preserves trend sign, stays per-name adaptive
    through σ, and keeps outlier robustness via the MAD σ + winsorization.
    """
    needed = horizon + skip + 1
    if len(closes) < needed:
        return None, None
    end = float(closes.iloc[-1 - skip]) if skip else float(closes.iloc[-1])
    start = float(closes.iloc[-1 - skip - horizon])
    if start <= 0:
        return None, None
    r = end / start - 1
    sigma = _robust_daily_sigma(closes)
    if sigma is None:
        return r, None
    z = float(np.clip(r / (sigma * math.sqrt(horizon)), -WINSOR_Z, WINSOR_Z))
    return r, z


# ── Factor computation ────────────────────────────────────────────────────────

def _rsi_series(closes: pd.Series, window: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def momentum_factors(frame: pd.DataFrame, spy: Optional[pd.DataFrame]) -> list[FactorRow]:
    closes = frame["Close"]
    rows: list[FactorRow] = []

    def add_tstat(name: str, horizon: int, skip: int = 0):
        value, z = return_tstat_z(closes, horizon, skip)
        if z is None:
            return
        rows.append(FactorRow(name=name, family="momentum",
                              value=round(value, 4) if value is not None else None,
                              z=z, score=squash(z)))

    def add_dist(name: str, history: pd.Series, sign: float = 1.0):
        z = robust_z(history)
        s = squash(z if z is None else z * sign)
        latest = history.dropna()
        rows.append(FactorRow(
            name=name, family="momentum",
            value=float(latest.iloc[-1]) if len(latest) else None,
            z=z, score=s,
        ))

    # Return-type factors: t-stat normalization (trend sign preserved).
    add_tstat("r12_1", horizon=231, skip=21)   # 12-1 skip-month (J–T 1993)
    add_tstat("r63", horizon=63)
    add_tstat("r21", horizon=21)               # timing feature (demoted weight)
    # MACD removed from scoring (audit: IC≈0, redundant) — display-only elsewhere.

    if "Volume" in frame.columns and frame["Volume"].fillna(0).sum() > 0:
        volume = frame["Volume"].astype(float)
        ratio = volume.rolling(21).mean() / volume.rolling(63).mean()
        r21_value, _ = return_tstat_z(closes, 21)
        direction = 1.0 if (r21_value is not None and r21_value >= 0) else -1.0
        add_dist("vol_confirm", ratio, sign=direction)

    # 52w-high proximity: LEVEL prior (the anchoring effect is the level).
    high = closes.rolling(252, min_periods=120).max()
    if len(high.dropna()):
        proximity = float(closes.iloc[-1] / high.dropna().iloc[-1])
        z = _prior_z(proximity, HIGH52_CENTER, HIGH52_SIGMA)
        rows.append(FactorRow(name="high52_prox", family="momentum",
                              value=round(proximity, 4), z=z, score=squash(z)))

    # Relative strength: t-stat of the 21d relative return.
    if spy is not None and len(spy) >= 63:
        stock_daily = closes.pct_change()
        spy_daily = spy["Close"].pct_change().reindex(stock_daily.index)
        relative = (stock_daily - spy_daily).dropna()
        if len(relative) >= 40:
            rel_21 = float(relative.tail(21).sum())
            mad = float((relative - relative.median()).abs().median())
            sigma = MAD_CONSISTENCY * mad
            if sigma > 1e-9:
                z = float(np.clip(rel_21 / (sigma * math.sqrt(21)), -WINSOR_Z, WINSOR_Z))
                rows.append(FactorRow(name="rel21_vs_spy", family="momentum",
                                      value=round(rel_21, 4), z=z, score=squash(z)))
    return rows


def reversal_factor(frame: pd.DataFrame) -> list[FactorRow]:
    """
    ONE merged reversal component (v2.1 §1): the mean of the contrarian
    readings of the 5d return t-stat and the RSI distribution z. RSI remains
    a display statistic elsewhere; here it only feeds this single sleeve.
    """
    closes = frame["Close"]
    rev_value, z_rev = return_tstat_z(closes, 5)
    z_rsi = robust_z(_rsi_series(closes))
    parts = [(-z) for z in (z_rev, z_rsi) if z is not None]  # contrarian signs
    if not parts:
        return []
    merged_z = float(np.clip(sum(parts) / len(parts), -WINSOR_Z, WINSOR_Z))
    return [FactorRow(name="reversal", family="reversal",
                      value=round(rev_value, 4) if rev_value is not None else None,
                      z=merged_z, score=squash(merged_z))]


def fundamental_factors(
    price: Optional[float],
    pe_ratio: Optional[float],
    forward_pe: Optional[float],
    analyst_target: Optional[float],
    analyst_count: Optional[int],
    earnings_surprise_pct: Optional[float] = None,
    days_since_earnings: Optional[int] = None,
) -> list[FactorRow]:
    rows: list[FactorRow] = []

    if analyst_target and price and price > 0:
        upside = (analyst_target - price) / price
        shrink = (analyst_count / (analyst_count + ANALYST_COUNT_PRIOR)
                  if analyst_count else ANALYST_DEFAULT_SHRINK)
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

    # PEAD (v2.1 §8): drift continues ~60 days post-announcement, linearly
    # decayed; conservative SUE proxy (surprise% / 5%); absent data ⇒ absent
    # factor — never estimated from nothing.
    if (earnings_surprise_pct is not None and days_since_earnings is not None
            and 0 <= days_since_earnings <= PEAD_HORIZON_DAYS):
        decay = 1.0 - days_since_earnings / PEAD_HORIZON_DAYS
        z = _prior_z(earnings_surprise_pct, 0.0, PEAD_SURPRISE_SIGMA)
        s = squash(z)
        s = float(np.clip((s or 0.0) * decay, -PEAD_MAX_ABS, PEAD_MAX_ABS))
        rows.append(FactorRow(name="pead", family="fundamental",
                              value=round(earnings_surprise_pct, 2), z=z, score=round(s, 4)))
    return rows


def quality_factors(
    gross_profit_over_assets: Optional[float] = None,
    net_issuance_yoy: Optional[float] = None,
    asset_growth_yoy: Optional[float] = None,
) -> list[FactorRow]:
    """Slow sleeve (v2.1 §9-of-plan): GP/A +, issuance −, asset growth −."""
    rows: list[FactorRow] = []
    if gross_profit_over_assets is not None:
        z = _prior_z(gross_profit_over_assets, GPA_CENTER, GPA_SIGMA)
        rows.append(FactorRow(name="gross_profitability", family="quality",
                              value=round(gross_profit_over_assets, 4), z=z, score=squash(z)))
    if net_issuance_yoy is not None:
        z = _prior_z(-net_issuance_yoy, 0.0, ISSUANCE_SIGMA)  # issuance is bearish
        rows.append(FactorRow(name="net_issuance", family="quality",
                              value=round(net_issuance_yoy, 4), z=z, score=squash(z)))
    if asset_growth_yoy is not None:
        z = _prior_z(-(asset_growth_yoy - ASSET_GROWTH_CENTER), 0.0, ASSET_GROWTH_SIGMA)
        rows.append(FactorRow(name="asset_growth", family="quality",
                              value=round(asset_growth_yoy, 4), z=z, score=squash(z)))
    return rows


def news_factor(effective_sentiment: Optional[float], effective_count: float) -> list[FactorRow]:
    """Consumes EFFECTIVE evidence from news_scoring (v2.1 §7):
    shrinkage n_eff/(n_eff + prior) — repeats and stale items can't inflate."""
    if effective_sentiment is None or effective_count <= 0:
        return []
    shrunk = effective_sentiment * effective_count / (effective_count + NEWS_PRIOR_STRENGTH)
    return [FactorRow(name="sentiment", family="news",
                      value=round(effective_sentiment, 4), z=None, score=round(shrunk, 4))]


# ── Regimes & gate ────────────────────────────────────────────────────────────

def detect_regimes(frame: pd.DataFrame, days_to_earnings: Optional[int],
                   today: Optional[date] = None) -> list[str]:
    regimes: list[str] = []
    daily = frame["Close"].pct_change().dropna()
    if len(daily) >= 120:
        rolling_vol = daily.rolling(21).std().dropna()
        if len(rolling_vol) >= 60 and rolling_vol.iloc[-1] >= rolling_vol.quantile(HIGH_VOL_PERCENTILE):
            regimes.append("high_volatility")
    if days_to_earnings is not None and 0 <= days_to_earnings <= EARNINGS_WINDOW_DAYS:
        regimes.append("earnings_window")
    fomc_days = business_days_to_next_fomc(today or date.today())
    if fomc_days is not None and fomc_days <= FOMC_WINDOW_DAYS:
        regimes.append("fomc_window")
    return regimes


def regime_weights(regimes: list[str], active_families: set[str]) -> dict[str, float]:
    weights = dict(BASE_WEIGHTS)
    if "high_volatility" in regimes:
        weights["momentum"] *= HIGH_VOL_MOMENTUM_MULT
        weights["reversal"] = REVERSAL_WEIGHT_HIGH_VOL
    if "earnings_window" in regimes:
        weights["news"] *= EARNINGS_NEWS_MULT
    filtered = {f: w for f, w in weights.items() if f in active_families and w > 0}
    total = sum(filtered.values())
    return {f: w / total for f, w in filtered.items()} if total else {}


def stress_probability(
    term_spread: Optional[float],
    nfci: Optional[float],
    credit_spread_z: Optional[float],
    vix_percentile: Optional[float],
    regimes: list[str],
) -> Optional[float]:
    """Continuous macro stress probability (v2.1 §9). Uses whatever fast
    inputs exist; term spread alone is a valid Estrella–Mishkin reduced model.
    Returns None only when NO input is available."""
    total = GATE_B0
    used = False
    if term_spread is not None:
        total += GATE_B_TERM * (-term_spread)
        used = True
    if nfci is not None:
        total += GATE_B_NFCI * nfci  # NFCI is already standardized by design
        used = True
    if credit_spread_z is not None:
        total += GATE_B_CREDIT * credit_spread_z
        used = True
    if vix_percentile is not None:
        total += GATE_B_VIX * (vix_percentile - 0.5) * 2
        used = True
    if not used:
        return None
    p = 1.0 / (1.0 + math.exp(-total))
    if "fomc_window" in regimes:
        p = min(1.0, p + FOMC_STRESS_BUMP)
    return round(p, 4)


def momentum_gate(p_stress: Optional[float], srm: float) -> float:
    """g = 1 − λ·p, applied to the momentum sleeve only. Falls back to the
    legacy SRM curve when fast inputs are unavailable."""
    if p_stress is not None:
        return round(1.0 - GATE_LAMBDA * p_stress, 4)
    legacy = 1.0 - GATE_LAMBDA * max(0.0, math.tanh((srm - LEGACY_GATE_CENTER) / LEGACY_GATE_SCALE))
    return round(legacy, 4)


def conflict_index(family_scores: dict[str, float], weights: dict[str, float]) -> float:
    names = [n for n, v in family_scores.items() if v is not None]
    numerator = denominator = 0.0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pair = weights.get(a, 0) * weights.get(b, 0)
            denominator += pair
            if family_scores[a] * family_scores[b] < 0:
                numerator += pair * min(abs(family_scores[a]), abs(family_scores[b]))
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


# ── Risk v2 (v2.1 §6) ─────────────────────────────────────────────────────────

def _pct_of_history(series: pd.Series, value: float) -> float:
    clean = series.dropna()
    if len(clean) < 10:
        return 50.0
    return float((clean <= value).mean() * 100)


def risk_score_v2(
    frame: pd.DataFrame,
    beta: Optional[float],
    srm: float,
    p_stress: Optional[float],
    spy_frame: Optional[pd.DataFrame] = None,
    sector_vol_percentile: Optional[float] = None,
    event_window: bool = False,
) -> tuple[int, list[RiskComponent]]:
    closes = frame["Close"]
    daily = closes.pct_change().dropna()
    pct: dict[str, float] = {}

    if len(daily) >= 60:
        # Downside semi-deviation — vectorized (std over negative-masked returns)
        downside = daily.where(daily < 0).rolling(21, min_periods=3).std()
        latest_downside = downside.dropna()
        pct["downside_dev"] = (_pct_of_history(latest_downside, float(latest_downside.iloc[-1]))
                               if len(latest_downside) else 50.0)
        # Tail: rolling 5% quantile (VaR95) — vectorized; percentile vs history
        var_roll = (-daily).rolling(250, min_periods=120).quantile(0.95).dropna()
        pct["tail_risk"] = _pct_of_history(var_roll, float(var_roll.iloc[-1])) if len(var_roll) else 50.0
        peak = closes.cummax()
        drawdowns = ((closes - peak) / peak).abs()
        pct["drawdown"] = _pct_of_history(drawdowns, float(drawdowns.iloc[-1]))
        vol_roll = daily.rolling(21).std().dropna()
        vol_pct = _pct_of_history(vol_roll, float(vol_roll.iloc[-1]))
        # vol-of-vol: rising short vol adds up to +10 within the component
        if len(vol_roll) >= 10:
            rising = float(vol_roll.iloc[-1] > vol_roll.iloc[-10])
            vol_pct = min(100.0, vol_pct + 10.0 * rising)
        pct["vol_regime"] = vol_pct
    else:
        pct.update({"downside_dev": 50.0, "tail_risk": 50.0, "drawdown": 50.0, "vol_regime": 50.0})

    # Beta level + stability; idiosyncratic share — need SPY alignment
    if spy_frame is not None and len(spy_frame) >= 140 and len(daily) >= 140:
        spy_daily = spy_frame["Close"].pct_change().reindex(daily.index).dropna()
        joined = pd.concat([daily, spy_daily], axis=1, keys=["s", "m"]).dropna()
        if len(joined) >= 126:
            window = joined.tail(126)
            var_m = float(window["m"].var())
            realized_beta = float(window.cov().loc["s", "m"] / var_m) if var_m > 0 else 1.0
            rolling_beta = joined["s"].rolling(63).cov(joined["m"]) / joined["m"].rolling(63).var()
            beta_instability = float(rolling_beta.dropna().tail(126).std() or 0.0)
            level = beta if beta is not None else realized_beta
            pct["beta"] = float(np.clip((abs(level) - 0.8) * 60 + beta_instability * 100, 0, 100))
            corr = float(window["s"].corr(window["m"]))
            pct["idiosyncratic"] = float(np.clip((1 - corr ** 2) * 100, 0, 100))
        else:
            pct["beta"] = float(np.clip(((abs(beta) if beta is not None else 1.0) - 0.8) * 60, 0, 100))
            pct["idiosyncratic"] = 50.0
    else:
        pct["beta"] = float(np.clip(((abs(beta) if beta is not None else 1.0) - 0.8) * 60, 0, 100))
        pct["idiosyncratic"] = 50.0

    # Amihud illiquidity: |r| / dollar volume, percentile vs own history
    if "Volume" in frame.columns and frame["Volume"].fillna(0).sum() > 0 and len(daily) >= 60:
        dollar_volume = (frame["Close"] * frame["Volume"].astype(float)).replace(0, np.nan)
        amihud = (daily.abs() / dollar_volume.reindex(daily.index)).dropna()
        rolling_amihud = amihud.rolling(21).mean().dropna()
        pct["liquidity"] = _pct_of_history(rolling_amihud, float(rolling_amihud.iloc[-1])) if len(rolling_amihud) else 50.0
    else:
        pct["liquidity"] = 50.0

    pct["macro"] = float(np.clip((p_stress if p_stress is not None
                                  else (srm - 0.5) / 1.1) * 100, 0, 100))
    pct["sector"] = sector_vol_percentile if sector_vol_percentile is not None else 50.0

    components = [
        RiskComponent(name=name, percentile=round(pct[name], 1), weight=weight,
                      contribution=round(weight * pct[name], 2))
        for name, weight in RISK_WEIGHTS.items()
    ]
    total = sum(component.contribution for component in components)
    if event_window:
        total = min(100.0, total + 5.0)  # event floor, documented (§6)
        components.append(RiskComponent(name="event_floor", percentile=100.0,
                                        weight=0.05, contribution=5.0))
    return int(round(total)), components


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
    headline_count: float = 0,
    spy_frame: Optional[pd.DataFrame] = None,
    days_to_earnings: Optional[int] = None,
    data_confidence: float = 1.0,
    today: Optional[date] = None,
    # v2.1 inputs — all optional; absence degrades gracefully
    gross_profit_over_assets: Optional[float] = None,
    net_issuance_yoy: Optional[float] = None,
    asset_growth_yoy: Optional[float] = None,
    earnings_surprise_pct: Optional[float] = None,
    days_since_earnings: Optional[int] = None,
    nfci: Optional[float] = None,
    credit_spread_z: Optional[float] = None,
    vix_percentile: Optional[float] = None,
    term_spread: Optional[float] = None,
    price_age_days: Optional[float] = None,
    news_age_hours: Optional[float] = None,
    model_rolling_ic: Optional[float] = None,
    recent_verdict_flips: Optional[int] = None,
    sector_vol_percentile: Optional[float] = None,
) -> Optional[ScoreCard]:
    if frame is None or len(frame) < MIN_BARS:
        return None

    regimes = detect_regimes(frame, days_to_earnings, today)

    rows = momentum_factors(frame, spy_frame)
    rows += reversal_factor(frame)
    fundamental_rows = fundamental_factors(
        price, pe_ratio, forward_pe, analyst_target, analyst_count,
        earnings_surprise_pct, days_since_earnings,
    )
    if "earnings_window" in regimes:
        for row in fundamental_rows:
            if row.name == "target_upside" and row.score is not None:
                row.score = round(row.score * EARNINGS_TARGET_MULT, 4)
    rows += fundamental_rows
    rows += quality_factors(gross_profit_over_assets, net_issuance_yoy, asset_growth_yoy)
    rows += news_factor(sentiment_avg, float(headline_count))

    family_members: dict[str, list[FactorRow]] = {}
    for row in rows:
        if row.score is not None:
            family_members.setdefault(row.family, []).append(row)
    if not family_members:
        return None

    weights = regime_weights(regimes, set(family_members.keys()))
    if not weights:
        return None

    p_stress = stress_probability(term_spread, nfci, credit_spread_z, vix_percentile, regimes)
    gate = momentum_gate(p_stress, srm)

    family_scores: dict[str, Optional[float]] = {}
    for family, members in family_members.items():
        if family == "momentum":
            member_weights = [MOMENTUM_MEMBER_WEIGHTS.get(m.name, 1.0) for m in members]
        else:
            member_weights = [1.0] * len(members)
        total_weight = sum(member_weights)
        raw_family = sum(w * m.score for w, m in zip(member_weights, members)) / total_weight

        # Gate applies to the momentum sleeve only, bullish side only (§9)
        gated_family = raw_family
        if family == "momentum" and raw_family > 0:
            gated_family = raw_family * gate

        family_scores[family] = raw_family
        effective = gated_family
        for w, m in zip(member_weights, members):
            share = w / total_weight
            m.contribution = round(weights[family] * effective * share
                                   if abs(raw_family) < 1e-12 else
                                   weights[family] * (m.score * w / total_weight)
                                   * (gated_family / raw_family if raw_family else 1.0), 4)

    ungated = sum(weights[f] * family_scores[f] for f in weights)
    gated_total = sum(
        weights[f] * (family_scores[f] * (gate if f == "momentum" and family_scores[f] > 0 else 1.0))
        for f in weights
    )

    conflict = conflict_index({f: family_scores[f] for f in weights}, weights)

    # ── Uncertainty & confidence (v2 §5 + v2.1 terms) ────────────────────────
    weighted_var = sum(weights[f] * (family_scores[f] - ungated) ** 2 for f in weights)
    u_disp = min(1.0, math.sqrt(weighted_var))
    total_possible = len(rows)
    computable = sum(1 for r in rows if r.score is not None)
    u_data = 1.0 - (computable / max(total_possible, 1)) * max(0.0, min(1.0, data_confidence))

    u_event = 0.0
    if "earnings_window" in regimes:
        u_event = 1.0 - (1.0 - u_event) * (1.0 - EVENT_U_EARNINGS)
    if "fomc_window" in regimes:
        u_event = 1.0 - (1.0 - u_event) * (1.0 - EVENT_U_FOMC)

    u_fresh = 0.0
    if price_age_days is not None:
        u_fresh = max(u_fresh, min(1.0, max(0.0, price_age_days - 1) / FRESH_TAU_PRICE_DAYS) * 0.5)
    if news_age_hours is not None and family_scores.get("news") is not None:
        u_fresh = max(u_fresh, min(1.0, news_age_hours / (FRESH_TAU_NEWS_HOURS * 3)) * 0.3)

    if model_rolling_ic is None:
        u_model = U_MODEL_MAX * 0.5  # unmeasured: honest partial doubt
        model_note = "unmeasured"
    else:
        u_model = U_MODEL_MAX * (1.0 - min(1.0, max(0.0, model_rolling_ic) / MODEL_IC_REF))
        model_note = f"rolling IC {model_rolling_ic:+.3f}"

    u_stab = min(U_STAB_MAX, U_STAB_PER_FLIP * (recent_verdict_flips or 0))

    u_macro = 0.0
    if p_stress is not None:
        u_macro = U_MACRO_MAX * (4.0 * p_stress * (1.0 - p_stress))  # peak ambiguity at p=.5

    uncertainty = 1.0 - np.prod([1.0 - u for u in
                                 (u_disp, u_data, u_event, u_fresh, u_model, u_stab, u_macro)])

    losses: list[ConfidenceLoss] = []
    confidence = 100.0
    for label, factor in (
        ("Family dispersion", 1.0 - u_disp),
        ("Data completeness", 1.0 - u_data),
        ("Event proximity", 1.0 - u_event),
        ("Data freshness", 1.0 - u_fresh),
        (f"Model reliability ({model_note})", 1.0 - u_model),
        ("Prediction stability", 1.0 - u_stab),
        ("Macro uncertainty", 1.0 - u_macro),
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

    risk, risk_components = risk_score_v2(
        frame, beta, srm, p_stress, spy_frame, sector_vol_percentile,
        event_window=("earnings_window" in regimes or "fomc_window" in regimes),
    )

    def fam(name: str) -> Optional[float]:
        value = family_scores.get(name)
        return None if value is None else round(value, 4)

    return ScoreCard(
        raw_score=round(gated_total, 4),
        ungated_score=round(ungated, 4),
        verdict=map_verdict(gated_total).value,
        raw_verdict=map_verdict(ungated).value,
        confidence=int(round(confidence)),
        confidence_losses=losses,
        uncertainty=round(float(uncertainty), 4),
        uncertainty_components={
            "dispersion": round(u_disp, 4), "data": round(u_data, 4),
            "event": round(u_event, 4), "freshness": round(u_fresh, 4),
            "model": round(u_model, 4), "stability": round(u_stab, 4),
            "macro": round(u_macro, 4),
        },
        conflict_index=round(conflict, 4),
        momentum_score=fam("momentum"),
        fundamental_score=fam("fundamental"),
        quality_score=fam("quality"),
        news_score=fam("news"),
        reversal_score=fam("reversal"),
        macro_gate=gate,
        stress_probability=p_stress,
        risk_score=risk,
        risk_components=risk_components,
        weights_used={f: round(w, 4) for f, w in weights.items()},
        regimes=regimes,
        factors=rows,
        data_completeness=round(computable / max(total_possible, 1), 4),
    )
