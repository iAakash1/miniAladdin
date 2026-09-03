"""A statistic that could not be computed must not take an endpoint down.

`/api/ml/labels/fwd_rank_21` returned 500 for exactly this reason. One baseline
model had twelve observations, so the deflated Sharpe routine correctly refused
a verdict — `deflated_probability` and `significant` were already null, with a
note saying "fewer than 30 periods" — but the inputs it could not compute stayed
NaN, and `json.dumps` refuses NaN. A single unreachable number on one baseline
model blanked the whole label report.

The distinction these tests defend is the one that matters: not computed is null
and stays null. It never becomes zero, because a Sharpe of 0.0 is a measurement
this model never produced.
"""

from __future__ import annotations

import json
import math

import pytest
from fastapi.testclient import TestClient

from api.index import app
from src.services.ml_service import _finite


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _non_finite(payload: object, path: str = "") -> list[str]:
    """Every path in a payload holding a float JSON cannot represent."""
    if isinstance(payload, dict):
        return [p for k, v in payload.items() for p in _non_finite(v, f"{path}.{k}")]
    if isinstance(payload, list):
        return [p for i, v in enumerate(payload) for p in _non_finite(v, f"{path}[{i}]")]
    if isinstance(payload, float) and not math.isfinite(payload):
        return [f"{path} = {payload}"]
    return []


def test_label_report_serialises(client: TestClient) -> None:
    response = client.get("/api/ml/labels/fwd_rank_21")
    assert response.status_code == 200, response.text


def test_label_report_holds_no_non_finite_floats(client: TestClient) -> None:
    payload = client.get("/api/ml/labels/fwd_rank_21").json()
    offenders = _non_finite(payload)
    assert not offenders, "non-finite floats reached the response: " + "; ".join(offenders)


def test_an_uncomputable_statistic_is_null_and_not_zero(client: TestClient) -> None:
    payload = client.get("/api/ml/labels/fwd_rank_21").json()
    short = [
        m for m in payload["models"]
        if (m.get("significance", {}).get("deflated_sharpe") or {}).get("observations", 99) < 30
    ]
    if not short:
        pytest.skip("no model in this study has too few periods for a deflated Sharpe")

    for model in short:
        deflated = model["significance"]["deflated_sharpe"]
        assert deflated["deflated_probability"] is None
        assert deflated["significant"] is None
        # The inputs are absent, not zero. Zero would read as a flat result.
        assert deflated["observed_sharpe"] is None
        assert deflated["observed_sharpe"] != 0
        assert deflated.get("note"), "a refused statistic must say why"


def test_finite_replaces_only_non_finite_floats() -> None:
    payload = {
        "nan": float("nan"),
        "inf": float("inf"),
        "neg_inf": float("-inf"),
        "zero": 0.0,
        "negative": -1.5,
        "int": 7,
        "text": "nan",
        "none": None,
        "nested": [{"deep": float("nan")}, {"deep": 0.25}],
    }
    cleaned = _finite(payload)

    assert cleaned["nan"] is None
    assert cleaned["inf"] is None
    assert cleaned["neg_inf"] is None
    # Everything computable survives untouched, including a genuine zero.
    assert cleaned["zero"] == 0.0
    assert cleaned["negative"] == -1.5
    assert cleaned["int"] == 7
    assert cleaned["text"] == "nan"
    assert cleaned["none"] is None
    assert cleaned["nested"][0]["deep"] is None
    assert cleaned["nested"][1]["deep"] == 0.25
    # And the result is now something JSON can carry.
    json.dumps(cleaned, allow_nan=False)


def test_a_bare_non_finite_float_is_handled() -> None:
    assert _finite(float("nan")) is None
    assert _finite(1.25) == 1.25
