"""
Analyst estimate revisions — the tests assert the traps, not the happy path.

Two failure modes would each manufacture signal out of bookkeeping:

1. **Fiscal rollover.** 'Current Year' points at a different period after a
   fiscal year end, so differencing across that boundary reports an enormous
   revision that nobody made — on a predictable calendar a tree model will fit.
2. **Forward reach.** An as-of attach that used `direction="forward"`, or a
   sort that let `shift` reach later vintages, would read next week's consensus
   into this week's row.

Both are asserted directly rather than inferred from an aggregate.
"""

from __future__ import annotations

from datetime import date as Date

import numpy as np
import pandas as pd
import pytest

from src.quant.features.estimates import (
    FEATURE_NAMES,
    MAX_VINTAGE_AGE_DAYS,
    MIN_ABS_CONSENSUS,
    attach_estimate_features,
    build_estimate_features,
)


def _vintages(rows: list[tuple[str, str, str, float, int, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["symbol", "date", "period_end_date", "consensus", "count", "high", "low", "year_ago"],
    ).assign(period="Current Year")


def _weekly(symbol: str, start: str, weeks: int, consensus, period_end: str = "2025-12-31"):
    dates = pd.date_range(start, periods=weeks, freq="7D")
    values = consensus if isinstance(consensus, list) else [consensus] * weeks
    return _vintages([
        (symbol, d.date().isoformat(), period_end, v, 9, v + 0.2, v - 0.2, 1.0)
        for d, v in zip(dates, values)
    ])


# ── the rollover trap ───────────────────────────────────────────────────────


def test_revision_is_null_across_a_fiscal_rollover():
    """A change of period is not a revision, and must not be reported as one."""
    # 13 weeks on FY2025 at 2.00, then 13 weeks on FY2026 at 5.00. The 5.00 is a
    # different question, not a 150% upgrade.
    before = _weekly("AAA", "2025-01-05", 13, 2.00, period_end="2025-12-31")
    after = _weekly("AAA", "2025-04-06", 13, 5.00, period_end="2026-12-31")
    frame = pd.concat([before, after], ignore_index=True)

    built = build_estimate_features(frame, None)
    rolled = built[built["available_from"] >= pd.Timestamp("2025-04-06")]

    assert not rolled.empty
    # Every row whose 4-week-prior vintage sat on the OLD period must be NULL.
    first_four = rolled.head(4)
    assert first_four["est_eps_rev_4w"].isna().all(), (
        "a fiscal rollover was reported as a revision"
    )


def test_revision_is_reported_within_a_stable_period():
    """The guard must not suppress genuine revisions."""
    values = [2.00] * 5 + [2.20] * 8
    frame = _weekly("AAA", "2025-01-05", 13, values, period_end="2025-12-31")
    built = build_estimate_features(frame, None)

    revised = built.dropna(subset=["est_eps_rev_4w"])
    assert not revised.empty
    assert revised["est_eps_rev_4w"].max() == pytest.approx(0.10, abs=1e-9)


# ── no forward reach ────────────────────────────────────────────────────────


def test_revision_never_uses_a_later_vintage():
    """A downgrade that happens in week 10 must be invisible in week 5."""
    values = [2.00] * 9 + [1.00] * 4
    frame = _weekly("AAA", "2025-01-05", 13, values)
    built = build_estimate_features(frame, None).sort_values("available_from")

    early = built[built["available_from"] < pd.Timestamp("2025-03-09")]
    assert early["est_eps_rev_4w"].fillna(0.0).abs().max() == pytest.approx(0.0), (
        "a later downgrade leaked backward into earlier vintages"
    )


def test_shuffled_input_gives_identical_output():
    """Ordering must not change a value; the sort inside must own correctness."""
    frame = _weekly("AAA", "2025-01-05", 13, [2.0 + 0.05 * i for i in range(13)])
    frame = pd.concat([frame, _weekly("BBB", "2025-01-05", 13, 3.0)], ignore_index=True)

    ordered = build_estimate_features(frame, None)
    shuffled = build_estimate_features(
        frame.sample(frac=1.0, random_state=7).reset_index(drop=True), None
    )
    key = ["symbol", "available_from"]
    pd.testing.assert_frame_equal(
        ordered.sort_values(key).reset_index(drop=True),
        shuffled.sort_values(key).reset_index(drop=True),
    )


def test_symbols_do_not_bleed_into_each_other():
    """AAA's revisions must not be computed from BBB's rows."""
    aaa = _weekly("AAA", "2025-01-05", 13, 2.00)
    bbb = _weekly("BBB", "2025-01-05", 13, [1.0 + i for i in range(13)])
    built = build_estimate_features(pd.concat([aaa, bbb], ignore_index=True), None)

    a_rev = built[built["symbol"] == "AAA"]["est_eps_rev_4w"].dropna()
    assert (a_rev.abs() < 1e-12).all(), "a flat symbol picked up its neighbour's revisions"


# ── attach is backward-only ─────────────────────────────────────────────────


def _panel(symbol: str, dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"symbol": symbol, "date": [Date.fromisoformat(d) for d in dates]})


def test_attach_never_reads_a_future_vintage():
    frame = _weekly("AAA", "2025-01-05", 6, [1.0, 1.0, 1.0, 1.0, 9.0, 9.0])
    built = build_estimate_features(frame, None)
    # 2025-01-20 sits before the 9.0 vintages (2025-02-02 onward).
    panel = _panel("AAA", ["2025-01-20"])
    attached = attach_estimate_features(panel, built)
    assert attached["est_eps_coverage"].notna().all()
    # The value carried must be the vintage at or before the date, never after.
    assert attached["est_eps_growth_expected"].iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_a_stale_vintage_is_null_rather_than_carried_forever():
    frame = _weekly("AAA", "2025-01-05", 2, 2.00)
    built = build_estimate_features(frame, None)
    panel = _panel("AAA", ["2025-06-01"])  # ~19 weeks after the last vintage
    attached = attach_estimate_features(panel, built, max_age_days=MAX_VINTAGE_AGE_DAYS)
    for name in FEATURE_NAMES:
        assert attached[name].isna().all(), f"{name} carried a stale vintage"


def test_absent_estimates_leave_nulls_not_zeros():
    panel = _panel("AAA", ["2025-01-20"])
    attached = attach_estimate_features(panel, pd.DataFrame())
    for name in FEATURE_NAMES:
        assert name in attached.columns
        assert attached[name].isna().all(), f"{name} was zero-filled instead of NULL"


def test_attach_preserves_row_count_and_order():
    frame = _weekly("AAA", "2025-01-05", 6, 2.0)
    frame = pd.concat([frame, _weekly("BBB", "2025-01-05", 6, 3.0)], ignore_index=True)
    built = build_estimate_features(frame, None)
    panel = pd.concat([
        _panel("BBB", ["2025-02-03", "2025-01-20"]),
        _panel("AAA", ["2025-01-20", "2025-02-03"]),
    ], ignore_index=True)
    attached = attach_estimate_features(panel, built)
    assert len(attached) == len(panel)
    assert attached["symbol"].tolist() == panel["symbol"].tolist()
    assert attached["date"].tolist() == panel["date"].tolist()


# ── degenerate denominators ─────────────────────────────────────────────────


def test_a_near_zero_consensus_gives_null_not_a_huge_number():
    """Break-even names are real; their percentage revision is not meaningful.

    The guard is on the DENOMINATOR — the vintage being differenced against. A
    move from 0.005 to 0.25 is a 4,900% "revision" that says nothing except that
    the base was noise, so those rows are NULL. Once the base is above the floor
    the revision is reported normally, which the second half asserts so the
    guard cannot pass by suppressing everything.
    """
    tiny = MIN_ABS_CONSENSUS / 10.0        # 0.005 — below the floor
    solid = MIN_ABS_CONSENSUS * 5.0        # 0.25  — above it
    values = [tiny] * 5 + [solid] * 8
    frame = _weekly("AAA", "2025-01-05", 13, values)
    built = build_estimate_features(frame, None).sort_values("available_from")

    revisions = built["est_eps_rev_4w"].to_numpy()
    # Rows 5-8 difference against a 0.005 base: refused.
    assert np.isnan(revisions[5:9]).all(), (
        "a near-zero denominator produced a revision instead of NULL"
    )
    # Rows 9-12 difference 0.25 against 0.25: reported, and flat.
    assert not np.isnan(revisions[9:]).any(), "a valid denominator was suppressed"
    assert revisions[9:] == pytest.approx(0.0, abs=1e-12)


def test_empty_input_returns_empty_not_an_exception():
    assert build_estimate_features(None, None).empty
    assert build_estimate_features(pd.DataFrame(), None).empty


def test_absent_period_returns_empty():
    frame = _weekly("AAA", "2025-01-05", 4, 2.0).assign(period="Next Quarter")
    assert build_estimate_features(frame, None).empty
