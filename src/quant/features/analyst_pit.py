"""
Point-in-time analyst-estimate features for EXP-009C.

This module supersedes `estimates.py` for the analyst arm. It exists because the
forensics in `docs/ANALYST_DATA_FORENSICS.md` found four things the earlier
construction handled implicitly or not at all:

1. **Cadence is not a fixed week.** 93% of per-symbol vintage gaps are 7 days,
   but only 56% in 2017 and 73% in 2018, and 4% of gaps overall are longer than a
   week. `estimates.py` differences by *row* (`shift(4)`), so a "4-week" revision
   silently spans a different time whenever a vintage is missing or extra. Here
   every lookback is a *calendar* lookback: the prior vintage must sit within a
   stated tolerance of `t - horizon`, or the revision is NULL.
2. **Same-day vintages.** 10.1% of distinct vintage dates (5.2% of rows) are not
   Sundays (they cluster in 2017-18); 0.7% of panel rows matched a vintage dated the same day. The
   intraday time of a vintage is unknown, so the attach step is strict: a panel
   row sees only vintages dated *before* it.
3. **A single analyst is not dispersion.** 20% of rows have `count == 1`; for
   those, `high - low` is exactly zero (99.98%), which `estimates.py` scores as
   "no disagreement". Dispersion is NULL below two analysts.
4. **Ticker reuse.** 308 symbols have a gap of more than a year between
   vintages. A revision across such a gap compares two different situations, and
   the calendar tolerance makes it NULL.

Everything else is inherited: revisions only where `period_end_date` is
unchanged (a fiscal rollover is a change of question, not a revision), missing
stays missing, a near-zero denominator gives NULL, and a stale vintage attaches
as NULL.

## Reproducibility, in two senses

*Computational:* every feature below is an exact function of the stored vintages
— rerun on the same data it returns the same numbers, and a truncation test
proves no future vintage can reach an earlier row.

*Against the literature:* only APPROXIMATED at best. The vendor and its
consensus definition are unknown, the horizon is FY1 only, the cadence is weekly
rather than monthly, and there is no analyst identity. Stickiness
(Cao, Tao, Wang & Yin, Review of Finance 2026), recommendation changes and
target-price revisions are NOT REPRODUCIBLE from this data; `LITERATURE_STATUS`
records that per feature so no claim outruns it.

The features are deliberately **not** added to the global `REGISTRY`: registering
them changes every default dataset build and the registry hash that ties
datasets to experiments. They are attached explicitly by the EXP-009C runner,
and registration is a separate step that only follows a result worth registering.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

PRIMARY_PERIOD = "Current Year"

#: Calendar lookbacks and how far from the target date a prior vintage may sit.
HORIZON_DAYS = {"4w": (28, 3), "13w": (91, 5)}

#: A denominator this close to zero makes a percentage change meaningless.
MIN_ABS_BASE = 0.05

#: A vintage older than this is not "the current consensus" any more.
MAX_VINTAGE_AGE_DAYS = 45

FEATURE_NAMES: tuple[str, ...] = (
    "analyst_eps_rev_4w",
    "analyst_eps_rev_13w",
    "analyst_sales_rev_4w",
    "analyst_sales_rev_13w",
    "analyst_eps_dispersion",
    "analyst_eps_coverage",
    "analyst_eps_coverage_chg_13w",
    "analyst_eps_rev_acceleration",
)

#: Two axes, kept apart on purpose. See the module docstring.
LITERATURE_STATUS: dict[str, dict[str, str]] = {
    "analyst_eps_rev_4w": {"computational": "EXACT", "literature": "APPROXIMATED",
                           "why": "consensus revision (Chan, Jegadeesh & Lakonishok 1996 family); vendor unknown, FY1 only, weekly vintages"},
    "analyst_eps_rev_13w": {"computational": "EXACT", "literature": "APPROXIMATED", "why": "as above, quarterly horizon"},
    "analyst_sales_rev_4w": {"computational": "EXACT", "literature": "APPROXIMATED", "why": "revenue consensus revision; 10% of sales rows lack consensus"},
    "analyst_sales_rev_13w": {"computational": "EXACT", "literature": "APPROXIMATED", "why": "as above, quarterly horizon"},
    "analyst_eps_dispersion": {"computational": "EXACT", "literature": "APPROXIMATED",
                               "why": "(high - low) / |consensus|, not the standard deviation of individual forecasts (Diether, Malloy & Scherbina 2002); NULL below two analysts"},
    "analyst_eps_coverage": {"computational": "EXACT", "literature": "APPROXIMATED", "why": "vendor `count`; its definition is undocumented"},
    "analyst_eps_coverage_chg_13w": {"computational": "EXACT", "literature": "APPROXIMATED", "why": "change in vendor `count`"},
    "analyst_eps_rev_acceleration": {"computational": "EXACT", "literature": "AUTHOR-DEFINED",
                                     "why": "change in the 4-week revision over the previous 4 weeks; no published counterpart"},
    "analyst_stickiness": {"computational": "NOT AVAILABLE", "literature": "NOT REPRODUCIBLE",
                           "why": "requires analyst identity and individual forecast histories (Cao, Tao, Wang & Yin 2026); the table holds only consensus, high, low and count"},
    "recommendation_change": {"computational": "NOT AVAILABLE", "literature": "NOT REPRODUCIBLE", "why": "no recommendation data"},
    "target_price_revision": {"computational": "NOT AVAILABLE", "literature": "NOT REPRODUCIBLE", "why": "no target-price data"},
    "individual_analyst_forecast_error": {"computational": "NOT AVAILABLE", "literature": "NOT REPRODUCIBLE", "why": "no analyst-level data"},
}


def _ratio(numerator: pd.Series, base: pd.Series) -> pd.Series:
    denominator = base.abs()
    return (numerator / denominator).where(denominator >= MIN_ABS_BASE)


def _prior_vintage(
    frame: pd.DataFrame,
    columns: list[str],
    days: int,
    tolerance: int,
    suffix: str,
    *,
    anchor: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """For each row, the latest vintage of the same symbol at or before `anchor - days`.

    `anchor` defaults to the row's own vintage date; passing a previous prior's
    date chains a second lookback (used for the acceleration). The match must sit
    within `tolerance` days of the target date, otherwise the row has no prior
    and its prior columns are NaT/NaN. Returns a frame aligned to `frame`'s index.
    """
    anchor_dates = frame["date"] if anchor is None else anchor
    left = pd.DataFrame({
        "symbol": frame["symbol"].to_numpy(),
        "_target": (pd.to_datetime(anchor_dates) - pd.Timedelta(days=days)).to_numpy(),
        "_row": np.arange(len(frame)),
    })
    valid = left["_target"].notna()
    right = frame[["symbol", "date", *columns]].rename(columns={"date": "_prior_date"})
    right = right.sort_values("_prior_date", kind="mergesort")

    merged = pd.merge_asof(
        left[valid].sort_values("_target", kind="mergesort"), right,
        left_on="_target", right_on="_prior_date", by="symbol",
        direction="backward", tolerance=pd.Timedelta(days=tolerance),
    )
    picked = merged.set_index("_row")[["_prior_date", *columns]].rename(
        columns={"_prior_date": f"date{suffix}", **{c: f"{c}{suffix}" for c in columns}})
    return picked.reindex(np.arange(len(frame))).set_axis(frame.index)


def _clean(table: Optional[pd.DataFrame], period: str) -> pd.DataFrame:
    if table is None or table.empty:
        return pd.DataFrame()
    frame = table[table["period"] == period].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["symbol"] = frame["symbol"].astype(str)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["period_end_date"] = pd.to_datetime(frame["period_end_date"])
    for column in ("consensus", "high", "low", "count"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def _revision(frame: pd.DataFrame, label: str) -> pd.Series:
    days, tolerance = HORIZON_DAYS[label]
    prior = _prior_vintage(frame, ["consensus", "period_end_date"], days, tolerance, "_p")
    same_period = prior["period_end_date_p"].eq(frame["period_end_date"]) & prior["date_p"].notna()
    return _ratio(frame["consensus"] - prior["consensus_p"], prior["consensus_p"]).where(same_period)


def build_analyst_features(
    eps_estimate: Optional[pd.DataFrame],
    sales_estimate: Optional[pd.DataFrame],
    *,
    period: str = PRIMARY_PERIOD,
) -> pd.DataFrame:
    """One dated row per (symbol, vintage) carrying every feature in `FEATURE_NAMES`.

    `available_from` is the vintage date; the attach step then requires the panel
    row to be strictly later. No feature reads a vintage dated after its own.
    """
    eps = _clean(eps_estimate, period)
    if eps.empty:
        return pd.DataFrame(columns=["symbol", "available_from", *FEATURE_NAMES])

    out = pd.DataFrame({"symbol": eps["symbol"], "available_from": eps["date"]})
    out["analyst_eps_rev_4w"] = _revision(eps, "4w").to_numpy()
    out["analyst_eps_rev_13w"] = _revision(eps, "13w").to_numpy()

    # Dispersion needs at least two analysts; a lone analyst has no disagreement to measure.
    spread = eps["high"] - eps["low"]
    out["analyst_eps_dispersion"] = _ratio(spread, eps["consensus"]).where(eps["count"] >= 2).to_numpy()
    out["analyst_eps_coverage"] = eps["count"].to_numpy()

    days, tolerance = HORIZON_DAYS["13w"]
    prior = _prior_vintage(eps, ["count", "period_end_date"], days, tolerance, "_p")
    out["analyst_eps_coverage_chg_13w"] = (
        (eps["count"] - prior["count_p"]).where(prior["date_p"].notna()).to_numpy()
    )

    # Acceleration: the 4-week revision now minus the 4-week revision one step
    # earlier. All three consensus points must describe the same fiscal period.
    d4, t4 = HORIZON_DAYS["4w"]
    first = _prior_vintage(eps, ["consensus", "period_end_date"], d4, t4, "_1")
    second = _prior_vintage(eps, ["consensus", "period_end_date"], d4, t4, "_2", anchor=first["date_1"])
    same = (
        first["period_end_date_1"].eq(eps["period_end_date"])
        & second["period_end_date_2"].eq(eps["period_end_date"])
        & first["date_1"].notna() & second["date_2"].notna()
    )
    recent = _ratio(eps["consensus"] - first["consensus_1"], first["consensus_1"])
    earlier = _ratio(first["consensus_1"] - second["consensus_2"], second["consensus_2"])
    out["analyst_eps_rev_acceleration"] = (recent - earlier).where(same).to_numpy()

    sales = _clean(sales_estimate, period)
    if sales.empty:
        out["analyst_sales_rev_4w"] = np.nan
        out["analyst_sales_rev_13w"] = np.nan
    else:
        keyed = pd.DataFrame({
            "symbol": sales["symbol"], "available_from": sales["date"],
            "analyst_sales_rev_4w": _revision(sales, "4w").to_numpy(),
            "analyst_sales_rev_13w": _revision(sales, "13w").to_numpy(),
        })
        out = out.merge(keyed, on=["symbol", "available_from"], how="left")

    return out[["symbol", "available_from", *FEATURE_NAMES]].sort_values(
        ["available_from", "symbol"], kind="mergesort").reset_index(drop=True)


def attach_analyst_features(
    panel: pd.DataFrame,
    features: pd.DataFrame,
    *,
    date_column: str = "date",
    symbol_column: str = "symbol",
    max_age_days: int = MAX_VINTAGE_AGE_DAYS,
) -> pd.DataFrame:
    """Attach the latest vintage strictly BEFORE each panel row.

    `allow_exact_matches=False` is the point: a vintage dated the same day as
    the panel row is unreachable, because the time of day the vintage was taken
    is unknown. Alignment is by original index label, not by position (the
    failure documented in `earnings._asof_aligned`). The input frame is not
    modified. A vintage older than `max_age_days` yields NULL.
    """
    out = panel.copy()
    for name in FEATURE_NAMES:
        out[name] = np.nan
    if features is None or features.empty:
        return out

    left = pd.DataFrame({
        "symbol": panel[symbol_column].astype(str).to_numpy(),
        "_date": pd.to_datetime(panel[date_column]).to_numpy(),
        "_row": np.arange(len(panel)),
    }).sort_values("_date", kind="mergesort")
    right = features.copy()
    right["symbol"] = right["symbol"].astype(str)
    right["available_from"] = pd.to_datetime(right["available_from"])
    right = right.sort_values("available_from", kind="mergesort")

    merged = pd.merge_asof(
        left, right[["symbol", "available_from", *FEATURE_NAMES]],
        left_on="_date", right_on="available_from", by="symbol",
        direction="backward", allow_exact_matches=False,
    ).sort_values("_row", kind="mergesort")
    age = (merged["_date"] - merged["available_from"]).dt.days
    fresh = (age <= max_age_days).to_numpy()
    for name in FEATURE_NAMES:
        out[name] = np.where(fresh, merged[name].to_numpy(), np.nan)
    return out
