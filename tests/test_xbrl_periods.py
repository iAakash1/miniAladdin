"""XBRL facts keyed by the period they describe, not by the filing's year.

Three defects, all found by checking the one thing a balance sheet cannot get
wrong: Assets = Liabilities + Equity. It was failing by up to 51% of assets
for NVDA and by 12% for Microsoft. Every individual fact was correct; they
were being drawn from different dates and put in one column.

The fixtures below use the real EDGAR row shape, taken from live
companyfacts responses for AAPL, MSFT, NVDA and WMT.
"""

from unittest.mock import patch

from src.providers.vendors.sec_vendor import SECVendor, _is_annual


def _vendor() -> SECVendor:
    v = SECVendor()
    v._ticker_map = {"X": {"cik": "0000000001", "name": "X CORP"}}
    return v


def _facts(payload: dict) -> dict:
    return {"facts": {"us-gaap": payload}}


# ── defect 1: `fy` is the filing's year, not the fact's period ──────────────

def test_a_filing_contributes_several_periods_all_tagged_with_its_own_year():
    """Apple's FY2025 10-K, verbatim.

    It carries assets of 359.24B for period end 2025-09-27 and 364.98B for
    2024-09-28 — the comparative — and tags both `fy: 2025`. Keyed by `fy`
    the two collapse and whichever the JSON lists first wins, which for Apple
    was the prior year. "FY2025 total assets" was 2024's balance sheet.
    """
    v = _vendor()
    facts = _facts({"Assets": {"units": {"USD": [
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 359_243_000_000,
         "end": "2025-09-27", "filed": "2025-10-31"},
        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 364_980_000_000,
         "end": "2024-09-28", "filed": "2025-10-31"},
        {"fy": 2024, "fp": "FY", "form": "10-K", "val": 364_980_000_000,
         "end": "2024-09-28", "filed": "2024-11-01"},
    ]}}})
    with patch.object(SECVendor, "_get_json", return_value=facts):
        series = v.get_xbrl_facts("X")
    assets = series["Total assets"]
    assert [r["fiscal_year"] for r in assets] == [2025, 2024]
    by_year = {r["fiscal_year"]: r for r in assets}
    assert by_year[2025]["value"] == 359_243_000_000, (
        "the prior-year comparative was published as the current year"
    )
    assert by_year[2025]["period_end"] == "2025-09-27"
    assert by_year[2024]["value"] == 364_980_000_000


def test_the_accounting_identity_holds_when_periods_are_keyed_correctly():
    """Apple FY2025 and FY2024, as filed. A = L + E, exactly, both years."""
    v = _vendor()
    facts = _facts({
        "Assets": {"units": {"USD": [
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 359_243_000_000,
             "end": "2025-09-27", "filed": "2025-10-31"},
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 364_980_000_000,
             "end": "2024-09-28", "filed": "2025-10-31"},
        ]}},
        "Liabilities": {"units": {"USD": [
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 285_513_000_000,
             "end": "2025-09-27", "filed": "2025-10-31"},
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 308_030_000_000,
             "end": "2024-09-28", "filed": "2025-10-31"},
        ]}},
        "StockholdersEquity": {"units": {"USD": [
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 73_730_000_000,
             "end": "2025-09-27", "filed": "2025-10-31"},
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 56_950_000_000,
             "end": "2024-09-28", "filed": "2025-10-31"},
        ]}},
    })
    with patch.object(SECVendor, "_get_json", return_value=facts):
        s = v.get_xbrl_facts("X")

    A = {r["fiscal_year"]: r["value"] for r in s["Total assets"]}
    L = {r["fiscal_year"]: r["value"] for r in s["Total liabilities"]}
    E = {r["fiscal_year"]: r["value"] for r in s["Shareholders’ equity"]}
    for year in (2025, 2024):
        gap = abs(A[year] - (L[year] + E[year]))
        assert gap / A[year] < 1e-9, (
            f"FY{year} balance sheet is out by {gap:,.0f} — the three concepts "
            "are not drawn from one date"
        )


# ── defect 2: `fp: FY` includes the quarters ────────────────────────────────

def test_quarterly_rows_tagged_fp_fy_are_not_mistaken_for_the_year():
    """Apple's 2018 10-K, verbatim.

    Revenue of 265.60B for 2017-10-01→2018-09-29 and 62.90B for
    2018-07-01→2018-09-29 — both `fp: FY`, both `form: 10-K`, ending the same
    day. Keying on the end date alone understates the year by three quarters.
    """
    v = _vendor()
    facts = _facts({"Revenues": {"units": {"USD": [
        {"fy": 2018, "fp": "FY", "form": "10-K", "val": 265_595_000_000,
         "start": "2017-10-01", "end": "2018-09-29", "filed": "2018-11-05"},
        {"fy": 2018, "fp": "FY", "form": "10-K", "val": 62_900_000_000,
         "start": "2018-07-01", "end": "2018-09-29", "filed": "2018-11-05"},
        {"fy": 2018, "fp": "FY", "form": "10-K", "val": 53_265_000_000,
         "start": "2018-04-01", "end": "2018-06-30", "filed": "2018-11-05"},
    ]}}})
    with patch.object(SECVendor, "_get_json", return_value=facts):
        s = v.get_xbrl_facts("X")
    revenue = s["Revenue"]
    assert len(revenue) == 1, "a quarter was published as a year"
    assert revenue[0]["value"] == 265_595_000_000


