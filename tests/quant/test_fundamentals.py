"""
Statement fundamentals — the tests are almost entirely about the gate.

The value of these features is unremarkable; the danger is not. A fiscal period
end is not an availability date, and a pipeline that forgets this reads a
quarter's results a month before they were published. Every test here is aimed
at that, plus the two degenerate cases (no announcement, restated-shape input)
where the correct answer is NULL rather than a number.
"""

from __future__ import annotations

from datetime import date as Date

import numpy as np
import pandas as pd
import pytest

from src.quant.features.fundamentals import (
    FEATURE_NAMES,
    MAX_ANNOUNCEMENT_LAG_DAYS,
    RESTATEMENT_NOTE,
    attach_fundamental_features,
    build_fundamental_events,
)
from src.quant.features.registry import REGISTRY


def _income(rows):
    return pd.DataFrame(
        rows, columns=["symbol", "date", "sales", "gross_profit", "pretax_income", "net_income"]
    ).assign(period="Quarter")


def _equity(rows):
    return pd.DataFrame(
        rows, columns=["symbol", "date", "total_equity", "shares_outstanding"]
    ).assign(period="Quarter")


def _assets(rows):
    return pd.DataFrame(
        rows, columns=["symbol", "date", "total_assets", "total_current_assets"]
    ).assign(period="Quarter")


def _calendar(rows):
    return pd.DataFrame(rows, columns=["symbol", "date"])


# ── the gate ────────────────────────────────────────────────────────────────


def test_availability_is_the_announcement_never_the_period_end():
    """The whole module exists for this assertion."""
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8)])
    calendar = _calendar([("AAA", "2025-04-30")])

    events = build_fundamental_events(income, None, None, None, None, calendar)

    assert len(events) == 1
    assert pd.Timestamp(events["available_from"].iloc[0]) == pd.Timestamp("2025-04-30")
    assert pd.Timestamp(events["period_end_date"].iloc[0]) == pd.Timestamp("2025-03-31")
    assert events["available_from"].iloc[0] > events["period_end_date"].iloc[0]


def test_a_period_with_no_announcement_is_dropped_not_estimated():
    """No conventional 45-day assumption. No announcement, no feature."""
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8)])
    events = build_fundamental_events(income, None, None, None, None, _calendar([]))
    assert events.empty


def test_an_announcement_before_the_period_end_is_refused():
    """An 'announcement' preceding the period it reports cannot be the right one."""
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8)])
    calendar = _calendar([("AAA", "2025-01-15")])
    assert build_fundamental_events(income, None, None, None, None, calendar).empty


def test_an_implausibly_late_announcement_is_refused():
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8)])
    late = (pd.Timestamp("2025-03-31") + pd.Timedelta(days=MAX_ANNOUNCEMENT_LAG_DAYS + 30)).date()
    calendar = _calendar([("AAA", late.isoformat())])
    assert build_fundamental_events(income, None, None, None, None, calendar).empty


def test_the_panel_never_sees_a_figure_before_its_announcement():
    """The end-to-end assertion: a row dated between period end and announcement
    must carry NULL, not the quarter's numbers."""
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8)])
    calendar = _calendar([("AAA", "2025-04-30")])
    events = build_fundamental_events(income, None, None, None, None, calendar)

    panel = pd.DataFrame({
        "symbol": ["AAA", "AAA", "AAA"],
        "date": [Date(2025, 4, 1), Date(2025, 4, 29), Date(2025, 5, 1)],
    })
    attached = attach_fundamental_features(panel, events)

    assert np.isnan(attached["fund_gross_margin"].iloc[0]), "read before the period was announced"
    assert np.isnan(attached["fund_gross_margin"].iloc[1]), "read the day before announcement"
    assert attached["fund_gross_margin"].iloc[2] == pytest.approx(0.4), "not readable after announcement"


def test_the_first_announcement_at_or_after_is_chosen_not_the_nearest():
    """Two candidate announcements: the earlier one that still follows wins."""
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8)])
    calendar = _calendar([("AAA", "2025-04-30"), ("AAA", "2025-07-30")])
    events = build_fundamental_events(income, None, None, None, None, calendar)
    assert pd.Timestamp(events["available_from"].iloc[0]) == pd.Timestamp("2025-04-30")


# ── growth needs a comparable prior period ──────────────────────────────────


def test_year_over_year_growth_requires_a_real_year_gap():
    """A filer with missing quarters must not compare across an arbitrary span."""
    # Five quarters, but the 4-back neighbour of the last is 4 years earlier.
    dates = ["2021-03-31", "2022-03-31", "2023-03-31", "2024-03-31", "2025-03-31"]
    income = _income([("AAA", d, 1e9, 4e8, 2e8, 1.5e8) for d in dates])
    assets = _assets([("AAA", d, 5e9, 2e9) for d in dates])
    calendar = _calendar([("AAA", (pd.Timestamp(d) + pd.Timedelta(days=30)).date().isoformat())
                          for d in dates])

    events = build_fundamental_events(income, assets, None, None, None, calendar)
    assert events["fund_asset_growth_yoy"].isna().all(), (
        "growth was computed across a four-year span"
    )


def test_year_over_year_growth_is_reported_on_consecutive_quarters():
    dates = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"]
    income = _income([("AAA", d, 1e9, 4e8, 2e8, 1.5e8) for d in dates])
    assets = _assets([("AAA", d, a, 2e9) for d, a in
                      zip(dates, [5e9, 5e9, 5e9, 5e9, 6e9])])
    calendar = _calendar([("AAA", (pd.Timestamp(d) + pd.Timedelta(days=30)).date().isoformat())
                          for d in dates])

    events = build_fundamental_events(income, assets, None, None, None, calendar)
    last = events.sort_values("period_end_date").iloc[-1]
    assert last["fund_asset_growth_yoy"] == pytest.approx(0.2)


