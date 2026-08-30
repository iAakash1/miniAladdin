"""
Analyst estimate revisions — the one fundamental-adjacent family that needs no
publication gate.

## Why this family is different

Every other fundamental source in this repository is keyed by fiscal period end
and is therefore unusable as-dated: the quarter ending 2026-06-30 was announced
2026-07-30, so reading it on its own date grants a month of hindsight. Those
tables reach a feature only behind `earnings_calendar` (see `fundamentals.py`).

`eps_estimate` and `sales_estimate` are keyed by **observation date**. A row
says what the analyst consensus was on that Sunday, and it was knowable that
Sunday. Verified directly on AAPL for the period ending 2026-06-30:

    2026-02-01  consensus 1.70   count 9
    ...
    2026-04-12  consensus 1.68   count 9      <- a downward revision
    2026-04-19  consensus 1.73   count 9      <- and back up

A revision series is recoverable by differencing the panel against itself, with
no forward reference anywhere. That is what makes this family admissible.

## The trap: `period` is relative, not absolute

`period` takes the values 'Current Quarter', 'Current Year', 'Next Quarter',
'Next Year'. These are labels *relative to the observation date*, so the period
they point at MOVES. When a fiscal year rolls over, the row labelled 'Current
Year' stops describing FY2025 and starts describing FY2026, and the consensus
jumps — not because anyone revised anything, but because the question changed.

Differencing naively across that boundary manufactures an enormous revision out
of a bookkeeping artefact, and it does so on a predictable calendar, which is
precisely the kind of spurious regularity a tree model will happily fit. So
every revision here is computed only where `period_end_date` is **unchanged**
between the two vintages being differenced; where it moves, the feature is NULL.
`test_estimates.py` asserts this on a constructed rollover.

## Cadence

Observations are weekly (~52 distinct dates a year since 2017-10-26). Lookbacks
are therefore expressed in weeks and converted to vintage rows, not sessions.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.quant.features.registry import (
    REGISTRY,
    Direction,
    FeatureDefinition,
    FeatureGroup,
)

logger = logging.getLogger("omnisignal.quant.features.estimates")

#: The relative period this family measures.
#:
#: 'Current Year' (FY1) is the standard horizon for the revisions literature:
#: quarterly consensus is noisier and rolls over four times as often, and 'Next
#: Year' is thinly covered early in a fiscal year. One horizon also keeps the
#: feature count honest — four periods x four measures would be sixteen
#: near-collinear columns dressed up as breadth.
PRIMARY_PERIOD = "Current Year"

#: Revision lookbacks in vintage rows. Weekly cadence, so 4 ~ one month and
#: 13 ~ one quarter.
REVISION_WEEKS: tuple[int, ...] = (4, 13)

#: A consensus this close to zero makes the percentage denominator meaningless.
#: Loss-making and break-even names genuinely sit here, so the revision is NULL
#: rather than an arbitrarily large number.
MIN_ABS_CONSENSUS = 0.05

#: Vintages older than this are stale: coverage dropped, or the symbol left the
#: estimate panel. Attaching a six-month-old consensus to today's row would
#: assert a belief nobody currently holds.
MAX_VINTAGE_AGE_DAYS = 45

FEATURE_NAMES: tuple[str, ...] = (
    "est_eps_rev_4w",
    "est_eps_rev_13w",
    "est_sales_rev_4w",
    "est_sales_rev_13w",
    "est_eps_dispersion",
    "est_eps_coverage",
    "est_eps_coverage_chg_13w",
    "est_eps_growth_expected",
)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Percentage change guarded against a denominator that means nothing."""
    base = denominator.abs()
    out = numerator / base
    return out.where(base >= MIN_ABS_CONSENSUS)


def _revisions(frame: pd.DataFrame, value: str, prefix: str) -> pd.DataFrame:
    """Backward differences of one estimate series, per symbol.

    The `period_end_date` equality check is the whole point-in-time argument for
    this family — see the module docstring. Without it a fiscal rollover reads
    as a revision.
    """
    out = pd.DataFrame(index=pd.RangeIndex(len(frame)))
    grouped = frame.groupby("symbol", sort=False, observed=True)

    for weeks in REVISION_WEEKS:
        prior = grouped[value].shift(weeks)
        prior_period = grouped["period_end_date"].shift(weeks)
        same_period = prior_period.to_numpy() == frame["period_end_date"].to_numpy()
        revision = _safe_ratio(frame[value] - prior, prior)
        out[f"{prefix}_rev_{weeks}w"] = revision.where(pd.Series(same_period, index=frame.index))

    return out


