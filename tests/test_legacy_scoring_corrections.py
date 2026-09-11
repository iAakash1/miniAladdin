"""Corrections to the legacy technical agent's scoring and its documentation.

Three findings, all in `RiskAwarePredictionAgent`, all the kind that survive
because nothing downstream crashes when they are wrong.

**An unreachable branch.** The analyst-target layer tested `upside < -0.10`
before `upside < -0.20`. Anything 20% below the target is also 10% below it,
so the first branch caught every case and the -2 penalty never once executed.
A stock the street thought was 40% overvalued scored exactly the same as one
it thought was 11% overvalued.

**A docstring that described a different function.** It claimed a maximum of
±10 mapping to Strong Buy at ±4. The five layers sum to ±9 (RSI 2, Sharpe 2,
21-day return 2, MACD 1, analyst target 2) and the verdict cutoffs are ±5 and
±2. Both numbers were wrong, which matters because this is the docstring
someone reads when asked how the score is derived.

**Two ratios on two different time scales.** Sharpe was annualised —
`mean * 252 / (std * sqrt(252))` — and Sortino was not: a bare
`mean / downside_std`. They are rendered beside each other under similar
names, so a reader comparing them was comparing a yearly figure against a
daily one, and Sortino looked roughly sixteen times smaller than it should.
"""

import numpy as np
import pandas as pd
import pytest

from src.models import SignalVerdict
from src.prediction_agent import RiskAwarePredictionAgent as Agent


class _Fundamentals:
    """Minimal stand-in for the analyst-target layer's input."""

    def __init__(self, analyst_target):
        self.error = None
        self.analyst_target = analyst_target


def _score_for_upside(upside: float) -> SignalVerdict:
    """Run only the analyst-target layer by neutralising every other input."""
    price = 100.0
    # `_raw_signal` never touches `self`; passing None keeps the layer under
    # test isolated from constructing an agent with a price frame.
    return Agent._raw_signal(
        None,
        rsi=None,
        sharpe=None,
        return_21d=None,
        macd=None,
        fundamentals=_Fundamentals(price * (1.0 + upside)),
        current_price=price,
    )


# ── the unreachable branch ───────────────────────────────────────────────────

def test_a_severely_overvalued_name_is_penalised_more_than_a_mildly_one():
    """-25% upside must outscore -15% downward. It did not: both were -1."""
    mild = _score_for_upside(-0.15)
    severe = _score_for_upside(-0.25)

    assert mild is SignalVerdict.HOLD, mild
    # -2 crosses the SELL cutoff; -1 does not. If the -2 branch is unreachable
    # both land on HOLD and this fails.
    assert severe is SignalVerdict.SELL, (
        "a 25% overvaluation scored the same as a 15% one — the -0.20 branch "
        "is unreachable because -0.10 is tested first"
    )


def test_the_positive_side_still_distinguishes_its_two_tiers():
    """The bug was ordering, not thresholds — the mirror side must be intact."""
    assert _score_for_upside(0.15) is SignalVerdict.HOLD
    assert _score_for_upside(0.25) is SignalVerdict.BUY


@pytest.mark.parametrize("upside", [-0.21, -0.30, -0.50, -0.95])
def test_every_severe_overvaluation_reaches_the_stronger_penalty(upside):
    assert _score_for_upside(upside) is SignalVerdict.SELL


# ── the documented range ─────────────────────────────────────────────────────

def _frame(closes):
    idx = pd.bdate_range("2026-01-01", periods=len(closes))
    return pd.DataFrame({"Close": list(closes), "Volume": [1_000_000] * len(closes)}, index=idx)


def test_the_scoring_layers_sum_to_the_documented_maximum():
    """±9, not ±10 — and the docstring must say so.

    Asserted against the docstring itself because the defect was that the
    prose and the arithmetic disagreed, and only the prose is ever read.
    """
    doc = Agent._raw_signal.__doc__ or ""
    assert "±10" not in doc, "the docstring still claims a maximum of ±10"
    assert "±9" in doc, "the docstring should state the real ±9 maximum"


def test_the_documented_cutoffs_match_the_code():
    """The code maps Strong Buy at ±5 and Buy/Sell at ±2, not ±4."""
    doc = Agent._raw_signal.__doc__ or ""
    assert "±4" not in doc, "the docstring still claims a ±4 Strong Buy cutoff"
    assert "±5" in doc and "±2" in doc


# ── consistent annualisation ─────────────────────────────────────────────────

def _agent(closes):
    return Agent("T", period="3mo", price_data=_frame(closes))


def test_sharpe_and_sortino_share_a_time_scale():
    """Both annualised, so the two numbers beside each other are comparable.

    A series with downside dispersion close to its total dispersion makes the
    two ratios land within the same order of magnitude. Before the fix Sortino
    was smaller by roughly sqrt(252) — about sixteen times — purely because of
    the missing annualisation, not because of anything in the prices.
    """
    rng = np.random.default_rng(20260911)
    closes = [100.0]
    for step in rng.normal(0.0008, 0.012, 250):
        closes.append(closes[-1] * (1.0 + step))

    agent = _agent(closes)
    sharpe, sortino = agent._compute_sharpe(), agent._compute_sortino()
    assert sharpe is not None and sortino is not None

    # Sortino uses only downside dispersion, so it is normally the larger of
    # the two; what must not happen is an order-of-magnitude gap created by
    # one being annualised and the other not.
    assert 0.2 < abs(sortino) / abs(sharpe) < 6.0, (
        f"sharpe={sharpe} sortino={sortino} — these are not on the same scale"
    )


def test_sortino_keeps_its_sign():
    """Annualisation scales; it must not flip a losing series positive."""
    # A losing series needs *varying* declines: a constant -0.3% every day has
    # zero downside dispersion, which the epsilon guard correctly refuses.
    rng = np.random.default_rng(11)
    closes = [100.0]
    for step in rng.normal(-0.004, 0.010, 200):
        closes.append(closes[-1] * (1.0 + step))
    sortino = _agent(closes)._compute_sortino()
    assert sortino is not None and sortino < 0


def test_sortino_is_still_unavailable_without_enough_downside():
    """A monotonically rising series has fewer than two down days."""
    assert _agent([100.0 + i for i in range(60)])._compute_sortino() is None


# ── RSI formulation disclosure ───────────────────────────────────────────────

def test_the_rsi_formulation_is_disclosed():
    """The implementation is a simple moving average, not Wilder smoothing.

    Both are called "RSI-14" in the wild and they return different numbers,
    so a reader comparing this figure against a charting platform needs to
    know which one this is.
    """
    doc = Agent._compute_rsi.__doc__ or ""
    lowered = doc.lower()
    assert "wilder" in lowered, "the RSI docstring should name the convention it is not"
    assert "simple moving average" in lowered or "sma" in lowered
