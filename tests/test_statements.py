"""Statement figures recovered from `vendor_metrics`, and the traps in doing it.

The figures were never missing. They arrive on every research request inside
`FundamentalsData.vendor_metrics` — 131 keys from Finnhub, 10 from yfinance —
and were dropped whole at the API boundary while `merge_fundamentals`
iterated fourteen field names that do not exist on the model.

Recovering them is only safe because every key is mapped to a concept, a
basis, a period, a unit and a scale. These pin the four traps that mapping
exists to defuse, each measured against live vendor responses for AAPL, MSFT,
NVDA and WMT rather than reasoned about.
"""

import math

import pytest

from src.providers import statements
from src.providers.schemas import FundamentalsData


# ── the schema defect that made this necessary ──────────────────────────────

def test_the_model_lacks_almost_every_field_the_merge_asks_for():
    """`merge_fundamentals` reads fourteen names off a model that has one.

    This is the defect, asserted so it cannot be quietly reintroduced by
    someone "cleaning up" the recovery path below. If `FundamentalsData` ever
    gains these fields the assertion fails and the recovery can be simplified
    — which is the right time to notice, not later.
    """
    from src.providers import fabric
    have = set(FundamentalsData.model_fields)
    present = [f for f in fabric._COMPARABLE_FUNDAMENTALS if f in have]
    assert present == ["eps"], (
        "FundamentalsData gained statement fields; merge_fundamentals can now "
        f"populate {present} directly and the vendor_metrics path may be revisited"
    )
    # The two keys that could never be filled either.
    assert "period" not in have
    assert "history" not in have


# ── trap 1: scale differs between vendors for one concept ───────────────────

def test_finnhub_company_totals_are_rescaled_from_millions():
    """Finnhub reports market cap and enterprise value in millions.

    Measured against yfinance's unit-scaled enterprise value the ratio is
    966,142 (AAPL), 996,663 (MSFT), 1,020,088 (NVDA) and 1,033,887 (WMT).
    Getting this wrong is a factor-of-a-million error that still looks like a
    plausible number, which is the worst kind.
    """
    facts = statements.normalise("finnhub", {
        "marketCapitalization": 4_811_261.5,
        "enterpriseValue": 4_856_061.5,
    })
    by = {f["concept"]: f for f in facts}
    assert by["Market capitalisation"]["value"] == pytest.approx(4.8112615e12)
    assert by["Enterprise value"]["value"] == pytest.approx(4.8560615e12)
    # The vendor's own number is kept beside the rescaled one, so a reader can
    # see that this product multiplied and by how much.
    assert by["Market capitalisation"]["vendor_value"] == 4_811_261.5
    assert by["Market capitalisation"]["scale"] == 1e6


def test_rescaling_makes_the_two_vendors_comparable_rather_than_absurd():
    """Same concept, two vendors, two scales — one group after normalisation."""
    facts = (statements.normalise("finnhub", {"enterpriseValue": 4_856_061.5})
             + statements.normalise("yfinance", {"enterprise_value": 4_691_644_645_376.0}))
    groups = statements.group(facts)
    assert len(groups) == 1, "the two enterprise values did not land in one group"
    g = groups[0]
    assert g["providers"] == ["finnhub", "yfinance"]
    # A real 3.5% disagreement between vendors — not a 10^6 unit error.
    assert g["spread_pct"] == pytest.approx(3.5, abs=0.2)
    assert g["agrees"] is False


# ── trap 2: basis differs between vendors for one concept ───────────────────

def test_revenue_per_share_is_never_grouped_with_revenue_in_dollars():
    """Both are "Revenue". Their difference is meaningless.

    Finnhub reports 31.725 per share TTM; yfinance reports 466,822,987,776
    absolute. Their ratio is the share count. Differencing them is the error.
    """
    facts = (statements.normalise("finnhub", {"revenuePerShareTTM": 31.725})
             + statements.normalise("yfinance", {"total_revenue": 466_822_987_776.0}))
    groups = statements.group(facts)
    assert len(groups) == 2, "a per-share figure was pooled with an absolute one"
    bases = sorted(g["basis"] for g in groups)
    assert bases == ["per share", "total"]
    # Neither group claims agreement: each holds a single observation.
    for g in groups:
        assert g["agrees"] is None
        assert g["spread_pct"] is None


# ── trap 3: one vendor's dictionary mixes bases with no marker ──────────────

