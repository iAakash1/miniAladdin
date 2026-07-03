"""
Opt-in live smoke tests against real upstream APIs.

Skipped by default so CI and local runs stay hermetic. Enable with:

    OMNISIGNAL_LIVE_TESTS=1 python -m pytest tests/test_live_smoke.py -v

(Replaces the old root-level test_api.py script.)
"""

from __future__ import annotations

import os

import pytest
import requests

LIVE = bool(os.getenv("OMNISIGNAL_LIVE_TESTS"))

pytestmark = pytest.mark.skipif(
    not LIVE, reason="live smoke tests are opt-in (set OMNISIGNAL_LIVE_TESTS=1)"
)


def test_fred_api_reachable():
    """FRED responds with observations when a key is configured."""
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        pytest.skip("FRED_API_KEY not configured")
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": "DGS10",
            "api_key": api_key,
            "file_type": "json",
            "limit": 1,
        },
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json().get("observations")


def test_backend_health():
    """The deployed (or locally running) backend reports healthy."""
    base = os.getenv("OMNISIGNAL_API_BASE", "http://localhost:8000")
    r = requests.get(f"{base}/api/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "data_sources" in body


def test_backend_research_shape():
    """A full research response carries the fields the dashboard depends on."""
    base = os.getenv("OMNISIGNAL_API_BASE", "http://localhost:8000")
    r = requests.get(f"{base}/api/research/SPY", params={"fast": "true"}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    for key in ("ticker", "macro", "technicals", "verdict", "mode"):
        assert key in body, f"missing {key}"
