"""
Earnings and options features — the point-in-time joins that make them usable.

The earnings tests exist because `eps_history` on its own is a leak. It is
keyed by `period_end_date` with no announcement date, and the measured gap on
AAPL is 30 days: the quarter ending 2026-06-30 became public on 2026-07-30.
Every test below is about closing that gap and proving it stays closed.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant.features.earnings import (
    MAX_SURPRISE_AGE_SESSIONS,
    attach_earnings_features,
    build_earnings_events,
)
from src.quant.features.options import (
    MAX_STALENESS_DAYS,
    attach_option_features,
    build_option_features,
)


# ── earnings ────────────────────────────────────────────────────────────────


@pytest.fixture
def eps_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * 6,
            "period_end_date": [
                Date(2023, 3, 31), Date(2023, 6, 30), Date(2023, 9, 30),
                Date(2023, 12, 31), Date(2024, 3, 31), Date(2024, 6, 30),
            ],
            "reported": [1.00, 1.10, 1.05, 1.30, 1.20, 1.40],
            "estimate": [1.00, 1.00, 1.10, 1.20, 1.20, 1.25],
        }
    )


@pytest.fixture
def earnings_calendar() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * 6,
            "date": [
                Date(2023, 4, 28), Date(2023, 7, 28), Date(2023, 10, 27),
                Date(2024, 1, 26), Date(2024, 4, 26), Date(2024, 7, 26),
            ],
            "when": [
                "After market close", "Before market open", "After market close",
                "After market close", "Before market open", None,
            ],
        }
    )


def test_events_match_each_period_to_its_announcement(eps_history, earnings_calendar):
    events = build_earnings_events(eps_history, earnings_calendar)
    assert len(events) == 6
    first = events.iloc[0]
    assert first["period_end_date"] == pd.Timestamp(2023, 3, 31)
    assert first["announcement_date"] == pd.Timestamp(2023, 4, 28)
    assert first["report_lag_days"] == 28


def test_after_close_prints_are_available_the_next_day(eps_history, earnings_calendar):
    """The session rule. Treating an after-close print as same-day tradeable
    grants a free session of foresight on roughly half of all prints."""
    events = build_earnings_events(eps_history, earnings_calendar).set_index("period_end_date")

    after_close = events.loc[pd.Timestamp(2023, 3, 31)]
    assert (after_close["available_from"] - after_close["announcement_date"]).days == 1

    before_open = events.loc[pd.Timestamp(2023, 6, 30)]
    assert (before_open["available_from"] - before_open["announcement_date"]).days == 0


def test_missing_session_marker_is_treated_conservatively(eps_history, earnings_calendar):
    """Unknown `when` must assume after-close, the later of the two."""
    events = build_earnings_events(eps_history, earnings_calendar).set_index("period_end_date")
    unknown = events.loc[pd.Timestamp(2024, 6, 30)]
    assert (unknown["available_from"] - unknown["announcement_date"]).days == 1


def test_a_period_with_no_announcement_is_dropped_not_estimated(eps_history):
    """Backfilling an average reporting lag would reintroduce the exact leak
    the calendar join exists to close."""
    empty = pd.DataFrame({"symbol": [], "date": [], "when": []})
    assert build_earnings_events(eps_history, empty).empty


def test_sue_uses_only_prior_surprises(eps_history, earnings_calendar):
    """The denominator must not contain the surprise it is scaling."""
    events = build_earnings_events(eps_history, earnings_calendar)
    # The first four periods cannot have SUE — fewer than MIN_SUE_HISTORY priors.
    assert events["sue"].head(4).isna().all()
    assert events["sue"].tail(1).notna().any()


def test_surprise_is_null_when_the_estimate_is_near_zero():
    history = pd.DataFrame(
        {"symbol": ["AAA"], "period_end_date": [Date(2023, 3, 31)],
         "reported": [0.05], "estimate": [0.001]}
    )
    calendar = pd.DataFrame(
        {"symbol": ["AAA"], "date": [Date(2023, 4, 28)], "when": ["Before market open"]}
    )
    events = build_earnings_events(history, calendar)
    assert pd.isna(events["surprise_pct"].iloc[0])


def test_attached_features_never_precede_availability(eps_history, earnings_calendar):
    """The point-in-time property, asserted directly."""
    events = build_earnings_events(eps_history, earnings_calendar)
    dates = [Date(2023, 4, 1) + timedelta(days=i * 7) for i in range(60)]
    panel = pd.DataFrame({"date": dates, "symbol": "AAA"})

    attached = attach_earnings_features(panel, events)
    first_available = events["available_from"].min().date()
    before = attached[attached["date"] < first_available]
    assert before["earn_surprise_pct"].isna().all()
    after = attached[attached["date"] >= first_available]
    assert after["earn_surprise_pct"].notna().any()


def test_a_stale_surprise_becomes_null_rather_than_carrying_forever(
    eps_history, earnings_calendar
):
    events = build_earnings_events(eps_history, earnings_calendar)
    last = events["available_from"].max().date()
    panel = pd.DataFrame(
        {"date": [last + timedelta(days=400)], "symbol": ["AAA"]}
    )
    attached = attach_earnings_features(panel, events)
    assert pd.isna(attached["earn_surprise_pct"].iloc[0])


def test_absent_events_leave_features_null_not_zero():
    panel = pd.DataFrame({"date": [Date(2024, 1, 2)], "symbol": ["AAA"]})
    attached = attach_earnings_features(panel, pd.DataFrame())
    assert pd.isna(attached["earn_surprise_pct"].iloc[0])
    assert pd.isna(attached["earn_sue"].iloc[0])


# ── options ─────────────────────────────────────────────────────────────────


@pytest.fixture
def volatility_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [Date(2024, 1, 5), Date(2024, 1, 12)],
            "symbol": ["AAA", "AAA"],
            "iv_current": [0.30, 0.36],
            "hv_current": [0.25, 0.24],
            "iv_year_high": [0.50, 0.50],
            "iv_year_low": [0.20, 0.20],
            "iv_month_ago": [0.28, 0.30],
        }
    )


@pytest.fixture
def chain_daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [Date(2024, 1, 5), Date(2024, 1, 12)],
            "symbol": ["AAA", "AAA"],
            "atm_iv": [0.30, 0.36],
            "put_25_iv": [0.36, 0.45],
            "call_25_iv": [0.27, 0.30],
            "atm_iv_near": [0.32, 0.40],
            "atm_iv_far": [0.28, 0.34],
            "rel_spread": [0.05, 0.07],
            "expirations": [6, 6],
        }
    )


def test_iv_premium_and_rank_are_computed_from_the_snapshot(volatility_history):
    features = build_option_features(volatility_history, None)
    first = features.iloc[0]
    assert first["opt_iv_minus_hv"] == pytest.approx(0.30 / 0.25 - 1)
    assert first["opt_iv_rank"] == pytest.approx((0.30 - 0.20) / (0.50 - 0.20))


def test_skew_is_normalised_by_atm(chain_daily):
    """A 5-point skew on 20% IV is not a 5-point skew on 80% IV."""
    features = build_option_features(None, chain_daily)
    assert features.iloc[0]["opt_skew_25d"] == pytest.approx((0.36 - 0.27) / 0.30)


def test_term_slope_is_far_over_near(chain_daily):
    features = build_option_features(None, chain_daily)
    assert features.iloc[0]["opt_term_slope"] == pytest.approx(0.28 / 0.32 - 1)


def test_absurd_iv_is_rejected_not_clipped():
    frame = pd.DataFrame(
        {"date": [Date(2024, 1, 5)], "symbol": ["AAA"], "iv_current": [42.0],
         "hv_current": [0.25], "iv_year_high": [0.5], "iv_year_low": [0.2],
         "iv_month_ago": [0.3]}
    )
    features = build_option_features(frame, None)
    assert pd.isna(features.iloc[0]["opt_iv"])


def test_attach_uses_the_latest_snapshot_at_or_before_the_date(
    volatility_history, chain_daily
):
    """Backward as-of. `nearest` would match a Monday to Tuesday's snapshot."""
    features = build_option_features(volatility_history, chain_daily)
    panel = pd.DataFrame(
        {"date": [Date(2024, 1, 8), Date(2024, 1, 15)], "symbol": ["AAA", "AAA"]}
    )
    attached = attach_option_features(panel, features)
    # 8 Jan sees the 5 Jan snapshot, not the 12 Jan one.
    assert attached["opt_iv"].iloc[0] == pytest.approx(0.30)
    assert attached["opt_iv"].iloc[1] == pytest.approx(0.36)


