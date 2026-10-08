"""A failure that is held in a cache for hours is a failure that lasts for hours.

`get_quality_inputs` and `get_pead_inputs` feed the verdict's quality and earnings-surprise
sleeves, and cached their answer for six hours *including* the answer "nothing", which is
what both vendors being down looks like. One transient outage took those factors out of a
ticker's verdict until the next day. The official record cached a record with a failed
source for the same six hours.

The rule these tests hold: an answer that is absent because nobody could be asked is kept
for minutes, and an answer that is absent because there is genuinely nothing keeps the long
TTL. The two are told apart by whether anything failed, not by whether anything came back.
"""

from __future__ import annotations

import math
import sys
import time
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest

from src.services import fundamentals_data, official_record


@pytest.fixture(autouse=True)
def _fresh():
    fundamentals_data.reset_for_tests()
    official_record.reset_for_tests()
    yield
    fundamentals_data.reset_for_tests()
    official_record.reset_for_tests()


def _ttl(cache, key) -> float:
    return cache[key][0] - time.time()


GOOD = {"gross_profit_over_assets": 0.3, "net_issuance_yoy": 0.01, "asset_growth_yoy": 0.05, "source": "fmp"}


# ── quality inputs ───────────────────────────────────────────────────────────

def test_both_vendors_failing_is_remembered_for_minutes_not_hours():
    with patch.object(fundamentals_data, "_from_fmp", return_value=None), \
         patch.object(fundamentals_data, "_from_yfinance", return_value=None):
        data = fundamentals_data.get_quality_inputs("NVDA")
    assert data["source"] is None
    ttl = _ttl(fundamentals_data._cache, "quality:NVDA")
    assert 0 < ttl <= fundamentals_data.UNAVAILABLE_TTL_SECONDS + 1
    assert fundamentals_data.UNAVAILABLE_TTL_SECONDS < fundamentals_data.CACHE_TTL_SECONDS / 10


def test_an_answer_keeps_the_long_ttl():
    with patch.object(fundamentals_data, "_from_fmp", return_value=dict(GOOD)):
        fundamentals_data.get_quality_inputs("NVDA")
    assert _ttl(fundamentals_data._cache, "quality:NVDA") > fundamentals_data.CACHE_TTL_SECONDS - 60


def test_a_remembered_outage_is_not_hammered_and_is_retried_once_it_expires():
    calls = []

    def fmp(symbol):
        calls.append(symbol)

    with patch.object(fundamentals_data, "_from_fmp", side_effect=fmp), \
         patch.object(fundamentals_data, "_from_yfinance", return_value=None):
        fundamentals_data.get_quality_inputs("NVDA")
        fundamentals_data.get_quality_inputs("NVDA")
        assert len(calls) == 1, "a failure inside its window must be served from the cache"
        # Time passes beyond the short window...
        expires, value = fundamentals_data._cache["quality:NVDA"]
        fundamentals_data._cache["quality:NVDA"] = (time.time() - 1, value)
        fundamentals_data.get_quality_inputs("NVDA")
    assert len(calls) == 2, "the failure must be retried after its short window"


def test_recovery_replaces_the_remembered_outage():
    with patch.object(fundamentals_data, "_from_fmp", return_value=None), \
         patch.object(fundamentals_data, "_from_yfinance", return_value=None):
        assert fundamentals_data.get_quality_inputs("NVDA")["source"] is None
    fundamentals_data._cache["quality:NVDA"] = (time.time() - 1, fundamentals_data._cache["quality:NVDA"][1])
    with patch.object(fundamentals_data, "_from_fmp", return_value=dict(GOOD)):
        assert fundamentals_data.get_quality_inputs("NVDA")["source"] == "fmp"


# ── what the FMP reader does with a reply it was not written for ─────────────

def _fmp_vendor():
    from src import providers
    return providers.fundamentals.fmp


@pytest.mark.parametrize("income,balance", [
    (["Error"], ["Error"]),
    ([None], [None]),
    ([1, 2], [3, 4]),
    ([{"grossProfit": 1}], ["not a row"]),
])
def test_rows_that_are_not_objects_are_no_answer_not_an_exception(income, balance):
    vendor = _fmp_vendor()
    replies = iter([income, balance])
    with patch.object(type(vendor), "healthy", new_callable=PropertyMock, return_value=True), \
         patch.object(vendor, "_get_json", side_effect=lambda *a, **k: next(replies)):
        assert fundamentals_data._from_fmp("NVDA") is None


