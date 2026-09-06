"""Boundaries that turned a failure or an absence into a measurement.

Four separate places, one shape of defect: an unusable input produced a
confident number instead of an admission.
"""

import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.providers.vendors.market_vendors import _safe_float
from src.quant.risk.engine import risk_contributions
from src.services import clerk_auth


# ── non-finite numbers at the vendor boundary ───────────────────────────────

@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan"),
                                 "Infinity", "-Infinity", "NaN"])
def test_a_non_finite_vendor_number_is_rejected(bad):
    """`x == x` catches NaN and lets infinity straight through."""
    assert _safe_float(bad) is None, f"{bad!r} was accepted as a price"


@pytest.mark.parametrize("good,expected", [
    (0, 0.0), (0.0, 0.0), (-12.5, -12.5), ("3.25", 3.25), (1e9, 1e9),
])
def test_real_numbers_still_pass(good, expected):
    """Including zero — a zero volume is a measurement."""
    assert _safe_float(good) == expected


def test_junk_is_still_rejected():
    for junk in (None, "", "n/a", object()):
        assert _safe_float(junk) is None


# ── non-finite numbers at the order boundary ────────────────────────────────

def _order(**kw):
    body = {"symbol": "AAPL", "qty": 1.0, "side": "buy",
            "order_type": "market", "time_in_force": "day"}
    body.update(kw)
    return api.PaperOrderRequest(**body)


@pytest.mark.parametrize("qty", [float("inf"), float("-inf"), float("nan")])
def test_a_non_finite_quantity_is_refused(qty):
    """`qty <= 0` is False for infinity, so it reached the broker."""
    problems = api._validate_paper_order(_order(qty=qty))
    assert problems, f"an order for {qty} shares passed validation"
    assert any("not a number" in p for p in problems)


def test_a_zero_or_negative_quantity_is_still_refused():
    assert api._validate_paper_order(_order(qty=0))
    assert api._validate_paper_order(_order(qty=-5))


def test_a_normal_quantity_passes():
    assert api._validate_paper_order(_order(qty=10)) == []


@pytest.mark.parametrize("price", [float("inf"), float("nan")])
def test_a_non_finite_limit_price_is_refused(price):
    problems = api._validate_paper_order(_order(order_type="limit", limit_price=price))
    assert any("not a number" in p for p in problems), problems


def test_a_zero_limit_price_is_refused_as_a_price_not_as_absence():
    """It used to be caught by truthiness, which conflates 0 with missing."""
    problems = api._validate_paper_order(_order(order_type="limit", limit_price=0))
    assert any("greater than zero" in p for p in problems), problems


def test_a_limit_order_with_no_price_says_the_price_is_missing():
    problems = api._validate_paper_order(_order(order_type="limit", limit_price=None))
    assert any("needs a limit price" in p for p in problems), problems


# ── a failed risk computation is not zero risk ──────────────────────────────

def _overflowing_book():
    """A finite, positive semi-definite covariance whose marginal overflows.

    An infinite covariance is rejected earlier by the PSD guard — a different
    control, also correct — so it cannot reach this branch. Driving the real
    one needs a matrix that passes every earlier check and still divides to
    infinity, which is a vanishing portfolio volatility against enormous
    covariances.
    """
    idx = ["A", "B"]
    weights = pd.Series([1.0, 1.0], index=idx)
    cov = pd.DataFrame([[1e300, 0.0], [0.0, 1e300]], index=idx, columns=idx)
    return weights, cov, patch(
        "src.quant.risk.engine.psd.volatility", return_value=1e-300,
    )


def test_a_non_finite_marginal_yields_no_contribution_rather_than_zero():
    """Zeros there published a portfolio with no risk in it."""
    weights, cov, tiny_vol = _overflowing_book()
    with tiny_vol:
        frame = risk_contributions(weights, cov)
    assert frame["component"].isna().all(), "a failed solve reported zero contribution"
    assert frame["marginal"].isna().all()
    assert frame["share"].isna().all()
    assert frame.attrs.get("computation") == "failed"
    assert "UNAVAILABLE" in str(frame.attrs.get("caveat"))
    assert "not a finding that it has none" in str(frame.attrs.get("caveat"))


def test_the_weights_are_still_reported_when_the_solve_fails():
    """What the book holds is known; what it contributes is not."""
    weights, cov, tiny_vol = _overflowing_book()
    with tiny_vol:
        frame = risk_contributions(weights, cov)
    assert frame["weight"].tolist() == [1.0, 1.0]


def test_an_infinite_covariance_is_refused_before_this_branch():
    """The PSD guard owns that case, and still does."""
    from src.quant.portfolio.psd import NotPositiveSemiDefinite
    idx = ["A", "B"]
    weights = pd.Series([0.5, 0.5], index=idx)
    cov = pd.DataFrame([[np.inf, 0.0], [0.0, 1.0]], index=idx, columns=idx)
    with pytest.raises(NotPositiveSemiDefinite):
        risk_contributions(weights, cov)


def test_a_genuinely_riskless_book_still_reports_zero():
    """Zero is the true answer there, and must survive."""
    idx = ["A"]
    weights = pd.Series([0.0], index=idx)
    cov = pd.DataFrame([[0.0]], index=idx, columns=idx)
    frame = risk_contributions(weights, cov)
    assert frame["component"].fillna(-1).tolist() == [0.0]
    assert frame.attrs.get("computation") != "failed"


def test_a_healthy_book_is_unaffected():
    idx = ["A", "B"]
    weights = pd.Series([0.6, 0.4], index=idx)
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]], index=idx, columns=idx)
    frame = risk_contributions(weights, cov)
    assert frame["component"].notna().all()
    assert frame.attrs.get("computation") != "failed"


# ── a real zero survives backend serialization ──────────────────────────────

def test_a_zero_macd_histogram_is_not_erased():
    """0.0 is the crossover itself — the moment the averages meet."""
    src = api.Path("api/index.py").read_text()
    assert "prediction.macd_histogram is not None" in src, (
        "the MACD histogram is serialised with a truthiness check, so an exact "
        "0.0 — the crossover — is reported as not computed"
    )
    assert "round(prediction.macd_histogram, 4) if prediction.macd_histogram else None" not in src


# ── metrics reset is not an anonymous GET ───────────────────────────────────

@pytest.fixture
def client():
    return TestClient(api.app)


def test_metrics_read_is_public_and_unchanged(client):
    assert client.get("/api/metrics").status_code == 200


def test_a_get_can_no_longer_reset_the_window(client):
    """A crawler, a prefetch or a reload destroyed the observability window."""
    with patch.object(api.observability.registry, "reset") as reset:
        client.get("/api/metrics?reset=true")
        client.get("/api/metrics")
    assert reset.call_count == 0, "a GET still resets global observability state"


def test_resetting_requires_authentication(client):
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value=None), \
         patch.object(api.observability.registry, "reset") as reset:
        r = client.post("/api/metrics/reset")
    assert r.status_code == 401
    assert reset.call_count == 0


def test_an_authenticated_operator_can_reset(client):
    with patch.object(clerk_auth, "is_configured", return_value=True), \
         patch.object(clerk_auth, "verify_token", return_value="user_1"), \
         patch.object(api.observability.registry, "reset") as reset:
        r = client.post("/api/metrics/reset")
    assert r.status_code == 200
    assert reset.call_count == 1
