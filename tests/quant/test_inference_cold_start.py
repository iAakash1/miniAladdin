"""
A cold start is not an outage.

Render's free tier spins a service down after ~15 minutes and takes roughly a
minute to wake — measured 43.0s for the backend and 42.7s for the inference
service on 2026-09-01, against a request budget of 8s. A timeout is therefore
the *expected* first response after a quiet period, and reporting it as
"unavailable" describes the deployment's most routine state as a fault.
"""

from __future__ import annotations

import requests

from src.services.inference_client import _from_exception


def test_a_timeout_is_reported_as_waking():
    result = _from_exception(requests.exceptions.Timeout("timed out"))
    assert result["status"] == "waking"
    assert "starting" in result["remedy"]
    assert "spins a service down" in result["remedy"]
    # The research evidence does not depend on the service, and the message says so.
    assert "committed artifacts" in result["remedy"]


def test_a_connection_error_is_reported_as_waking():
    result = _from_exception(requests.exceptions.ConnectionError("refused"))
    assert result["status"] == "waking"
    assert "persists" in result["remedy"], (
        "a connection error might also be a real outage; the message must say "
        "when to stop waiting"
    )


def test_an_unexpected_error_stays_unavailable():
    """Only the two transport causes are softened. Everything else is an outage."""
    result = _from_exception(ValueError("something structural"))
    assert result["status"] == "unavailable"
    assert "ValueError" in result["detail"]


def test_every_classification_preserves_the_promotion_state():
    """No transport state may imply the model became promotable."""
    for error in (
        requests.exceptions.Timeout("t"),
        requests.exceptions.ConnectionError("c"),
        ValueError("v"),
    ):
        result = _from_exception(error)
        assert result["research_status"] == "EXPERIMENTAL"
        assert result["promotion_status"] == "BLOCKED"