# ── degenerate inputs ───────────────────────────────────────────────────────


def test_a_zero_denominator_gives_null_not_infinity():
    income = _income([("AAA", "2025-03-31", 0.0, 4e8, 2e8, 1.5e8)])
    calendar = _calendar([("AAA", "2025-04-30")])
    events = build_fundamental_events(income, None, None, None, None, calendar)
    assert np.isnan(events["fund_gross_margin"].iloc[0])


def test_absent_sources_leave_nulls_not_zeros():
    panel = pd.DataFrame({"symbol": ["AAA"], "date": [Date(2025, 5, 1)]})
    attached = attach_fundamental_features(panel, pd.DataFrame())
    for name in FEATURE_NAMES:
        assert name in attached.columns
        assert attached[name].isna().all(), f"{name} was zero-filled"


def test_attach_preserves_row_count_and_order():
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8),
                      ("BBB", "2025-03-31", 2e9, 6e8, 3e8, 2e8)])
    calendar = _calendar([("AAA", "2025-04-30"), ("BBB", "2025-04-25")])
    events = build_fundamental_events(income, None, None, None, None, calendar)

    panel = pd.DataFrame({
        "symbol": ["BBB", "AAA", "BBB", "AAA"],
        "date": [Date(2025, 5, 2), Date(2025, 5, 2), Date(2025, 4, 26), Date(2025, 4, 26)],
    })
    attached = attach_fundamental_features(panel, events)
    assert len(attached) == len(panel)
    assert attached["symbol"].tolist() == panel["symbol"].tolist()
    # BBB announced 04-25, AAA 04-30: on 04-26 only BBB is readable.
    assert not np.isnan(attached["fund_gross_margin"].iloc[2])
    assert np.isnan(attached["fund_gross_margin"].iloc[3])


def test_symbols_do_not_bleed_across_the_gate():
    income = _income([("AAA", "2025-03-31", 1e9, 4e8, 2e8, 1.5e8),
                      ("BBB", "2025-03-31", 2e9, 1.8e9, 3e8, 2e8)])
    calendar = _calendar([("AAA", "2025-04-30"), ("BBB", "2025-04-30")])
    events = build_fundamental_events(income, None, None, None, None, calendar)
    by_symbol = events.set_index("symbol")["fund_gross_margin"]
    assert by_symbol["AAA"] == pytest.approx(0.4)
    assert by_symbol["BBB"] == pytest.approx(0.9)


# ── the caveat must travel with the features ────────────────────────────────


def test_every_fundamental_feature_declares_its_restatement_risk():
    """The limitation has to be on the feature, not only in a docstring.

    These features are admissible because of the announcement gate. They are NOT
    clean: a restatement overwrites history irrecoverably, and any promotion
    decision that leans on them has to see that.
    """
    for name in FEATURE_NAMES:
        definition = REGISTRY.get(name)
        notes = " ".join(definition.notes)
        assert RESTATEMENT_NOTE in notes, f"{name} does not declare restatement risk"
        assert "UNQUANTIFIED" in notes, f"{name} implies the risk has been measured"
        assert "Announcement-gated" in notes, f"{name} does not declare its gate"


# ── the rank transform is what makes wild ratios safe ───────────────────────


def test_raw_ratios_may_be_extreme_but_the_rank_is_bounded():
    """A near-zero equity base gives a debt/equity of several hundred.

    That value is *correct* — the firm really is levered that way — and
    winsorising it in the feature would destroy information about the ordering.
    What protects the model is that it never sees the raw number: features are
    consumed as cross-sectional ranks, which are bounded by construction.

    Measured on the real 2023 panel, `fund_debt_to_equity` spans -719 to +796
    while every `_xs` column the models consume sits within [-1, 1]. This test
    asserts the mechanism on a constructed extreme so the guarantee does not
    depend on that particular panel.
    """
    from src.quant.features import cross_section as xs

    # MIN_NAMES_PER_DATE is 10: a rank over fewer names is not a cross-section,
    # so the panel needs at least that many for the transform to produce anything.
    symbols = [f"S{i:02d}" for i in range(12)]
    income = _income([(s, "2025-03-31", 1e9, 4e8, 2e8, 1.5e8) for s in symbols])
    liabilities = pd.DataFrame(
        [(s, "2025-03-31", 5e11 if s == "S01" else 1e9) for s in symbols],
        columns=["symbol", "date", "total_liabilities"],
    ).assign(period="Quarter")
    equity = _equity([
        # S01 has near-zero equity, giving an enormous ratio; the rest are ordinary.
        (s, "2025-03-31", 1.1e6 if s == "S01" else 1e9 + 1e8 * i, 1e8)
        for i, s in enumerate(symbols)
    ])
    calendar = _calendar([(s, "2025-04-30") for s in symbols])

    events = build_fundamental_events(income, None, liabilities, equity, None, calendar)
    raw = events.set_index("symbol")["fund_debt_to_equity"]
    assert raw["S01"] > 1000, "the constructed extreme did not materialise"

    panel = pd.DataFrame({
        "symbol": symbols,
        "date": [Date(2025, 5, 1)] * len(symbols),
        "in_universe": True,
    })
    attached = attach_fundamental_features(panel, events)
    ranked = xs.cross_sectional_frame(
        attached, ["fund_debt_to_equity"],
        universe_for={Date(2025, 5, 1): tuple(symbols)}, method="rank",
    )
    values = ranked["fund_debt_to_equity_xs"].dropna()
    assert not values.empty
    assert values.abs().max() <= 1.0, "a rank escaped [-1, 1]"