def test_a_date_before_any_snapshot_gets_null(volatility_history):
    features = build_option_features(volatility_history, None)
    panel = pd.DataFrame({"date": [Date(2023, 1, 1)], "symbol": ["AAA"]})
    assert pd.isna(attach_option_features(panel, features)["opt_iv"].iloc[0])


def test_stale_snapshots_are_dropped_beyond_the_cap(volatility_history):
    features = build_option_features(volatility_history, None)
    stale = Date(2024, 1, 12) + timedelta(days=MAX_STALENESS_DAYS + 5)
    panel = pd.DataFrame({"date": [stale], "symbol": ["AAA"]})
    assert pd.isna(attach_option_features(panel, features)["opt_iv"].iloc[0])


def test_absent_option_sources_leave_features_null_not_zero():
    panel = pd.DataFrame({"date": [Date(2024, 1, 2)], "symbol": ["AAA"]})
    attached = attach_option_features(panel, pd.DataFrame())
    assert pd.isna(attached["opt_iv"].iloc[0])


def test_option_features_do_not_depend_on_future_snapshots(volatility_history):
    """Appending a later snapshot must not change an earlier row."""
    features = build_option_features(volatility_history, None)
    panel = pd.DataFrame({"date": [Date(2024, 1, 8)], "symbol": ["AAA"]})
    before = attach_option_features(panel, features)["opt_iv"].iloc[0]

    extended = pd.concat([
        volatility_history,
        pd.DataFrame({
            "date": [Date(2024, 6, 1)], "symbol": ["AAA"], "iv_current": [0.99],
            "hv_current": [0.25], "iv_year_high": [1.0], "iv_year_low": [0.2],
            "iv_month_ago": [0.3],
        }),
    ], ignore_index=True)
    after = attach_option_features(
        panel, build_option_features(extended, None)
    )["opt_iv"].iloc[0]
    assert before == pytest.approx(after)


