"""Tests for the v2 quantitative scoring engine (docs/SCORING.md)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.scoring import engine


def make_frame(days: int = 300, drift: float = 0.0, vol: float = 0.01,
               seed: int = 7, spike_last: float | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, days)
    if spike_last is not None:
        returns[-1] = spike_last
    closes = 100 * np.cumprod(1 + returns)
    index = pd.bdate_range(end=date(2026, 7, 1), periods=days)
    return pd.DataFrame({
        "Open": closes, "High": closes * 1.01, "Low": closes * 0.99,
        "Close": closes, "Volume": rng.integers(1_000_000, 2_000_000, days),
    }, index=index)


AWAY_FROM_FOMC = date(2026, 6, 1)  # > 3 business days from any 2026 decision


def score(frame, **kwargs):
    defaults = dict(srm=1.0, price=float(frame["Close"].iloc[-1]), today=AWAY_FROM_FOMC)
    defaults.update(kwargs)
    return engine.score_ticker(frame, **defaults)


class TestNormalization:
    def test_robust_z_ignores_history_outliers(self):
        clean = pd.Series(np.random.default_rng(1).normal(0, 1, 250))
        polluted = clean.copy()
        polluted.iloc[10] = 500.0  # absurd outlier in history
        z_clean = engine.robust_z(clean)
        z_polluted = engine.robust_z(polluted)
        assert abs(z_clean - z_polluted) < 0.15  # MAD barely moves

    def test_winsorization_caps_extreme_readings(self):
        history = pd.Series(list(np.random.default_rng(2).normal(0, 1, 250)) + [1000.0])
        assert engine.robust_z(history) == pytest.approx(engine.WINSOR_Z)

    def test_squash_bounds(self):
        assert engine.squash(engine.WINSOR_Z) < 1.0
        assert engine.squash(-engine.WINSOR_Z) > -1.0
        assert engine.squash(0.0) == 0.0


class TestComposite:
    def test_uptrend_scores_bullish(self):
        card = score(make_frame(drift=0.004, vol=0.008))
        assert card is not None
        assert card.momentum_score > 0
        assert card.raw_score > 0

    def test_downtrend_scores_bearish(self):
        card = score(make_frame(drift=-0.004, vol=0.008))
        assert card.momentum_score < 0
        assert card.raw_score < 0

    def test_contributions_sum_to_ungated_score(self):
        card = score(
            make_frame(drift=0.002),
            pe_ratio=25.0, forward_pe=20.0, analyst_target=None,
            sentiment_avg=0.4, headline_count=8,
        )
        total = sum(row.contribution for row in card.factors)
        assert total == pytest.approx(card.ungated_score, abs=0.02)

    def test_insufficient_history_returns_none(self):
        assert score(make_frame(days=40)) is None


class TestMacroGate:
    def test_gate_dampens_bullish_only(self):
        frame = make_frame(drift=0.004, vol=0.008)
        calm = score(frame, srm=1.0)
        stressed = score(frame, srm=1.5)
        assert stressed.raw_score < calm.raw_score  # bullish gated down
        assert stressed.macro_gate < 1.0

        down = make_frame(drift=-0.004, vol=0.008)
        calm_bear = score(down, srm=1.0)
        stressed_bear = score(down, srm=1.5)
        # bearish signal is NOT dampened by the gate
        assert stressed_bear.ungated_score == pytest.approx(calm_bear.ungated_score)
        assert stressed_bear.raw_score == pytest.approx(stressed_bear.ungated_score)

    def test_gate_bounds_and_probabilistic_path(self):
        # Legacy SRM fallback (no fast inputs)
        assert engine.momentum_gate(None, 0.5) == pytest.approx(1.0)
        worst_legacy = engine.momentum_gate(None, 1.6)
        assert 1.0 - engine.GATE_LAMBDA <= worst_legacy < 1.0
        # Probabilistic path: stress p directly controls the gate
        assert engine.momentum_gate(0.0, 1.6) == pytest.approx(1.0)
        assert engine.momentum_gate(1.0, 0.5) == pytest.approx(1.0 - engine.GATE_LAMBDA)

    def test_stress_probability_monotonicity(self):
        calm = engine.stress_probability(term_spread=1.5, nfci=-0.5,
                                         credit_spread_z=-0.5, vix_percentile=0.2, regimes=[])
        stressed = engine.stress_probability(term_spread=-0.5, nfci=1.0,
                                             credit_spread_z=1.5, vix_percentile=0.95, regimes=[])
        assert calm is not None and stressed is not None
        assert calm < 0.2 < stressed
        assert engine.stress_probability(None, None, None, None, []) is None
        # Term spread alone is a valid reduced model (Estrella–Mishkin)
        term_only = engine.stress_probability(term_spread=-1.0, nfci=None,
                                              credit_spread_z=None, vix_percentile=None, regimes=[])
        assert term_only is not None and term_only > 0.2


class TestRegimes:
    def test_high_volatility_detected_and_reweighted(self):
        rng = np.random.default_rng(3)
        calm_part = rng.normal(0.001, 0.005, 260)
        wild_part = rng.normal(0.0, 0.05, 25)  # recent chaos
        returns = np.concatenate([calm_part, wild_part])
        closes = 100 * np.cumprod(1 + returns)
        frame = pd.DataFrame({
            "Open": closes, "High": closes, "Low": closes, "Close": closes,
            "Volume": np.full(len(closes), 1_000_000),
        }, index=pd.bdate_range(end=date(2026, 7, 1), periods=len(closes)))

        # Two active families so renormalized weights are comparable.
        card = score(frame, sentiment_avg=0.3, headline_count=10)
        calm_card = score(make_frame(), sentiment_avg=0.3, headline_count=10)
        assert "high_volatility" in card.regimes
        assert "high_volatility" not in calm_card.regimes
        assert card.weights_used["momentum"] < calm_card.weights_used["momentum"]

    def test_earnings_window_flags_and_raises_uncertainty(self):
        frame = make_frame()
        normal = score(frame)
        earnings = score(frame, days_to_earnings=2)
        assert "earnings_window" in earnings.regimes
        assert earnings.uncertainty > normal.uncertainty
        assert earnings.confidence < normal.confidence

    def test_fomc_window_lowers_confidence(self):
        frame = make_frame()
        normal = score(frame, today=AWAY_FROM_FOMC)
        fomc = score(frame, today=date(2026, 7, 28))  # decision 2026-07-29
        assert "fomc_window" in fomc.regimes
        assert fomc.confidence < normal.confidence


class TestConflictAndConfidence:
    def test_conflicting_families_raise_conflict_index(self):
        frame = make_frame(drift=0.004, vol=0.008)  # bullish momentum
        agreeing = score(frame, sentiment_avg=0.5, headline_count=10)
        conflicted = score(frame, sentiment_avg=-0.8, headline_count=10)
        assert conflicted.conflict_index > agreeing.conflict_index
        assert conflicted.confidence < agreeing.confidence

    def test_confidence_losses_sum_exactly(self):
        card = score(make_frame(), sentiment_avg=-0.6, headline_count=10,
                     pe_ratio=30.0, days_to_earnings=1)
        assert sum(loss.points for loss in card.confidence_losses) == pytest.approx(
            100 - card.confidence, abs=1
        )

    def test_confidence_bounds_respected(self):
        card = score(make_frame(), sentiment_avg=-0.9, headline_count=12,
                     days_to_earnings=0, data_confidence=0.3)
        assert engine.CONFIDENCE_FLOOR <= card.confidence <= engine.CONFIDENCE_CAP


class TestNewsShrinkage:
    def test_few_headlines_shrink_toward_zero(self):
        frame = make_frame()
        few = score(frame, sentiment_avg=0.9, headline_count=2)
        many = score(frame, sentiment_avg=0.9, headline_count=12)
        assert abs(few.news_score) < abs(many.news_score)
        assert abs(many.news_score) < 0.9  # even max evidence can't claim face value


class TestRiskScore:
    def test_risk_score_monotone_in_srm(self):
        frame = make_frame()
        low = score(frame, srm=0.8)
        high = score(frame, srm=1.5)
        assert high.risk_score > low.risk_score

    def test_risk_components_present_and_bounded(self):
        card = score(make_frame(), beta=2.0)
        names = {component.name for component in card.risk_components}
        assert {"downside_dev", "tail_risk", "drawdown", "vol_regime", "beta",
                "idiosyncratic", "liquidity", "macro", "sector"} <= names
        assert 0 <= card.risk_score <= 100
        # Contributions are exact: weight × percentile, summing to the score
        total = sum(component.contribution for component in card.risk_components)
        assert card.risk_score == pytest.approx(total, abs=1)


class TestVerdictMapping:
    @pytest.mark.parametrize("value,expected", [
        (0.5, "Strong Buy"), (0.2, "Buy"), (0.0, "Hold"),
        (-0.2, "Sell"), (-0.5, "Strong Sell"),
        (0.1499, "Hold"), (-0.1499, "Hold"),
    ])
    def test_cut_points(self, value, expected):
        assert engine.map_verdict(value).value == expected
