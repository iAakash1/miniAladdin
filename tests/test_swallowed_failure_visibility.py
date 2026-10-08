"""A block that fails quietly must not vanish quietly.

The research handler treats every enrichment block as non-fatal and swallows the
exception, which keeps one broken lookup from costing the whole response. It also
meant the provenance table simply had no row for the block, which reads exactly
like a block nobody asked for. The same was true of a macro rate that did not
load, and a degraded macro-stress snapshot was kept for fifteen minutes.

These tests hold each of those to the stronger promise: the reader is told the
reading is missing, and a transient failure is retried soon.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.providers.schemas import ProviderResult
from src.services.provenance import Ledger


# ── the recorder ─────────────────────────────────────────────────────────────

def test_a_gap_is_a_missing_row_with_a_reason():
    ledger = Ledger("AAPL")
    ledger.record_gap(label="Ownership & short interest", kind="fundamental")
    built = ledger.build()
    [row] = built["inputs"]
    assert row["label"] == "Ownership & short interest"
    assert row["health"] == "missing"
    assert "failed" in row["note"]
    assert built["summary"]["missing"] == 1


def test_a_gap_never_overwrites_what_an_input_already_recorded():
    ledger = Ledger("AAPL")
    ledger.record(label="SEC filings", kind="fundamental",
                  result=ProviderResult(data=[1], source="sec", confidence=0.9))
    ledger.record_gap(label="SEC filings", kind="fundamental")
    rows = ledger.build()["inputs"]
    assert len(rows) == 1 and rows[0]["health"] == "ok"


# ── the research route ───────────────────────────────────────────────────────

def _run_research(synthetic_series, **broken):
    unavailable = (None, {"status": "UNAVAILABLE", "error": "none", "yield_spread": None,
                          "inflation_rate": None, "fed_funds_rate": None,
                          "yield_curve_inverted": None, "recession_warning": None})
    patches = [
        patch.object(api, "_fetch_macro_safe", return_value=unavailable),
        patch.object(api.providers.market_data, "get_series", return_value=synthetic_series("AAPL")),
    ]
    for name, owner in broken.items():
        patches.append(patch.object(getattr(api.providers, owner[0]), name, side_effect=RuntimeError("boom")))
    for p in patches:
        p.start()
    try:
        with TestClient(api.app) as client:
            return client.get("/api/research/AAPL")
    finally:
        for p in reversed(patches):
            p.stop()


@pytest.mark.parametrize("method,owner,label", [
    ("ownership_evidence", ("fundamentals",), "Ownership & short interest"),
    ("analyst_evidence", ("fundamentals",), "Analyst targets"),
    ("target_evidence", ("fundamentals",), "Price targets"),
    ("statement_evidence", ("fundamentals",), "Reported statements"),
    ("filings_evidence", ("filings",), "SEC filings"),
    ("street_evidence", ("fundamentals",), "Street & insider activity"),
])
def test_an_enrichment_block_that_raises_is_listed_as_missing(offline_network, synthetic_series, method, owner, label):
    response = _run_research(synthetic_series, **{method: owner})
    assert response.status_code == 200, response.text
    rows = {row["label"]: row for row in response.json()["provenance"]["inputs"]}
    assert label in rows, f"{label} left no trace in the provenance table"
    assert rows[label]["health"] == "missing"
    assert "failed" in (rows[label]["note"] or "")


# ── macro context ────────────────────────────────────────────────────────────

def _snapshot(series_id, count=8):
    if series_id == "DGS10":
        return ProviderResult(data=None, error="timeout")
    return ProviderResult(data=[("2026-09-01", 4.0), ("2026-10-01", 4.1)], source="fred", confidence=0.85)


def test_a_macro_reading_that_did_not_load_is_named():
    stress = {"nfci": -0.5, "credit_spread_z": None, "vix_percentile": 0.4, "term_spread": 0.3}
    with patch("src.providers.macro.get_series_snapshot", side_effect=_snapshot):
        ctx = api._macro_context(stress)
    assert "10-year Treasury" in ctx["unavailable"]
    assert "Credit spread (BAA−10y)" in ctx["unavailable"]
    assert "Not available for this run" in ctx["note"]
    assert "10-year Treasury" in ctx["note"]
    # The ones that did load are not reported as missing.
    assert "Policy rate" not in ctx["unavailable"]


def test_a_complete_macro_context_claims_nothing_is_missing():
    stress = {"nfci": -0.5, "credit_spread_z": 0.1, "vix_percentile": 0.4, "term_spread": 0.3}
    with patch("src.providers.macro.get_series_snapshot",
               return_value=ProviderResult(data=[("2026-09-01", 4.0), ("2026-10-01", 4.1)], source="fred")):
        ctx = api._macro_context(stress)
    assert ctx["unavailable"] == []
    assert "Not available" not in ctx["note"]


# ── the stress snapshot ──────────────────────────────────────────────────────

def _bars(count, base=20.0):
    from src.providers.schemas import OHLCVBar, PriceSeries
    import pandas as pd
    dates = pd.bdate_range("2025-06-02", periods=count).strftime("%Y-%m-%d")
    bars = [OHLCVBar(date=d, open=base + i % 5, high=base + i % 5 + 1, low=base + i % 5 - 1,
                     close=base + i % 5, volume=1) for i, d in enumerate(dates)]
    return ProviderResult(data=PriceSeries(symbol="^VIX", bars=bars), source="fixture")


def _healthy_series(series_id, count=5):
    n = max(count, 5)
    return ProviderResult(data=[(f"2026-0{1 + i % 9}-01", 1.0 + (i % 7) * 0.1) for i in range(n)],
                          source="fred", confidence=0.85)


def _ttl_of_cached_snapshot():
    with api._macro_lock:
        expires, _ = api._stress_cache["v1"]
    return expires - time.time()


def test_a_degraded_stress_snapshot_is_retried_soon():
    api._stress_cache.clear()
    with patch.object(api.providers.macro, "get_series_snapshot",
                      return_value=ProviderResult(data=None, error="fred down")), \
         patch.object(api.providers.market_data, "get_series", return_value=ProviderResult(data=None, error="down")):
        stress = api._stress_inputs()
    assert all(value is None for value in stress.values())
    assert _ttl_of_cached_snapshot() <= api.STRESS_DEGRADED_TTL + 1
    assert api.STRESS_DEGRADED_TTL < api.STRESS_CACHE_TTL
    api._stress_cache.clear()


def test_a_complete_stress_snapshot_is_kept_for_the_full_ttl():
    api._stress_cache.clear()
    # BAA10Y needs 60 observations for the z-score; the others need a handful.
    with patch.object(api.providers.macro, "get_series_snapshot",
                      side_effect=lambda sid, count=5: _healthy_series(sid, 260 if sid == "BAA10Y" else count)), \
         patch.object(api.providers.market_data, "get_series", return_value=_bars(80)):
        stress = api._stress_inputs()
    assert all(value is not None for value in stress.values()), stress
    assert _ttl_of_cached_snapshot() > api.STRESS_DEGRADED_TTL + 60
    api._stress_cache.clear()
