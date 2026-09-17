"""Contracts for the illustrative portfolio surface.

The book is built from cross-sectional ranks.  Those ranks can size and order
positions, but they are not returns and cannot be mixed with dollar execution
costs to manufacture a P&L waterfall.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from src.services import quant_portfolio_service as service


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(17)
    symbols = [f"S{i:03d}" for i in range(120)]
    # More observations than names keeps the synthetic covariance full-rank;
    # the contract under test is portfolio semantics, not singular-matrix
    # degradation (covered separately).
    dates = pd.date_range("2020-01-03", periods=180, freq="W-FRI")
    scales = np.linspace(0.25, 3.0, len(symbols))
    panel = pd.DataFrame(
        rng.normal(size=(len(dates), len(symbols))) * scales,
        index=dates,
        columns=symbols,
    )
    latest = pd.DataFrame(
        {
            "date": dates[-1],
            "symbol": symbols,
            "model": "gradient_boosting",
            "prediction": np.linspace(-1.0, 1.0, len(symbols)),
            "fwd_rank_21": np.linspace(-1.0, 1.0, len(symbols)),
        }
    )
    return latest, panel


def test_post_tilt_book_is_rechecked_against_its_reported_constraints():
    predictions, panel = _inputs()
    with patch.object(service, "_predictions", return_value=predictions), patch.object(
        service, "_panel", return_value=panel
    ):
        book = service.build(method="inverse_volatility", max_weight=0.03)

    weights = pd.Series({row["symbol"]: row["weight"] for row in book["weights"]})
    assert book["status"] == "ok"
    assert book["allocation"]["feasible"] is True
    assert float(weights.abs().sum()) <= 1.0 + 1e-6
    assert abs(float(weights.sum())) <= 1e-6
    assert float(weights.abs().max()) <= 0.03 + 1e-6


def test_rank_book_refuses_a_dimensionally_invalid_return_waterfall():
    predictions, panel = _inputs()
    with patch.object(service, "_predictions", return_value=predictions), patch.object(
        service, "_panel", return_value=panel
    ):
        book = service.build(method="equal_weight")

    assert book["cost"]["waterfall"]["status"] == "unavailable"
    assert "rank outcomes" in book["cost"]["waterfall"]["reason"]
    assert book["cost"]["breakdown_units"]["total"] == "USD"
    assert book["cost"]["assumptions"]["half_spread_bps"] == 10.0
    assert "not subtracted from ranks" in book["units"]
