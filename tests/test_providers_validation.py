"""
Price validation tests.

The motivating incident: a vendor returned a zero close while the primary was
in cooldown, and four of eleven sector rows died with `float division by
zero`. The crash was the lucky outcome — a zero close inside a return
calculation yields −100%, which looks like a real number and would have
flowed into momentum, the score, the verdict, and eventually the panel as
point-in-time truth.

So these tests care about two things: that impossible values cannot reach a
consumer, and that dropping them is never silent.
"""

from __future__ import annotations

import math

import pytest

from src.providers.orchestrator import _is_trustworthy, _quality_summary
from src.providers.schemas import OHLCVBar, PriceSeries
from src.providers.validation import MIN_RETENTION, SeriesQuality, sanitize_bars


def _bar(close, low=None, high=None, day="2024-01-02") -> OHLCVBar:
    return OHLCVBar(date=day, close=close, low=low, high=high)


def _good(count: int) -> list[OHLCVBar]:
    return [_bar(100.0 + index, low=99.0 + index, high=101.0 + index)
            for index in range(count)]


# ── what must be dropped ─────────────────────────────────────────────────────

@pytest.mark.parametrize("close", [0.0, -1.0, -0.0001])
def test_non_positive_closes_are_dropped(close):
    """A price of zero or less is not a price."""
    kept, quality = sanitize_bars([_bar(close), _bar(100.0)])
    assert len(kept) == 1
    assert quality.dropped_non_positive == 1


