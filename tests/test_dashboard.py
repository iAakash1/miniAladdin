"""Tests for the market intelligence dashboard service (mocked providers)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from src.providers.schemas import MacroSnapshot, OHLCVBar, PriceSeries, ProviderResult
from src.services import dashboard_service as ds


def series_result(closes: list[float], start: date = date(2025, 7, 10)) -> ProviderResult[PriceSeries]:
    bars = []
    day = start
    for close in closes:
        day = date.fromordinal(day.toordinal() + 1)
        while day.weekday() >= 5:
            day = date.fromordinal(day.toordinal() + 1)
        bars.append(OHLCVBar(date=day.isoformat(), close=close, volume=1000))
    return ProviderResult(data=PriceSeries(symbol="X", bars=bars), source="test", confidence=0.85)


def monthly_obs(values: list[float]) -> ProviderResult[list]:
    return ProviderResult(
        data=[(f"2026-{(i % 12) + 1:02d}-01", value) for i, value in enumerate(values)],
        source="fred", confidence=0.85,
    )


@pytest.fixture(autouse=True)
def clean():
    ds.reset_for_tests()
    yield
    ds.reset_for_tests()


class TestMacroCards:
    def test_level_series_card(self):
        obs = monthly_obs([3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.63])
        with patch.object(ds.providers.macro, "get_series_snapshot", return_value=obs):
            card = ds._macro_card({"id": "FEDFUNDS", "label": "Fed", "unit": "%", "explain": "x"})
        assert card["value"] == 3.63
        assert card["previous"] == 3.6
        assert card["change"] == pytest.approx(0.03)
        assert card["direction"] == "up"
        assert len(card["trend"]) == 6

    def test_yoy_series_card(self):
        # 15 monthly index values rising 0.4%/month → ~4.9% y/y
        values = [100 * (1.004 ** i) for i in range(15)]
        with patch.object(ds.providers.macro, "get_series_snapshot", return_value=monthly_obs(values)):
            card = ds._macro_card({"id": "CPIAUCSL", "label": "CPI", "unit": "index",
                                   "yoy": "true", "explain": "x"})
        assert card["unit"] == "% y/y"
        assert card["value"] == pytest.approx(4.9, abs=0.2)

    def test_failed_series_returns_none(self):
        failed = ProviderResult(data=None, error="down")
        with patch.object(ds.providers.macro, "get_series_snapshot", return_value=failed):
            assert ds._macro_card(ds.MACRO_SERIES[0]) is None


class TestSectorsAndBreadth:
    def test_sector_row_and_breadth_score(self):
        rising = series_result([100 + i * 0.5 for i in range(260)])
        with patch.object(ds.providers.market_data, "get_series", return_value=rising):
            breadth, sectors = ds._breadth_and_sectors()

        assert len(sectors) == len(ds.SECTOR_ETFS)
        assert all(row["above_50d"] for row in sectors)
        assert breadth["breadth_score"] == 100
        assert breadth["sector_count"] == 11
        row = sectors[0]
        assert row["strength_21d"] > 0 and row["momentum_63d"] > 0
        assert row["verdict"] in ("Buy", "Strong Buy", "Hold")

    def test_breadth_survives_total_provider_failure(self):
        failed = ProviderResult(data=None, error="down")
        with patch.object(ds.providers.market_data, "get_series", return_value=failed):
            breadth, sectors = ds._breadth_and_sectors()
        assert sectors == []
        assert breadth["breadth_score"] is None


class TestEvents:
    def test_upcoming_sorted_with_countdown(self):
        failed = ProviderResult(data=None, error="down")
        with patch.object(ds.providers.market_data, "get_series", return_value=failed):
            events = ds._events(date(2026, 7, 4))
        assert events, "expected upcoming events from static calendars"
        assert events == sorted(events, key=lambda event: event["date"])
        first = events[0]
        assert first["days_away"] >= 0
        assert first["importance"] in ("high", "medium")

    def test_event_volatility_is_measured_from_bars(self):
        closes = [100.0] * 250
        closes[100] = 102.0  # +2% on an event day
        result = series_result(closes)
        bars = result.data.bars
        event_day = date.fromisoformat(bars[100].date)
        move = ds._event_volatility(bars, [event_day])
        assert move == pytest.approx(2.0, abs=0.1)


class TestAssemblyCache:
    def test_dashboard_caches(self):
        failed = ProviderResult(data=None, error="down")
        snapshot = ProviderResult(data=MacroSnapshot(yield_spread=0.3, inflation_rate=3.0,
                                                     fed_funds_rate=3.6), source="fred", confidence=0.85)
        with patch.object(ds.providers.macro, "get_series_snapshot", return_value=failed), \
             patch.object(ds.providers.macro, "get_macro", return_value=snapshot), \
             patch.object(ds.providers.market_data, "get_series", return_value=failed):
            first = ds.get_dashboard()
            second = ds.get_dashboard()
        assert first["cached"] is False
        assert second["cached"] is True
        assert first["macro"]["regime"]["risk_multiplier"] == 1.0