def test_yfinance_book_value_is_mapped_per_share_despite_its_name():
    """`book_value` sits beside `total_revenue` and is not a total.

    7.36 for AAPL against Finnhub's explicitly-named
    `bookValuePerShareQuarterly` of 7.3599; 59.565 against 59.5647 for MSFT;
    9.483 against 9.4829 for NVDA. Mapping it as a company total would print
    a seven-dollar number in a column of hundred-billion-dollar ones and call
    it Apple's equity.
    """
    fact = statements.normalise("yfinance", {"book_value": 7.36})[0]
    assert fact["basis"] == statements.PER_SHARE
    assert fact["unit"] == "currency/share"
    assert fact["value"] == 7.36, "a per-share figure was rescaled"


def test_a_per_share_and_a_total_from_one_vendor_stay_apart():
    groups = statements.group(statements.normalise("yfinance", {
        "book_value": 7.36, "total_revenue": 466_822_987_776.0,
    }))
    assert {g["basis"] for g in groups} == {"per share", "total"}


# ── trap 4: unmapped keys are dropped, never guessed ────────────────────────

def test_ratios_and_percentages_in_the_metric_bag_are_not_surfaced():
    """`ebitda` is currency and `ebitda_margins` is a percentage, in one dict.

    Only the mapped key survives. An unmapped number is one whose unit, basis
    and period nobody has established, and rendering it beside currency is how
    a 35.979 becomes thirty-six dollars.
    """
    facts = statements.normalise("yfinance", {
        "ebitda": 167_959_003_136.0,
        "ebitda_margins": 35.979,
        "peg_ratio": 2.5546,
    })
    assert [f["concept"] for f in facts] == ["EBITDA"]
    assert facts[0]["value"] == pytest.approx(1.67959003136e11)


def test_an_unknown_vendor_yields_nothing_rather_than_raw_passthrough():
    assert statements.normalise("some-new-vendor", {"revenue": 1.0}) == []


# ── periods ─────────────────────────────────────────────────────────────────

def test_finnhub_periods_come_from_its_own_key_names():
    facts = statements.normalise("finnhub", {
        "revenuePerShareAnnual": 27.7354,
        "revenuePerShareTTM": 31.725,
        "cashFlowPerShareQuarterly": 9.3561,
    })
    got = {(f["concept"], f["period"]): f["value"] for f in facts}
    assert got[("Revenue", "FY")] == 27.7354
    assert got[("Revenue", "TTM")] == 31.725
    assert got[("Operating cash flow", "MRQ")] == 9.3561


def test_annual_and_trailing_revenue_are_different_measurements():
    """27.74 and 31.73 are both correct and are not the same number."""
    groups = statements.group(statements.normalise("finnhub", {
        "revenuePerShareAnnual": 27.7354, "revenuePerShareTTM": 31.725,
    }))
    assert len(groups) == 2, "a fiscal-year figure was pooled with a trailing one"
    assert {g["period"] for g in groups} == {"FY", "TTM"}


def test_an_unstated_period_is_not_treated_as_matching_a_stated_one():
    """yfinance names no period. Silence is not a wildcard.

    Its book value of 7.36 equals Finnhub's MRQ book value of 7.36 to the
    cent, and they are still kept apart — resembling a quarterly figure is
    not evidence of being one.
    """
    groups = statements.group(
        statements.normalise("finnhub", {"bookValuePerShareQuarterly": 7.3599})
        + statements.normalise("yfinance", {"book_value": 7.36}))
    assert len(groups) == 2, "an unlabelled period was matched to a stated one"
    assert sorted(g["period"] for g in groups) == ["", "MRQ"]


# ── agreement is only claimed where it was measured ─────────────────────────

def test_one_observation_reports_no_agreement_rather_than_perfect_agreement():
    g = statements.group(statements.normalise("finnhub", {"epsTTM": 8.7233}))[0]
    assert g["agrees"] is None, "a lone vendor was recorded as agreeing with itself"
    assert g["spread_pct"] is None, "a spread was computed from one observation"


def test_two_vendors_within_a_percent_agree():
    facts = (statements.normalise("finnhub", {"enterpriseValue": 4_700_000.0})
             + statements.normalise("yfinance", {"enterprise_value": 4_700_000_000_000.0}))
    g = statements.group(facts)[0]
    assert g["agrees"] is True
    assert g["spread_pct"] == pytest.approx(0.0, abs=0.01)


# ── junk in the metric bag ──────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [None, "n/a", True, False, float("nan")])
def test_non_numeric_and_boolean_metrics_are_dropped(bad):
    """`True` is an int in Python. It is not a book value."""
    facts = statements.normalise("yfinance", {"total_revenue": bad})
    assert facts == []


def test_empty_metrics_yield_no_facts():
    assert statements.normalise("finnhub", None) == []
    assert statements.normalise("finnhub", {}) == []
    assert statements.group([]) == []