def build_estimate_features(
    eps_estimate: Optional[pd.DataFrame],
    sales_estimate: Optional[pd.DataFrame],
    *,
    period: str = PRIMARY_PERIOD,
) -> pd.DataFrame:
    """Collapse the estimate vintages into one dated row per symbol per vintage.

    Returns a frame keyed (symbol, available_from) carrying every feature in
    `FEATURE_NAMES`. `available_from` is the vintage date itself: unlike a
    fiscal period, an estimate observation is knowable on the day it is observed.
    """
    if eps_estimate is None or eps_estimate.empty:
        logger.warning("estimates: no eps_estimate — estimate features absent, not zeroed")
        return pd.DataFrame()

    eps = eps_estimate.copy()
    eps = eps[eps["period"] == period]
    if eps.empty:
        logger.warning("estimates: period %r absent from eps_estimate", period)
        return pd.DataFrame()

    eps["date"] = pd.to_datetime(eps["date"])
    eps["period_end_date"] = pd.to_datetime(eps["period_end_date"])
    for column in ("consensus", "high", "low", "count", "year_ago"):
        if column in eps.columns:
            eps[column] = pd.to_numeric(eps[column], errors="coerce")

    # Sorting by (symbol, date) is what makes `shift` a backward operation. The
    # groupby preserves this order, so a shift can only reach earlier vintages.
    eps = eps.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)

    out = pd.DataFrame(
        {"symbol": eps["symbol"].to_numpy(), "available_from": eps["date"].to_numpy()}
    )

    eps_rev = _revisions(eps, "consensus", "eps")
    out["est_eps_rev_4w"] = eps_rev["eps_rev_4w"].to_numpy()
    out["est_eps_rev_13w"] = eps_rev["eps_rev_13w"].to_numpy()

    # Dispersion: the spread of analyst opinion, scaled. High dispersion is
    # documented to predict LOWER returns (Diether, Malloy & Scherbina 2002).
    spread = eps["high"] - eps["low"]
    out["est_eps_dispersion"] = _safe_ratio(spread, eps["consensus"]).to_numpy()

    out["est_eps_coverage"] = eps["count"].to_numpy()
    coverage_prior = eps.groupby("symbol", sort=False, observed=True)["count"].shift(13)
    out["est_eps_coverage_chg_13w"] = (eps["count"] - coverage_prior).to_numpy()

    # Expected growth against the year-ago actual. `year_ago` is a realised
    # figure for a period already reported, so it carries no forward reference.
    out["est_eps_growth_expected"] = _safe_ratio(
        eps["consensus"] - eps["year_ago"], eps["year_ago"]
    ).to_numpy()

    if sales_estimate is not None and not sales_estimate.empty:
        sales = sales_estimate.copy()
        sales = sales[sales["period"] == period]
        if not sales.empty:
            sales["date"] = pd.to_datetime(sales["date"])
            sales["period_end_date"] = pd.to_datetime(sales["period_end_date"])
            sales["consensus"] = pd.to_numeric(sales["consensus"], errors="coerce")
            sales = sales.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
            sales_rev = _revisions(sales, "consensus", "sales")
            keyed = pd.DataFrame(
                {
                    "symbol": sales["symbol"].to_numpy(),
                    "available_from": sales["date"].to_numpy(),
                    "est_sales_rev_4w": sales_rev["sales_rev_4w"].to_numpy(),
                    "est_sales_rev_13w": sales_rev["sales_rev_13w"].to_numpy(),
                }
            )
            out = out.merge(keyed, on=["symbol", "available_from"], how="left")

    for name in ("est_sales_rev_4w", "est_sales_rev_13w"):
        if name not in out.columns:
            out[name] = np.nan

    out = out.sort_values("available_from", kind="mergesort").reset_index(drop=True)
    logger.info(
        "estimates: %d vintages across %d symbols (%s .. %s)",
        len(out), out["symbol"].nunique(),
        out["available_from"].min(), out["available_from"].max(),
    )
    return out


def attach_estimate_features(
    panel: pd.DataFrame,
    estimates: pd.DataFrame,
    *,
    date_column: str = "date",
    symbol_column: str = "symbol",
    max_age_days: int = MAX_VINTAGE_AGE_DAYS,
) -> pd.DataFrame:
    """Attach the most recent *observed* estimate vintage to each panel row.

    Backward as-of on the vintage date. A vintage published next Sunday is
    structurally unreachable from today's row, not merely unused.
    """
    from src.quant.features.earnings import _asof_aligned, _match_key_dtype

    out = panel.copy()
    for name in FEATURE_NAMES:
        out[name] = np.nan

    if estimates.empty:
        logger.warning("estimates: no vintages — estimate features remain NULL, not zero")
        return out

    # The pre-initialised NULL columns must not appear on the left of the merge,
    # or they collide with the right frame's real ones and pandas suffixes both.
    left = out.drop(columns=list(FEATURE_NAMES), errors="ignore").copy()
    left["_date"] = pd.to_datetime(left[date_column])

    right = estimates.dropna(subset=["available_from"]).copy()
    right["available_from"] = pd.to_datetime(right["available_from"])
    right = right.sort_values("available_from", kind="mergesort")
    _match_key_dtype(left, right, symbol_column)
    _match_key_dtype(left, right, "symbol")
    if symbol_column != "symbol":
        left = left.rename(columns={symbol_column: "symbol"})

    merged = _asof_aligned(
        left,
        right[["symbol", "available_from", *FEATURE_NAMES]],
        left_on="_date", right_on="available_from", by="symbol",
        columns=list(FEATURE_NAMES),
    )

    age_days = (merged["_date"] - merged["available_from"]).dt.days
    fresh = age_days <= max_age_days

    for name in FEATURE_NAMES:
        out[name] = merged[name].where(fresh).to_numpy()

    attached = int(fresh.sum())
    logger.info(
        "estimates: attached %d/%d panel rows (%.1f%%) within %d days",
        attached, len(out), 100.0 * attached / max(len(out), 1), max_age_days,
    )
    return out