def test_annual_spans_admit_fifty_two_and_fifty_three_week_years():
    """Real spans, from the filings. 52- and 53-week years both count."""
    for start, end, span, ok in (
        ("2017-10-01", "2018-09-29", 363, True),   # Apple, 52 weeks
        ("2016-09-25", "2017-09-30", 370, True),   # Apple, 53 weeks
        ("2025-07-01", "2026-06-30", 364, True),   # Microsoft, calendar-aligned
        ("2018-07-01", "2018-09-29", 90, False),   # Apple Q4
        ("2018-04-01", "2018-06-30", 90, False),   # Apple Q3
    ):
        assert _is_annual({"start": start, "end": end}) is ok, (
            f"a {span}-day span was classified wrongly"
        )


def test_a_period_ending_before_it_starts_is_rejected():
    """A negative span is malformed, not a long year."""
    assert _is_annual({"start": "2017-10-01", "end": "2017-09-30"}) is False


def test_a_balance_sheet_fact_has_no_start_and_is_always_annual():
    """An instant is a moment, not a span. It cannot be a quarter."""
    assert _is_annual({"end": "2025-09-27"}) is True
    assert _is_annual({"start": None, "end": "2025-09-27"}) is True


def test_a_malformed_date_is_excluded_rather_than_guessed():
    assert _is_annual({"start": "not-a-date", "end": "2025-09-27"}) is False


# ── defect 3: first alias with any data won ─────────────────────────────────

def test_the_alias_with_the_most_periods_wins_the_label():
    """Apple tagged `Revenues` once, in 2018, then moved tags.

    First-wins gave Apple a one-fact revenue series from 2018 and Microsoft
    one from 2010, while the tag carrying six years sat unused behind it.
    """
    v = _vendor()
    facts = _facts({
        "Revenues": {"units": {"USD": [
            {"fy": 2018, "fp": "FY", "form": "10-K", "val": 265_595_000_000,
             "start": "2017-10-01", "end": "2018-09-29", "filed": "2018-11-05"},
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"fy": y, "fp": "FY", "form": "10-K", "val": v_,
             "start": f"{y-1}-10-01", "end": f"{y}-09-28", "filed": f"{y}-11-01"}
            for y, v_ in ((2025, 416_161_000_000), (2024, 391_035_000_000),
                          (2023, 383_285_000_000))
        ]}},
    })
    with patch.object(SECVendor, "_get_json", return_value=facts):
        s = v.get_xbrl_facts("X")
    revenue = s["Revenue"]
    assert [r["fiscal_year"] for r in revenue] == [2025, 2024, 2023]
    assert revenue[0]["value"] == 416_161_000_000


def test_the_winning_tag_is_recorded_on_every_fact():
    """Which tag a series came from is part of what the number means.

    Two tags are not unioned even when that would lengthen the series: a
    column whose definition changes partway down is worse than a short one.
    """
    v = _vendor()
    facts = _facts({
        "Revenues": {"units": {"USD": [
            {"fy": 2018, "fp": "FY", "form": "10-K", "val": 1,
             "start": "2017-10-01", "end": "2018-09-29", "filed": "2018-11-05"},
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 2,
             "start": "2024-09-29", "end": "2025-09-27", "filed": "2025-10-31"},
            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 3,
             "start": "2023-10-01", "end": "2024-09-28", "filed": "2024-11-01"},
        ]}},
    })
    with patch.object(SECVendor, "_get_json", return_value=facts):
        s = v.get_xbrl_facts("X")
    tags = {r["concept_tag"] for r in s["Revenue"]}
    assert tags == {"RevenueFromContractWithCustomerExcludingAssessedTax"}, (
        "a single series was assembled from two different XBRL tags"
    )


def test_a_concept_the_filer_never_tagged_is_absent_rather_than_derived():
    """Walmart does not tag `Liabilities`. It is not inferred from the total.

    `LiabilitiesAndStockholdersEquity` is the balance sheet total — it equals
    assets by definition — and mapping it to "Total liabilities" would print
    a number 4x too large under a correct-looking label.
    """
    v = _vendor()
    facts = _facts({
        "Assets": {"units": {"USD": [
            {"fy": 2026, "fp": "FY", "form": "10-K", "val": 260_823_000_000,
             "end": "2026-01-31", "filed": "2026-03-01"},
        ]}},
        "LiabilitiesAndStockholdersEquity": {"units": {"USD": [
            {"fy": 2026, "fp": "FY", "form": "10-K", "val": 260_823_000_000,
             "end": "2026-01-31", "filed": "2026-03-01"},
        ]}},
    })
    with patch.object(SECVendor, "_get_json", return_value=facts):
        s = v.get_xbrl_facts("X")
    assert "Total liabilities" not in s
    assert s["Total assets"][0]["value"] == 260_823_000_000