def test_a_non_finite_figure_is_absent_not_a_quality_input():
    assert fundamentals_data._safe_ratio("nan", 5) is None
    assert fundamentals_data._safe_ratio(1e308, 1e-308) is None
    assert fundamentals_data._yoy(float("inf"), 1) is None
    assert fundamentals_data._yoy("inf", 2) is None
    assert fundamentals_data._safe_ratio(50, 100) == 0.5
    assert math.isclose(fundamentals_data._yoy(110, 100), 0.1)


# ── earnings-surprise inputs ─────────────────────────────────────────────────

def _fake_yfinance(earnings_dates=None, raises=None):
    class Ticker:
        def __init__(self, symbol):
            if raises:
                raise raises

        @property
        def earnings_dates(self):
            return earnings_dates

    return SimpleNamespace(Ticker=Ticker)


def test_a_lookup_that_raised_is_retried_soon():
    with patch.dict(sys.modules, {"yfinance": _fake_yfinance(raises=RuntimeError("down"))}):
        result = fundamentals_data.get_pead_inputs("NVDA")
    assert result == {"surprise_pct": None, "days_since": None}
    assert 0 < _ttl(fundamentals_data._cache, "pead:NVDA") <= fundamentals_data.UNAVAILABLE_TTL_SECONDS + 1


def test_a_lookup_that_answered_with_nothing_keeps_the_long_ttl():
    with patch.dict(sys.modules, {"yfinance": _fake_yfinance(earnings_dates=None)}):
        result = fundamentals_data.get_pead_inputs("NVDA")
    assert result == {"surprise_pct": None, "days_since": None}
    assert _ttl(fundamentals_data._cache, "pead:NVDA") > fundamentals_data.CACHE_TTL_SECONDS - 60


# ── the official record ──────────────────────────────────────────────────────

HEALTHCARE = {"name": "ACME PHARMA INC", "sic": "2834", "sic_description": "Pharmaceutical Preparations"}
SOFTWARE = {"name": "ACME SOFTWARE INC", "sic": "7372", "sic_description": "Services-Prepackaged Software"}


def _build(entity, *, federal="ok", drug="ok", device="ok", trials="ok", configured=True):
    """Drive `build` with each source answering, answering empty, or failing."""
    src = official_record.sources

    def answer(kind, payload_key, value):
        def call(*a, **k):
            if kind == "fail":
                raise RuntimeError("source down")
            return {payload_key: value if kind == "ok" else ([] if payload_key != "active_total" else 0)}
        return call

    with patch.object(src.sec, "get_entity", return_value=entity), \
         patch.object(type(src.federal_register), "available", new_callable=PropertyMock, return_value=configured), \
         patch.object(type(src.openfda), "available", new_callable=PropertyMock, return_value=configured), \
         patch.object(type(src.clinicaltrials), "available", new_callable=PropertyMock, return_value=configured), \
         patch.object(src.federal_register, "get_official_actions", answer("fail" if federal == "fail" else federal, "documents", [{"title": "x"}])), \
         patch.object(src.openfda, "get_recalls", lambda core, kind: answer("fail" if (drug if kind == "drug" else device) == "fail" else (drug if kind == "drug" else device), "recalls", [{"id": 1}])()), \
         patch.object(src.clinicaltrials, "get_trials", answer("fail" if trials == "fail" else trials, "active_total", 3)):
        return official_record.build("ACME")


def test_a_record_with_a_failed_source_is_held_briefly():
    record = _build(HEALTHCARE, drug="fail")
    assert record["sections"]["fda_drug_recalls"]["status"] == "unavailable"
    assert record["sections"]["federal_register"]["status"] == "ok"
    ttl = _ttl(official_record._cache, "ACME")
    assert 0 < ttl <= official_record.DEGRADED_TTL_SECONDS + 1


def test_a_complete_record_keeps_the_long_ttl():
    record = _build(HEALTHCARE)
    assert all(s["status"] in {"ok", "empty"} for s in record["sections"].values())
    assert _ttl(official_record._cache, "ACME") > official_record.CACHE_TTL_SECONDS - 60


def test_sources_that_do_not_apply_do_not_shorten_the_ttl():
    record = _build(SOFTWARE)
    assert record["sections"]["fda_drug_recalls"]["status"] == "not_applicable"
    assert _ttl(official_record._cache, "ACME") > official_record.CACHE_TTL_SECONDS - 60


def test_a_record_where_every_source_failed_is_not_held_at_all():
    record = _build(HEALTHCARE, federal="fail", drug="fail", device="fail", trials="fail")
    assert all(s["status"] == "unavailable" for s in record["sections"].values())
    assert "ACME" not in official_record._cache