def _register() -> None:
    common = (
        "Vintage-dated: the row records what consensus WAS on its observation "
        "date, so no publication gate is required.",
        "Revisions are NULL across a fiscal rollover, where 'Current Year' "
        "changes which period it refers to.",
        f"Weekly cadence; a vintage older than {MAX_VINTAGE_AGE_DAYS} days is "
        "treated as stale and the row is NULL.",
    )

    for weeks in REVISION_WEEKS:
        REGISTRY.register(
            FeatureDefinition(
                name=f"est_eps_rev_{weeks}w",
                group=FeatureGroup.FUNDAMENTAL,
                description=f"Change in FY1 EPS consensus over {weeks} weekly vintages.",
                rationale=(
                    "Analyst revisions are among the better-replicated cross-sectional "
                    "effects: consensus adjusts gradually, so the direction of recent "
                    "revision carries into forward returns."
                ),
                formula=(
                    f"(consensus_t - consensus_(t-{weeks}w)) / |consensus_(t-{weeks}w)|, "
                    "only where period_end_date is unchanged"
                ),
                lookback_sessions=weeks * 5,
                required_columns=("consensus", "period_end_date"),
                direction=Direction.POSITIVE,
                citation="Chan, Jegadeesh & Lakonishok (1996); Stickel (1991)",
                notes=common,
            )
        )
        REGISTRY.register(
            FeatureDefinition(
                name=f"est_sales_rev_{weeks}w",
                group=FeatureGroup.FUNDAMENTAL,
                description=f"Change in FY1 revenue consensus over {weeks} weekly vintages.",
                rationale=(
                    "Revenue revisions are harder to manage than earnings revisions "
                    "and so carry information the EPS series does not."
                ),
                formula=(
                    f"(consensus_t - consensus_(t-{weeks}w)) / |consensus_(t-{weeks}w)|, "
                    "only where period_end_date is unchanged"
                ),
                lookback_sessions=weeks * 5,
                required_columns=("consensus", "period_end_date"),
                direction=Direction.POSITIVE,
                notes=common,
            )
        )

    REGISTRY.register(
        FeatureDefinition(
            name="est_eps_dispersion",
            group=FeatureGroup.FUNDAMENTAL,
            description="Spread of FY1 EPS estimates, scaled by consensus.",
            rationale=(
                "Disagreement among analysts proxies for uncertainty. High-dispersion "
                "names have historically UNDERperformed, which is the opposite of what "
                "a risk story predicts."
            ),
            formula="(high - low) / |consensus|",
            lookback_sessions=0,
            required_columns=("high", "low", "consensus"),
            direction=Direction.NEGATIVE,
            citation="Diether, Malloy & Scherbina (2002)",
            notes=common,
        )
    )
    REGISTRY.register(
        FeatureDefinition(
            name="est_eps_coverage",
            group=FeatureGroup.FUNDAMENTAL,
            description="Number of analysts contributing an FY1 EPS estimate.",
            rationale=(
                "Coverage proxies for attention and for how quickly information is "
                "impounded. Included as a control on the revision features rather "
                "than as a predictor in its own right."
            ),
            formula="count",
            lookback_sessions=0,
            required_columns=("count",),
            direction=Direction.DESCRIPTIVE,
            notes=common,
        )
    )
    REGISTRY.register(
        FeatureDefinition(
            name="est_eps_coverage_chg_13w",
            group=FeatureGroup.FUNDAMENTAL,
            description="Change in analyst count over 13 weekly vintages.",
            rationale=(
                "Analysts initiating or dropping coverage is a slow signal about "
                "institutional interest."
            ),
            formula="count_t - count_(t-13w)",
            lookback_sessions=65,
            required_columns=("count",),
            direction=Direction.POSITIVE,
            notes=common,
        )
    )
    REGISTRY.register(
        FeatureDefinition(
            name="est_eps_growth_expected",
            group=FeatureGroup.FUNDAMENTAL,
            description="FY1 consensus against the year-ago realised figure.",
            rationale=(
                "Expected growth. `year_ago` describes a period already reported, so "
                "it carries no forward reference."
            ),
            formula="(consensus - year_ago) / |year_ago|",
            lookback_sessions=0,
            required_columns=("consensus", "year_ago"),
            direction=Direction.DESCRIPTIVE,
            notes=common,
        )
    )


_register()
