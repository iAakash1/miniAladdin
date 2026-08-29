"""
Earnings features — a period-dated table made point-in-time by an explicit join.

## The problem, measured

`eps_history` is keyed `(act_symbol, period_end_date)` and carries `reported`
and `estimate`. It has **no announcement date**. Verified directly on AAPL:

    eps_history        period_end_date 2026-06-30   reported 1.91  estimate 1.88
    earnings_calendar  date            2026-07-30   when "After market close"

The figure is dated 2026-06-30 and became public on 2026-07-30. Using the table
as-is inserts a quarter's result into prices **30 days** before anyone knew it —
and because a positive surprise is followed by a positive drift, the leak makes
results better, which is the class of error that survives review.

So nothing here reads `eps_history` alone. `build_earnings_events` joins it to
`earnings_calendar`, and a period whose announcement date cannot be established
is **dropped**, never estimated with an average reporting lag.

## The session rule

`earnings_calendar.when` distinguishes "Before market open" from "After market
close", and the distinction is a whole trading session:

* **Before market open** — tradeable on the announcement date's own close.
* **After market close** — not tradeable until the *next* session.

Treating both as same-day availability grants a free session of foresight on
roughly half of all prints. `_availability_date` applies the rule, and defaults
to the conservative side when `when` is missing or unrecognised.

## What is deliberately not built

**`days_to_next_earnings`.** Companies do announce their reporting date weeks
ahead, so in principle a model could know it. But `earnings_calendar` is a
*current snapshot* — it records that a print happened on a date, not when that
date was first published, and it contains 263 future-dated rows. There is no
column from which the announcement-of-the-announcement can be recovered, so the
feature is not built. `days_since_earnings` is unambiguous and is built instead.

## SUE, and why the denominator is trailing

Standardised unexpected earnings scales the surprise by the firm's own history
of surprises, so a 2-cent beat means something different for a company that
usually lands within a cent than for one that swings by ten. The standard
deviation is computed over **prior** surprises only — an expanding window that
ends at the previous announcement — because a denominator computed over the
full history would carry information from after the observation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.features.registry import (
    REGISTRY,
    Direction,
    FeatureDefinition,
    FeatureGroup,
)

logger = logging.getLogger("omnisignal.quant.features.earnings")

#: A period end must be followed by an announcement inside this window for the
#: two to be matched. Below the floor the "announcement" precedes the period's
#: own close; above the ceiling the association is a guess. US quarterly filers
#: report 2-8 weeks after period end, so 5-150 days is generous without being
#: credulous.
MIN_REPORT_LAG_DAYS = 5
MAX_REPORT_LAG_DAYS = 150

#: Minimum prior surprises before SUE's denominator is meaningful. Below this
#: the standard deviation is dominated by whichever quarters happen to be in it.
MIN_SUE_HISTORY = 4

#: A surprise older than this is stale. Post-earnings drift is documented over
#: roughly a quarter, so beyond ~90 days the feature is carrying an event the
#: market has long absorbed.
MAX_SURPRISE_AGE_SESSIONS = 63


def _availability_date(row: Any) -> Optional[pd.Timestamp]:
    """The first date on which a print could be acted on.

    "After market close" moves availability to the next calendar day, which the
    caller then snaps to the next trading session. Unknown or missing `when` is
    treated as after-close: the conservative direction, because assuming
    before-open would hand the model a session it did not have.
    """
    announced = row.announcement_date
    if pd.isna(announced):
        return None
    session = str(getattr(row, "when", "") or "").strip().lower()
    if session.startswith("before"):
        return pd.Timestamp(announced)
    return pd.Timestamp(announced) + pd.Timedelta(days=1)


def build_earnings_events(
    eps_history: pd.DataFrame,
    earnings_calendar: pd.DataFrame,
    *,
    min_lag_days: int = MIN_REPORT_LAG_DAYS,
    max_lag_days: int = MAX_REPORT_LAG_DAYS,
) -> pd.DataFrame:
    """Join reported EPS to its announcement date, producing dated events.

    Returns one row per matched (symbol, period), carrying the surprise and the
    date from which it was knowable. Periods with no matching announcement are
    dropped and counted — never backfilled with an assumed reporting lag, which
    would reintroduce exactly the leak this join exists to close.
    """
    if eps_history.empty or earnings_calendar.empty:
        return pd.DataFrame()

    history = eps_history.copy()
    history["period_end_date"] = pd.to_datetime(history["period_end_date"], errors="coerce")
    history = history.dropna(subset=["symbol", "period_end_date", "reported"])
    # merge_asof requires the `on` key sorted GLOBALLY, not within each `by`
    # group — sorting by (symbol, period_end_date) raises "left keys must be
    # sorted". The grouping is handled by `by=`, so only the key is sorted here.
    history = history.sort_values("period_end_date", kind="mergesort").reset_index(drop=True)

    calendar = earnings_calendar.copy()
    calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce")
    calendar = calendar.dropna(subset=["symbol", "date"])
    calendar = calendar.rename(columns={"date": "announcement_date"})
    calendar = calendar.sort_values("announcement_date", kind="mergesort").reset_index(drop=True)

    # merge_asof with direction="forward": the FIRST announcement at or after
    # each period end. `by="symbol"` keeps the match within a company.
    merged = pd.merge_asof(
        history,
        calendar[["symbol", "announcement_date", "when"]],
        left_on="period_end_date",
        right_on="announcement_date",
        by="symbol",
        direction="forward",
        tolerance=pd.Timedelta(days=max_lag_days),
    )

    merged["report_lag_days"] = (
        merged["announcement_date"] - merged["period_end_date"]
    ).dt.days
    unmatched = int(merged["announcement_date"].isna().sum())
    too_soon = int((merged["report_lag_days"] < min_lag_days).sum())

    merged = merged[
        merged["announcement_date"].notna()
        & (merged["report_lag_days"] >= min_lag_days)
    ].reset_index(drop=True)

    if merged.empty:
        logger.warning("earnings: no period matched an announcement date")
        return pd.DataFrame()

    merged["available_from"] = [
        _availability_date(row) for row in merged.itertuples(index=False)
    ]
    merged["surprise"] = pd.to_numeric(merged["reported"], errors="coerce") - pd.to_numeric(
        merged["estimate"], errors="coerce"
    )
    # Scaled by |estimate| so a 2-cent beat on a 10-cent estimate is not the
    # same as a 2-cent beat on a $5 estimate. A near-zero estimate makes the
    # ratio meaningless, so it becomes NULL rather than a large number.
    denominator = pd.to_numeric(merged["estimate"], errors="coerce").abs()
    merged["surprise_pct"] = np.where(
        denominator > 0.01, merged["surprise"] / denominator, np.nan
    )

    # Trailing standard deviation of PRIOR surprises only. `shift(1)` before the
    # expanding window is what keeps the current surprise out of its own scale.
    grouped = merged.groupby("symbol", sort=False)["surprise"]
    prior_std = grouped.transform(lambda s: s.shift(1).expanding(MIN_SUE_HISTORY).std())
    prior_count = grouped.transform(lambda s: s.shift(1).expanding(1).count())
    merged["sue"] = np.where(
        (prior_std > 1e-9) & (prior_count >= MIN_SUE_HISTORY),
        merged["surprise"] / prior_std,
        np.nan,
    )
    merged["prior_surprises"] = prior_count

    logger.info(
        "earnings: %d events matched (%d unmatched, %d lag < %dd), %d with SUE",
        len(merged), unmatched, too_soon, min_lag_days, int(merged["sue"].notna().sum()),
    )
    return merged[
        [
            "symbol", "period_end_date", "announcement_date", "available_from",
            "when", "report_lag_days", "reported", "estimate",
            "surprise", "surprise_pct", "sue", "prior_surprises",
        ]
    ]


def _match_key_dtype(left: pd.DataFrame, right: pd.DataFrame, column: str) -> None:
    """Force both merge keys to plain object dtype, in place.

    `RawStore` normalisation types symbols as pandas `string[python]` while a
    frame assembled in memory carries `object`. `merge_asof` refuses the pair
    with "incompatible merge keys" rather than coercing — which is the right
    behaviour, since a silent coercion could match different values. Both sides
    are pinned here so the comparison is defined.
    """
    for frame in (left, right):
        if column in frame.columns:
            frame[column] = frame[column].astype(str)


def attach_earnings_features(
    panel: pd.DataFrame,
    events: pd.DataFrame,
    *,
    date_column: str = "date",
    symbol_column: str = "symbol",
    max_age_sessions: int = MAX_SURPRISE_AGE_SESSIONS,
) -> pd.DataFrame:
    """Attach the most recent *available* earnings event to each panel row.

    `merge_asof` with `direction="backward"` on `available_from` is the whole
    point-in-time argument: a row dated `d` can only match an event whose
    availability date is at or before `d`. An event announced tomorrow is
    structurally unreachable, not merely unused.
    """
    out = panel.copy()
    for name in ("earn_surprise_pct", "earn_sue", "earn_days_since", "earn_surprise_sign"):
        out[name] = np.nan

    if events.empty:
        logger.warning("earnings: no events — earnings features remain NULL, not zero")
        return out

    # See the note in options.attach_option_features: the pre-initialised NULL
    # columns must not be present on the left side of the merge.
    left = out.drop(
        columns=["earn_surprise_pct", "earn_sue", "earn_days_since", "earn_surprise_sign"],
        errors="ignore",
    ).copy()
    left["_date"] = pd.to_datetime(left[date_column])
    left = left.sort_values("_date", kind="mergesort")

    right = events.dropna(subset=["available_from"]).copy()
    right["available_from"] = pd.to_datetime(right["available_from"])
    right = right.sort_values("available_from", kind="mergesort")
    _match_key_dtype(left, right, symbol_column)
    _match_key_dtype(left, right, "symbol")

    merged = pd.merge_asof(
        left,
        right[["symbol", "available_from", "surprise_pct", "sue"]],
        left_on="_date",
        right_on="available_from",
        left_by=symbol_column,
        right_by="symbol",
        direction="backward",
    )

    age = (merged["_date"] - merged["available_from"]).dt.days
    # Calendar days converted to an approximate session count. Approximate is
    # honest here: the cut-off is a staleness heuristic, not a measurement, and
    # 7/5 is the standard conversion.
    sessions = age / 7.0 * 5.0
    fresh = sessions <= max_age_sessions

    merged["earn_surprise_pct"] = merged["surprise_pct"].where(fresh)
    merged["earn_sue"] = merged["sue"].where(fresh)
    merged["earn_days_since"] = sessions.where(fresh)
    merged["earn_surprise_sign"] = np.sign(merged["surprise_pct"]).where(fresh)

    merged = merged.drop(columns=["_date", "available_from", "surprise_pct", "sue", "symbol_y"],
                         errors="ignore")
    merged = merged.sort_index()
    for name in ("earn_surprise_pct", "earn_sue", "earn_days_since", "earn_surprise_sign"):
        out[name] = merged[name].to_numpy()
    return out


def _register() -> None:
    definitions = [
        FeatureDefinition(
            name="earn_surprise_pct",
            group=FeatureGroup.FUNDAMENTAL,
            description="Latest EPS surprise as a fraction of |estimate|, available from the print.",
            rationale=(
                "Post-earnings-announcement drift: prices continue in the direction "
                "of the surprise for weeks after the print. One of the most "
                "replicated cross-sectional effects there is."
            ),
            formula="(reported - estimate) / |estimate|, attached from the announcement's availability date",
            lookback_sessions=1,
            required_columns=("reported", "estimate"),
            direction=Direction.POSITIVE,
            availability_lag_sessions=1,
            citation="Ball & Brown (1968); Bernard & Thomas (1989)",
            notes=(
                "NULL when |estimate| <= 0.01 — a ratio to a near-zero denominator is not a surprise.",
                "NULL beyond 63 sessions after the print; drift is a quarter-horizon effect.",
            ),
        ),
        FeatureDefinition(
            name="earn_sue",
            group=FeatureGroup.FUNDAMENTAL,
            description="Standardised unexpected earnings: surprise over its own trailing dispersion.",
            rationale=(
                "Scales the surprise by the firm's own history of surprises, so a "
                "2-cent beat is read against how tightly that company usually lands."
            ),
            formula="(reported - estimate) / std(prior surprises, expanding, >= 4 observations)",
            lookback_sessions=1,
            required_columns=("reported", "estimate"),
            direction=Direction.POSITIVE,
            availability_lag_sessions=1,
            citation="Foster, Olsen & Shevlin (1984)",
            notes=("The denominator uses PRIOR surprises only — shift(1) before the expanding window.",),
        ),
        FeatureDefinition(
            name="earn_days_since",
            group=FeatureGroup.FUNDAMENTAL,
            description="Approximate trading sessions since the latest available print.",
            rationale=(
                "Drift decays. A surprise 5 sessions old and one 55 sessions old are "
                "different signals and the model should be able to tell them apart."
            ),
            formula="(observation date - availability date) in calendar days x 5/7",
            lookback_sessions=1,
            required_columns=("reported",),
            direction=Direction.NEGATIVE,
            availability_lag_sessions=1,
            notes=("Calendar-to-session conversion is approximate and used only as a staleness cut-off.",),
        ),
        FeatureDefinition(
            name="earn_surprise_sign",
            group=FeatureGroup.FUNDAMENTAL,
            description="Sign of the latest available surprise (-1, 0, +1).",
            rationale=(
                "Separates direction from magnitude. Part of the drift literature "
                "finds the sign carries most of the effect and the magnitude adds little."
            ),
            formula="sign(surprise_pct)",
            lookback_sessions=1,
            required_columns=("reported", "estimate"),
            direction=Direction.POSITIVE,
            availability_lag_sessions=1,
        ),
    ]
    for definition in definitions:
        REGISTRY.register(definition)


_register()
