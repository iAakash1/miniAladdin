"""A price that did not move is a measurement, not a missing value.

Two defects share one input: a security whose price is flat over some window.
Halts, illiquid names and pegged instruments all produce one.

**A measured zero was reported as unavailable.** `return_5d`, `return_21d` and
`volatility` were serialised with a truthiness guard — `round(x, 4) if x else
None` — so a five-session return of exactly 0.0 left the API as `null`. The
frontend renders `null` as "unavailable", so the reader was told the return
could not be measured when it had been measured and was zero. The same dict
already states the rule three lines further down, on `macd_histogram`: "`is
not None`, not truthiness. A MACD histogram of exactly 0.0 is the crossover
itself." The rule was written; three financial fields did not follow it.

**An undefined RSI discarded every other metric.** With neither gains nor
losses in its window, `rs = gain / loss` is 0/0 and RSI is NaN. NaN is not a
number the model will accept — `rsi_14` is bounded `ge=0, le=100` — so
constructing `TechnicalAnalysis` raised, the whole technical future failed,
and the route answered with "Technical analysis failed — check that the ticker
symbol is valid". The ticker was fine. Volatility, Sharpe, drawdown, momentum
and both returns had all computed correctly and were thrown away with it, and
the reader was handed a false explanation.

RSI is undefined there, not neutral. It is not 50 and it is not 100: it is
unmeasurable, and the honest answer is the one this codebase gives everywhere
else — `None`.
"""

import math

import pandas as pd
import pytest

from src.prediction_agent import RiskAwarePredictionAgent



def _frame(closes):
    idx = pd.bdate_range("2026-01-01", periods=len(closes))
    return pd.DataFrame(
        {"Close": list(closes), "Volume": [1_000_000] * len(closes)}, index=idx
    )


def _agent(closes):
    return RiskAwarePredictionAgent("FLAT", period="3mo", price_data=_frame(closes))


# ── the measured zero ────────────────────────────────────────────────────────

def test_a_flat_window_measures_a_zero_return_not_a_missing_one():
    agent = _agent([100.0] * 40)
    returns = agent._compute_returns()
    assert returns["return_5d"] == 0.0
    assert returns["return_21d"] == 0.0
    assert agent._compute_volatility() == 0.0


@pytest.mark.parametrize("field", ["return_5d", "return_21d", "volatility"])
def test_a_measured_zero_survives_serialisation(field):
    """The route's own expression, applied to a measured zero.

    Truthiness turns 0.0 into None here; `is not None` keeps it. This asserts
    the surviving value rather than the syntax, so it holds however the line
    is written.
    """
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    import api.index as api
    from src.providers.schemas import OHLCVBar, PriceSeries, ProviderResult

    # Real movement inside the RSI window, then a flat final week: the
    # technical block is produced normally and return_5d is exactly 0.0.
    closes = [100.0 + (i % 7) * 0.9 + i * 0.1 for i in range(215)] + [149.0] * 5
    dates = pd.bdate_range("2025-01-01", periods=len(closes)).strftime("%Y-%m-%d")
    bars = [
        OHLCVBar(date=d, open=c, high=c, low=c, close=c, volume=1_000_000)
        for d, c in zip(dates, closes)
    ]
    series = ProviderResult(
        data=PriceSeries(symbol="FLATWK", bars=bars), source="fixture", confidence=0.85
    )

    with patch.object(api.providers.market_data, "get_series", return_value=series):
        with TestClient(api.app) as client:
            response = client.get("/api/research/FLATWK?fast=true")

    assert response.status_code == 200, response.text
    technicals = response.json()["technicals"]
    assert "error" not in technicals, technicals

    value = technicals[field]
    assert value is not None, (
        f"{field} was measured but serialised as null — a reader sees "
        f"'unavailable' for a value the engine computed"
    )
    assert math.isfinite(value)


# ── the undefined RSI ────────────────────────────────────────────────────────

def test_rsi_is_unavailable_when_its_window_has_neither_gains_nor_losses():
    """0/0 is undefined. Not 50, not 100, not NaN."""
    assert _agent([100.0] * 40)._compute_rsi() is None


def test_rsi_is_unavailable_for_a_name_halted_after_trading_normally():
    """The realistic shape: 26 normal sessions, then 20 unchanged."""
    closes = [100.0 + i * 0.7 for i in range(26)] + [118.0] * 20
    assert _agent(closes)._compute_rsi() is None


def test_rsi_is_100_when_the_window_has_only_gains():
    """The guard must not have swallowed the defined limiting case.

    All gains and no losses is `rs = inf`, which resolves to exactly 100 —
    a real RSI reading, and it must survive.
    """
    rsi = _agent([100.0 + i for i in range(40)])._compute_rsi()
    assert rsi == 100.0


def test_rsi_is_still_computed_for_an_ordinary_series():
    closes = [100.0 + (i % 5) * 2.0 - (i % 3) for i in range(40)]
    rsi = _agent(closes)._compute_rsi()
    assert rsi is not None and 0.0 <= rsi <= 100.0


def test_a_halted_name_keeps_the_metrics_that_are_defined():
    """The whole point: one undefined metric must not delete the rest.

    Every one of these is computable for a halted series, and all of them
    were being discarded because RSI alone was NaN.
    """
    closes = [100.0 + i * 0.7 for i in range(26)] + [118.0] * 20
    agent = _agent(closes)
    analysis = agent.predict(risk_multiplier=1.0)

    assert analysis.rsi_14 is None
    assert analysis.volatility is not None and math.isfinite(analysis.volatility)
    assert analysis.return_21d is not None
    assert analysis.max_drawdown is not None


def test_a_series_that_never_fell_reports_zero_drawdown_not_unavailable():
    """`predict()` carried the same truthiness guard on max_drawdown.

    A price that never closed below its running peak has a maximum drawdown
    of exactly 0.0. That is among the most informative readings the field can
    take — it says the window contains no decline at all — and it was being
    reported as "not computed".
    """
    analysis = _agent([100.0 + i for i in range(40)]).predict(risk_multiplier=1.0)
    assert analysis.max_drawdown == 0.0


def test_a_real_drawdown_is_still_reported():
    """The guard must not have flattened genuine declines to zero."""
    closes = [100.0 + i for i in range(20)] + [119.0 - i * 2 for i in range(20)]
    analysis = _agent(closes).predict(risk_multiplier=1.0)
    assert analysis.max_drawdown is not None
    assert analysis.max_drawdown < 0.0
