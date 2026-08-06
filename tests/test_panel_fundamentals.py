"""
Point-in-time fundamentals tests.

The whole value of this module is one property: a figure published in 2023
must be invisible on a 2020 observation date. That is not testable by
inspection — a look-ahead bug here produces better-looking results, never an
error — so it is asserted directly, including the restatement case that a
single-snapshot fundamentals API cannot even represent.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.panel.fundamentals import PointInTimeFacts


def _fact(label, period_end, value, filed, form="10-K"):
    return {"label": label, "period_end": period_end, "value": value,
            "filed": filed, "form": form}


ASSETS = [
    _fact("Total assets", "2021-12-31", 100.0, "2022-02-15"),
    _fact("Total assets", "2022-12-31", 120.0, "2023-02-15"),
    _fact("Total assets", "2021-12-31", 105.0, "2023-02-15"),   # restated
    _fact("Total assets", "2023-12-31", 150.0, "2024-02-15"),
]


# ── the property that matters ────────────────────────────────────────────────

def test_a_future_filing_is_invisible():
    facts = PointInTimeFacts(ASSETS)
    series = facts.annual_series("Total assets", date(2022, 6, 1))
    assert [f.period_end for f in series] == ["2021-12-31"]
    assert series[0].value == 100.0


def test_a_filing_is_visible_on_its_filing_date():
    facts = PointInTimeFacts(ASSETS)
    assert facts.latest("Total assets", date(2022, 2, 15)).value == 100.0
    assert facts.latest("Total assets", date(2022, 2, 14)) is None


def test_a_restatement_appears_only_after_it_was_filed():
    """The case a single-snapshot API cannot represent at all."""
    facts = PointInTimeFacts(ASSETS)

    before = facts.annual_series("Total assets", date(2023, 2, 14))
    assert next(f.value for f in before if f.period_end == "2021-12-31") == 100.0

    after = facts.annual_series("Total assets", date(2023, 2, 15))
    assert next(f.value for f in after if f.period_end == "2021-12-31") == 105.0


def test_year_over_year_uses_only_what_was_knowable():
    facts = PointInTimeFacts(ASSETS)
    # On 2023-06-01 the 2022 10-K is out: 120 against a restated 105.
    assert facts.year_over_year("Total assets", date(2023, 6, 1)) == pytest.approx(120 / 105 - 1)
    # On 2022-06-01 only one period exists, so no growth rate.
    assert facts.year_over_year("Total assets", date(2022, 6, 1)) is None


def test_growth_off_a_non_positive_base_is_none():
    facts = PointInTimeFacts([
        _fact("Total assets", "2021-12-31", 0.0, "2022-02-15"),
        _fact("Total assets", "2022-12-31", 50.0, "2023-02-15"),
    ])
    assert facts.year_over_year("Total assets", date(2023, 6, 1)) is None


# ── shape and guards ─────────────────────────────────────────────────────────

def test_quarterly_filings_are_excluded_from_annual_series():
    """A 10-Q in a year-over-year comparison would read seasonality as growth."""
    facts = PointInTimeFacts(ASSETS + [
        _fact("Total assets", "2023-03-31", 130.0, "2023-05-01", form="10-Q"),
    ])
    series = facts.annual_series("Total assets", date(2024, 6, 1))
    assert "2023-03-31" not in [f.period_end for f in series]


def test_series_is_oldest_period_first():
    facts = PointInTimeFacts(ASSETS)
    series = facts.annual_series("Total assets", date(2024, 6, 1))
    assert [f.period_end for f in series] == ["2021-12-31", "2022-12-31", "2023-12-31"]


def test_ratio_uses_the_same_point_in_time_view():
    facts = PointInTimeFacts(ASSETS + [
        _fact("Net income", "2022-12-31", 12.0, "2023-02-15"),
        _fact("Net income", "2023-12-31", 30.0, "2024-02-15"),
    ])
    assert facts.ratio("Net income", "Total assets", date(2023, 6, 1)) == pytest.approx(12 / 120)
    assert facts.ratio("Net income", "Total assets", date(2024, 6, 1)) == pytest.approx(30 / 150)


def test_ratio_is_none_on_a_non_positive_denominator():
    facts = PointInTimeFacts([
        _fact("Net income", "2022-12-31", 5.0, "2023-02-15"),
        _fact("Total assets", "2022-12-31", 0.0, "2023-02-15"),
    ])
    assert facts.ratio("Net income", "Total assets", date(2023, 6, 1)) is None


def test_missing_label_returns_nothing_rather_than_zero():
    facts = PointInTimeFacts(ASSETS)
    assert facts.annual_series("Revenue", date(2024, 6, 1)) == []
    assert facts.latest("Revenue", date(2024, 6, 1)) is None
    assert facts.year_over_year("Revenue", date(2024, 6, 1)) is None


def test_empty_history_is_handled():
    facts = PointInTimeFacts([])
    assert len(facts) == 0
    assert facts.visible(date(2024, 1, 1)) == []
    assert facts.as_of_summary(date(2024, 1, 1))["facts_visible"] == 0


def test_rows_without_a_filing_date_are_dropped():
    """A fact with no filing date cannot be placed in time, so it is unusable."""
    facts = PointInTimeFacts([
        {"label": "Total assets", "period_end": "2022-12-31", "value": 1.0, "filed": None},
        _fact("Total assets", "2022-12-31", 120.0, "2023-02-15"),
    ])
    assert len(facts) == 1


def test_summary_reports_provenance():
    facts = PointInTimeFacts(ASSETS)
    summary = facts.as_of_summary(date(2023, 6, 1))
    assert summary["facts_visible"] == 3
    assert summary["latest_filing"] == "2023-02-15"
    assert summary["labels"] == ["Total assets"]