@pytest.mark.parametrize("close", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_closes_are_dropped(close):
    kept, quality = sanitize_bars([_bar(close), _bar(100.0)])
    assert len(kept) == 1
    assert quality.dropped_non_finite == 1


def test_impossible_high_low_is_dropped():
    kept, quality = sanitize_bars([_bar(100.0, low=110.0, high=90.0), _bar(100.0)])
    assert len(kept) == 1
    assert quality.dropped_impossible_range == 1


def test_missing_close_is_dropped():
    class Bar:
        close = None
    kept, quality = sanitize_bars([Bar(), _bar(100.0)])
    assert len(kept) == 1
    assert quality.dropped_non_finite == 1


# ── what must NOT be dropped ─────────────────────────────────────────────────

def test_close_outside_range_is_recorded_but_kept():
    """Adjusted closes legitimately sit outside the unadjusted intraday range.

    Vendors apply dividend and split adjustments to the close but not always
    to the high and low. Dropping these would discard good data to satisfy a
    rule that does not hold in practice — so it is counted, not enforced.
    """
    kept, quality = sanitize_bars([_bar(120.0, low=99.0, high=101.0)])
    assert len(kept) == 1, "an adjusted close must survive"
    assert quality.suspicious_close_outside_range == 1
    assert quality.dropped == 0


def test_bars_without_high_low_are_kept():
    """Some vendors return close only. That is thin, not invalid."""
    kept, quality = sanitize_bars([_bar(100.0), _bar(101.0)])
    assert len(kept) == 2
    assert quality.is_clean


def test_clean_data_is_untouched():
    bars = _good(250)
    kept, quality = sanitize_bars(bars)
    assert kept == bars
    assert quality.is_clean and quality.retention == 1.0


def test_chronological_order_is_preserved():
    """Consumers read `bars[-1]` as latest; reordering would corrupt every one."""
    bars = [_bar(100.0, day="2024-01-01"), _bar(0.0, day="2024-01-02"),
            _bar(102.0, day="2024-01-03")]
    kept, _ = sanitize_bars(bars)
    assert [bar.date for bar in kept] == ["2024-01-01", "2024-01-03"]


# ── the record is never silent ───────────────────────────────────────────────

def test_quality_counts_everything():
    kept, quality = sanitize_bars([
        _bar(100.0), _bar(0.0), _bar(float("nan")),
        _bar(100.0, low=110.0, high=90.0), _bar(120.0, low=99.0, high=101.0),
    ])
    assert quality.bars_received == 5
    assert quality.bars_kept == 2
    assert quality.dropped == 3
    assert quality.suspicious_close_outside_range == 1
    assert not quality.is_clean


def test_summary_names_what_went_wrong():
    _, quality = sanitize_bars([_bar(0.0), _bar(float("inf")), _bar(100.0)])
    summary = quality.summary()
    assert "non-positive" in summary and "non-finite" in summary
    assert "1/3" in summary or "1/3 bars" in summary


def test_empty_series_is_not_a_validation_failure():
    """Absent data and bad data need different responses from the chain."""
    kept, quality = sanitize_bars([])
    assert kept == []
    assert quality.retention == 1.0
    assert quality.is_trustworthy


# ── retention and trust ──────────────────────────────────────────────────────

def test_a_mostly_bad_series_is_untrustworthy():
    bars = _good(10) + [_bar(0.0) for _ in range(10)]
    _, quality = sanitize_bars(bars)
    assert quality.retention == 0.5
    assert not quality.is_trustworthy


def test_a_slightly_imperfect_series_stays_trustworthy():
    """One bad tick in a year is a glitch, not a malfunction."""
    bars = _good(199) + [_bar(0.0)]
    _, quality = sanitize_bars(bars)
    assert quality.retention >= MIN_RETENTION
    assert quality.is_trustworthy


# ── the schema boundary ──────────────────────────────────────────────────────

def test_price_series_sanitizes_on_construction():
    """No vendor can route around this — every adapter returns a PriceSeries."""
    series = PriceSeries(symbol="XLI", bars=[_bar(100.0), _bar(0.0), _bar(102.0)])
    assert len(series.bars) == 2
    assert series.quality.dropped_non_positive == 1
    assert all(bar.close > 0 for bar in series.bars)


def test_round_tripping_does_not_double_count():
    """A cached series re-validated would otherwise report a fake retention."""
    original = PriceSeries(symbol="AAPL", bars=[_bar(100.0), _bar(0.0)])
    revived = PriceSeries.model_validate(original.model_dump())
    assert revived.quality.bars_received == original.quality.bars_received
    assert revived.quality.bars_kept == original.quality.bars_kept
    assert len(revived.bars) == 1


def test_clean_series_reports_full_retention():
    series = PriceSeries(symbol="AAPL", bars=_good(100))
    assert series.quality.is_clean
    assert series.quality.retention == 1.0


def test_empty_price_series_is_valid():
    series = PriceSeries(symbol="AAPL")
    assert series.bars == []
    assert series.quality.is_trustworthy


# ── the fallback chain reacts ────────────────────────────────────────────────

def test_chain_rejects_an_untrustworthy_payload():
    bad = PriceSeries(symbol="X", bars=_good(2) + [_bar(0.0) for _ in range(8)])
    assert not _is_trustworthy(bad)


def test_chain_accepts_a_healthy_payload():
    assert _is_trustworthy(PriceSeries(symbol="X", bars=_good(50)))


def test_chain_trusts_payloads_without_a_quality_record():
    """Validation is opt-in per schema; adding it must not retroactively
    start rejecting payload types that were never checked."""
    class Unchecked:
        pass

    assert _is_trustworthy(Unchecked())
    assert _quality_summary(Unchecked()) == "no quality record"


# ── the original crash ───────────────────────────────────────────────────────

def test_the_sector_row_crash_cannot_recur():
    """Reproduces the incident: a zero close mid-series killed the whole row."""
    from src.services.dashboard_service import _sector_row
    from src.providers.schemas import ProviderResult
    from src import providers

    bars = _good(120)
    poisoned = bars[:60] + [_bar(0.0, day="2024-06-01")] + bars[60:]
    series = PriceSeries(symbol="XLI", bars=poisoned)

    original = providers.market_data.get_series
    try:
        providers.market_data.get_series = lambda *a, **k: ProviderResult(
            data=series, source="test", confidence=0.85
        )
        row = _sector_row("XLI", "Industrials")
    finally:
        providers.market_data.get_series = original

    assert row is not None, "a single bad bar must not delete the sector"
    assert math.isfinite(row["volatility"])
