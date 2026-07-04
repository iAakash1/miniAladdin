"""Tests for v2.1 plumbing: analyst snapshot store and fundamentals-data guards."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.services import analyst_store, fundamentals_data


class TestAnalystStore:
    @pytest.fixture(autouse=True)
    def tmp_store(self, tmp_path):
        analyst_store.reset_for_tests(tmp_path / "snapshots")
        yield
        analyst_store.reset_for_tests()

    def test_writes_one_row_per_day(self):
        first = analyst_store.record_snapshot("NVDA", price=190.0, analyst_target=300.0,
                                              pe_ratio=45.0, forward_pe=38.0, eps=4.2)
        second = analyst_store.record_snapshot("NVDA", price=191.0, analyst_target=301.0,
                                               pe_ratio=45.1, forward_pe=38.1, eps=4.2)
        assert first is True
        assert second is False  # same UTC day → deduped

        rows = analyst_store.load_snapshots("NVDA")
        assert len(rows) == 1
        assert rows[0]["analyst_target"] == 300.0
        assert "date" in rows[0] and "ts" in rows[0]

    def test_load_survives_corrupt_lines(self):
        analyst_store.record_snapshot("AAPL", 300.0, 320.0, 35.0, 30.0, 8.0)
        path = analyst_store._path("AAPL")
        with path.open("a") as handle:
            handle.write("{not json\n")
        rows = analyst_store.load_snapshots("AAPL")
        assert len(rows) == 1  # corrupt line skipped, not fatal

    def test_never_raises_on_write_failure(self, tmp_path):
        analyst_store.reset_for_tests(tmp_path / "not" / "writable")
        with patch.object(analyst_store.Path, "mkdir", side_effect=OSError("denied")):
            assert analyst_store.record_snapshot("X", 1.0, None, None, None, None) is False


class TestFundamentalsDataGuards:
    @pytest.fixture(autouse=True)
    def clean(self):
        fundamentals_data.reset_for_tests()
        yield
        fundamentals_data.reset_for_tests()

    def test_all_sources_failing_yield_nones_not_errors(self):
        with patch.object(fundamentals_data, "_from_fmp", return_value=None), \
             patch.object(fundamentals_data, "_from_yfinance", return_value=None):
            data = fundamentals_data.get_quality_inputs("NVDA")
        assert data["gross_profit_over_assets"] is None
        assert data["net_issuance_yoy"] is None
        assert data["asset_growth_yoy"] is None

    def test_quality_inputs_cached(self):
        payload = {"gross_profit_over_assets": 0.4, "net_issuance_yoy": -0.02,
                   "asset_growth_yoy": 0.1, "source": "fmp"}
        with patch.object(fundamentals_data, "_from_fmp", return_value=payload) as mocked:
            first = fundamentals_data.get_quality_inputs("NVDA")
            second = fundamentals_data.get_quality_inputs("NVDA")
        assert mocked.call_count == 1
        assert first == second == payload

    def test_safe_math_helpers(self):
        assert fundamentals_data._safe_ratio(10, 0) is None
        assert fundamentals_data._safe_ratio(None, 5) is None
        assert fundamentals_data._safe_ratio(50, 100) == 0.5
        assert fundamentals_data._yoy(110, 100) == pytest.approx(0.1)
        assert fundamentals_data._yoy(110, 0) is None
