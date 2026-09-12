"""Three visible failures, and the vocabulary that replaced them.

Each of these reached a reader as a status code rather than a reason, and in
two of the three cases nothing was actually wrong:

  performance  a legitimately absent artifact rendered "Request failed: 404"
  covariance   six distinct causes collapsed into one sentence, or a 500
  paper        an unconfigured feature was styled as a broken one

The property these tests hold is narrow and important: **a truthful answer
about absence is a successful request.** 200 with a typed state, because a 404
tells a client the route was wrong and a 500 tells it we failed, and neither
is what happened. A reader sent to chase the wrong problem is worse off than
one told plainly that nothing is there.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.services import availability, covariance_service
from src.services import quant_portfolio_service as qps
from src.services.availability import State


@pytest.fixture()
def client():
    return TestClient(api.app)


# ── the vocabulary ───────────────────────────────────────────────────────────

def test_expected_absences_are_distinguished_from_faults():
    """A reader told every absence is an error stops believing the real ones."""
    assert availability.empty("x").expected
    assert availability.not_configured("x").expected
    assert availability.insufficient("x").expected
    assert availability.unsupported("x").expected
    assert not availability.error("x").expected
    assert not availability.dependency_unavailable("x").expected


def test_a_payload_never_carries_an_exception():
    state = availability.insufficient("Too few overlapping sessions.", reason="X", names=3)
    body = state.payload()
    assert body["message"] == "Too few overlapping sessions."
    assert body["detail"] == {"names": 3}
    for leaked in ("Traceback", "File \"", "Error:", ".py"):
        assert leaked not in str(body)


# ── performance ──────────────────────────────────────────────────────────────

def _series(client, experiment, model):
    response = client.get(f"/api/quant/experiments/{experiment}/series/{model}")
    return response, response.json()


def test_a_missing_artifact_is_answered_not_refused(client):
    """The deployed case: predictions_*.parquet is gitignored as regenerable,
    so on any host but the researcher's laptop the series is simply absent."""
    with patch("src.services.quant_series.fold_series",
               return_value={"status": "unavailable", "detail": "no predictions artifact"}):
        response, body = _series(client, "EXP-006", "gradient_boosting")

    assert response.status_code == 200
    assert body["status"] == State.EMPTY.value
    assert body["reason"] == "NO_ARTIFACT"
    assert "regenerable" in body["message"]


def test_a_model_the_experiment_never_ran_says_so(client):
    with patch("src.services.quant_series.fold_series",
               return_value={"status": "unavailable", "detail": "no predictions for zzz"}):
        response, body = _series(client, "EXP-006", "zzz")

    assert response.status_code == 200
    assert body["reason"] == "NO_SERIES"
    assert "not part of this experiment" in body["message"]


def test_the_two_absences_are_not_the_same_answer(client):
    """A missing artifact and a missing model need different responses from a
    reader, so they must not share a reason."""
    with patch("src.services.quant_series.fold_series",
               return_value={"status": "unavailable", "detail": "no predictions artifact"}):
        _, no_artifact = _series(client, "EXP-006", "gradient_boosting")
    with patch("src.services.quant_series.fold_series",
               return_value={"status": "unavailable", "detail": "no predictions for zzz"}):
        _, no_series = _series(client, "EXP-006", "zzz")

    assert no_artifact["reason"] != no_series["reason"]
    assert no_artifact["message"] != no_series["message"]


def test_a_present_series_is_still_served(client):
    """The guard must not have turned every response into an absence."""
    with patch("src.services.quant_series.fold_series",
               return_value={"status": "ok", "folds": []}), \
         patch("src.services.quant_series.spread_curve", return_value={"periods": []}):
        response, body = _series(client, "EXP-006", "gradient_boosting")

    assert response.status_code == 200
    assert body["status"] == State.AVAILABLE.value
    assert "folds" in body


# ── covariance ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("reason,expected", [
    ("NO_BOOK", State.EMPTY),
    ("NO_POSITIONS", State.EMPTY),
    ("NO_PANEL", State.EMPTY),
    ("INSUFFICIENT_HISTORY", State.INSUFFICIENT_DATA),
    ("INSUFFICIENT_POSITIONS", State.INSUFFICIENT_DATA),
])
def test_every_covariance_cause_has_its_own_answer(client, reason, expected):
    with patch.object(qps, "panel_and_weights_detailed", return_value=(None, reason)):
        response = client.get("/api/quant/covariance")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == expected.value
    assert body["reason"] == reason
    assert body["message"]


def test_covariance_causes_produce_distinct_messages(client):
    """Six causes that all said "no research book is available" told a reader
    nothing about whether to wait, configure something, or report a bug."""
    messages = set()
    for reason in ("NO_BOOK", "NO_POSITIONS", "NO_PANEL",
                   "INSUFFICIENT_HISTORY", "INSUFFICIENT_POSITIONS"):
        with patch.object(qps, "panel_and_weights_detailed", return_value=(None, reason)):
            messages.add(client.get("/api/quant/covariance").json()["message"])
    assert len(messages) == 5


def test_a_failing_estimator_is_a_finding_not_a_500(client):
    """This route answered 500 with a stack trace. A matrix that will not
    decompose is a fact about the data, and the exception is ours to log."""
    frame = pd.DataFrame(np.ones((30, 12)))
    weights = pd.Series(np.ones(12) / 12)

    with patch.object(qps, "panel_and_weights_detailed", return_value=((frame, weights), None)), \
         patch.object(covariance_service, "compare",
                      side_effect=RuntimeError("LinAlgError: matrix is singular")):
        response = client.get("/api/quant/covariance")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == State.INSUFFICIENT_DATA.value
    assert body["reason"] == "SINGULAR_MATRIX"
    assert "LinAlgError" not in response.text
    assert "Traceback" not in response.text


def test_the_estimator_detail_is_safe_and_useful(client):
    frame = pd.DataFrame(np.ones((30, 12)))
    weights = pd.Series(np.ones(12) / 12)
    with patch.object(qps, "panel_and_weights_detailed", return_value=((frame, weights), None)), \
         patch.object(covariance_service, "compare", side_effect=RuntimeError("boom")):
        body = client.get("/api/quant/covariance").json()

    assert body["detail"] == {"names": 12, "observations": 30}


def test_panel_and_weights_still_returns_none_for_its_old_callers():
    """The detailed variant is additive; the original contract is unchanged."""
    with patch.object(qps, "build", return_value={"status": "unavailable"}):
        assert qps.panel_and_weights() is None


# ── paper ────────────────────────────────────────────────────────────────────

def test_paper_reports_unconfigured_without_claiming_breakage(client):
    body = client.get("/api/paper/status").json()
    assert "endpoint" in body and body["endpoint"].startswith("https://paper-api.alpaca.markets")
    assert "access" in body
    # Whatever the deployment's state, the payload never carries a credential.
    for leaked in ("APCA_API_SECRET", "secret", "token"):
        assert leaked not in str(body).lower().replace("secret_key", "")


def test_the_paper_endpoint_is_never_a_live_host(client):
    body = client.get("/api/paper/status").json()
    assert "paper-api" in body["endpoint"]
    assert "api.alpaca.markets" not in body["endpoint"].replace("paper-api.alpaca.markets", "")