# ── as-of alignment regression ──────────────────────────────────────────────
#
# These exist because the original tests above PASSED while the join was
# broken. They used a single symbol whose rows were already in date order, so a
# date-sort was the identity and the misalignment was invisible. The panel the
# builder actually produces is SYMBOL-MAJOR and multi-symbol, where sorting by
# date permutes every row.


def _interleaved_panel() -> pd.DataFrame:
    """Symbol-major, multi-symbol — the shape the builder really emits."""
    rows = []
    for symbol in ("AAA", "BBB", "CCC"):
        for offset in range(8):
            rows.append({"date": Date(2024, 1, 5) + timedelta(days=7 * offset), "symbol": symbol})
    return pd.DataFrame(rows)


def test_asof_option_join_aligns_to_the_original_row_order():
    """Each row must receive ITS OWN symbol's snapshot, not a positional neighbour.

    `pandas.merge_asof` discards the left index and returns a fresh RangeIndex,
    so `sort_index()` on the result is a no-op and `to_numpy()` writes
    date-sorted values into a symbol-major frame. Every value lands on the
    wrong row, and because the permutation is global a later observation can be
    written onto an earlier row.
    """
    panel = _interleaved_panel()
    # A distinct, constant IV per symbol makes any cross-symbol bleed obvious.
    marker = {"AAA": 0.10, "BBB": 0.50, "CCC": 0.90}
    volatility = pd.DataFrame(
        [
            {
                "date": Date(2024, 1, 5), "symbol": symbol,
                "iv_current": value, "hv_current": 0.25,
                "iv_year_high": 1.0, "iv_year_low": 0.05, "iv_month_ago": value,
            }
            for symbol, value in marker.items()
        ]
    )
    attached = attach_option_features(panel, build_option_features(volatility, None))
    for symbol, expected in marker.items():
        got = attached.loc[attached["symbol"] == symbol, "opt_iv"].dropna().unique()
        assert list(got) == pytest.approx([expected]), (
            f"{symbol} received {got}, expected {expected} — rows are misaligned"
        )


def test_asof_earnings_join_aligns_to_the_original_row_order():
    # Panel dates must run past the announcement for the join to attach anything.
    panel = _interleaved_panel()
    marker = {"AAA": 1.0, "BBB": 2.0, "CCC": 4.0}
    history = pd.DataFrame(
        [
            {"symbol": s, "period_end_date": Date(2023, 12, 31),
             "reported": 1.0 + v, "estimate": 1.0}
            for s, v in marker.items()
        ]
    )
    # 28-day reporting lag: inside [MIN_REPORT_LAG_DAYS, MAX_REPORT_LAG_DAYS],
    # so the period matches an announcement rather than being dropped.
    calendar = pd.DataFrame(
        [{"symbol": s, "date": Date(2024, 1, 28), "when": "Before market open"}
         for s in marker]
    )
    events = build_earnings_events(history, calendar)
    attached = attach_earnings_features(panel, events)
    for symbol, expected in marker.items():
        got = attached.loc[attached["symbol"] == symbol, "earn_surprise_pct"].dropna().unique()
        assert list(got) == pytest.approx([expected]), (
            f"{symbol} received {got}, expected {expected} — rows are misaligned"
        )


def test_asof_join_is_invariant_to_input_row_order():
    """Shuffling the panel must not change any row's attached value."""
    panel = _interleaved_panel()
    volatility = pd.DataFrame(
        [
            {"date": Date(2024, 1, 5), "symbol": s, "iv_current": v, "hv_current": 0.25,
             "iv_year_high": 1.0, "iv_year_low": 0.05, "iv_month_ago": v}
            for s, v in {"AAA": 0.10, "BBB": 0.50, "CCC": 0.90}.items()
        ]
    )
    features = build_option_features(volatility, None)

    ordered = attach_option_features(panel, features).set_index(["symbol", "date"])["opt_iv"]
    shuffled_panel = panel.sample(frac=1.0, random_state=7).reset_index(drop=True)
    shuffled = attach_option_features(shuffled_panel, features).set_index(["symbol", "date"])["opt_iv"]

    pd.testing.assert_series_equal(
        ordered.sort_index(), shuffled.sort_index(), check_names=False
    )
