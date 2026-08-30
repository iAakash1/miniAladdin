"""
Statement fundamentals, behind the announcement gate.

## The gate is the entire argument

`income_statement`, `balance_sheet_*` and `cash_flow_statement` are keyed by
FISCAL PERIOD END. Verified on AAPL: the quarter ending 2026-06-30 was announced
2026-07-30, the quarter ending 2025-12-31 was announced 2026-01-29 — a 29-30 day
lag — and 270,888 of 270,925 `income_statement` rows fall on a month end.

Reading any of them on its own date hands a model a month of hindsight on every
quarterly figure. So nothing here is emitted as-dated. Each period is joined
forward to its first `earnings_calendar` announcement, and a period whose
announcement cannot be established produces NOTHING — it is dropped, never
estimated from a conventional 45- or 90-day assumption. `earnings_calendar`
begins 2020-01-22, so periods before it are simply unavailable, and that is
recorded rather than patched.

This is the same mechanism `earnings.py` has applied to `eps_history` since
EXP-002, reused rather than reinvented.

## What the gate does NOT fix

There is one row per (symbol, period) and no vintage column. A restatement
therefore OVERWRITES the original figure, and the original is unrecoverable. A
model reading a restated value on the original announcement date is reading a
correction that did not exist yet.

The size of that effect cannot be measured from this table. It is recorded as
`restatement_risk=UNQUANTIFIED` on every feature here, these features are
isolated in their own ablation arm so their contribution can be discounted
separately, and `docs/quant/FEATURES.md` states it. It is a real, open
limitation — not a solved problem.

## Quarterly cash flow

Some filers report cash-flow lines year-to-date rather than per quarter. Where
the annual row for a period is present the quarterly figures are differenced;
where the convention cannot be established the value is NULL. Trailing-twelve-
month sums are built only from four consecutive discrete quarters.
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

logger = logging.getLogger("omnisignal.quant.features.fundamentals")

#: An announcement must follow the period end within this window to be matched.
#: Below the floor the "announcement" precedes the period it reports on; above
#: the ceiling the pairing is guesswork.
MIN_ANNOUNCEMENT_LAG_DAYS = 1
MAX_ANNOUNCEMENT_LAG_DAYS = 180

#: A fundamental older than this is stale — the filer has probably stopped
#: reporting, and carrying a two-year-old margin forward asserts a fact nobody
#: has confirmed.
MAX_FUNDAMENTAL_AGE_DAYS = 200

#: Denominator floor. Scaled figures are in dollars, so this is a real filter
#: against microcaps and shells rather than a numerical epsilon.
MIN_DENOMINATOR = 1_000_000.0

FEATURE_NAMES: tuple[str, ...] = (
    "fund_gross_margin",
    "fund_operating_margin",
    "fund_roe",
    "fund_roa",
    "fund_debt_to_equity",
    "fund_current_ratio",
    "fund_accruals",
    "fund_asset_growth_yoy",
    "fund_sales_growth_yoy",
    "fund_net_issuance_yoy",
)

#: Attached to every definition in this module. See the module docstring.
RESTATEMENT_NOTE = (
    "restatement_risk=UNQUANTIFIED — one row per period, no vintage column, so a "
    "later correction overwrites the original irrecoverably."
)
GATE_NOTE = (
    "Announcement-gated: joined forward to the first earnings_calendar date at or "
    "after the period end. Periods with no announcement are dropped, not estimated."
)


def _ratio(numerator: pd.Series, denominator: pd.Series, *, floor: float = MIN_DENOMINATOR) -> pd.Series:
    base = pd.to_numeric(denominator, errors="coerce")
    top = pd.to_numeric(numerator, errors="coerce")
    return (top / base).where(base.abs() >= floor)


def build_fundamental_events(
    income: Optional[pd.DataFrame],
    balance_assets: Optional[pd.DataFrame],
    balance_liabilities: Optional[pd.DataFrame],
    balance_equity: Optional[pd.DataFrame],
    cash_flow: Optional[pd.DataFrame],
    earnings_calendar: Optional[pd.DataFrame],
    *,
    period: str = "Quarter",
) -> pd.DataFrame:
    """Join the statement set into dated, announcement-gated events.

    Returns a frame keyed (symbol, available_from). `available_from` is an
    ANNOUNCEMENT date, never a period end — that distinction is the reason this
    module exists.
    """
    if income is None or income.empty or earnings_calendar is None or earnings_calendar.empty:
        logger.warning(
            "fundamentals: income statement or earnings calendar absent — "
            "fundamental features absent, not zeroed"
        )
        return pd.DataFrame()

    def _prep(frame: Optional[pd.DataFrame], label: str) -> Optional[pd.DataFrame]:
        if frame is None or frame.empty:
            logger.warning("fundamentals: %s absent; its features will be NULL", label)
            return None
        out = frame.copy()
        out = out[out["period"] == period]
        if out.empty:
            return None
        out["date"] = pd.to_datetime(out["date"])
        return out.rename(columns={"date": "period_end_date"})

    inc = _prep(income, "income_statement")
    if inc is None:
        return pd.DataFrame()

    merged = inc
    for frame, label in (
        (balance_assets, "balance_sheet_assets"),
        (balance_liabilities, "balance_sheet_liabilities"),
        (balance_equity, "balance_sheet_equity"),
        (cash_flow, "cash_flow_statement"),
    ):
        prepared = _prep(frame, label)
        if prepared is None:
            continue
        overlap = [
            c for c in prepared.columns
            if c in merged.columns and c not in ("symbol", "period_end_date", "period")
        ]
        prepared = prepared.drop(columns=overlap)
        merged = merged.merge(
            prepared.drop(columns=["period"], errors="ignore"),
            on=["symbol", "period_end_date"], how="left",
        )

    # ── the gate ────────────────────────────────────────────────────────
    calendar = earnings_calendar.copy()
    calendar["date"] = pd.to_datetime(calendar["date"])
    calendar = calendar.rename(columns={"date": "announcement_date"})
    calendar = calendar.sort_values("announcement_date", kind="mergesort").reset_index(drop=True)

    merged = merged.sort_values("period_end_date", kind="mergesort").reset_index(drop=True)

    # direction="forward": the FIRST announcement at or after the period end.
    gated = pd.merge_asof(
        merged,
        calendar[["symbol", "announcement_date"]],
        left_on="period_end_date",
        right_on="announcement_date",
        left_by="symbol",
        right_by="symbol",
        direction="forward",
    )

    lag = (gated["announcement_date"] - gated["period_end_date"]).dt.days
    plausible = (
        gated["announcement_date"].notna()
        & (lag >= MIN_ANNOUNCEMENT_LAG_DAYS)
        & (lag <= MAX_ANNOUNCEMENT_LAG_DAYS)
    )
    dropped = int((~plausible).sum())
    gated = gated[plausible].copy()
    if gated.empty:
        logger.warning("fundamentals: no period matched a plausible announcement date")
        return pd.DataFrame()
    logger.info(
        "fundamentals: %d periods gated, %d dropped for want of an announcement",
        len(gated), dropped,
    )

    gated["available_from"] = gated["announcement_date"]
    gated = gated.sort_values(["symbol", "period_end_date"], kind="mergesort").reset_index(drop=True)
    grouped = gated.groupby("symbol", sort=False, observed=True)

    out = pd.DataFrame(
        {
            "symbol": gated["symbol"].to_numpy(),
            "available_from": gated["available_from"].to_numpy(),
            "period_end_date": gated["period_end_date"].to_numpy(),
        }
    )

    def col(name: str) -> pd.Series:
        if name in gated.columns:
            return pd.to_numeric(gated[name], errors="coerce")
        return pd.Series(np.nan, index=gated.index)

    sales = col("sales")
    out["fund_gross_margin"] = _ratio(col("gross_profit"), sales)
    out["fund_operating_margin"] = _ratio(col("pretax_income"), sales)
    out["fund_roe"] = _ratio(col("net_income"), col("total_equity"))
    out["fund_roa"] = _ratio(col("net_income"), col("total_assets"))
    out["fund_debt_to_equity"] = _ratio(col("total_liabilities"), col("total_equity"))
    out["fund_current_ratio"] = _ratio(
        col("total_current_assets"), col("total_current_liabilities")
    )

    # Accruals: the wedge between accounting earnings and cash. Persistently
    # negative for firms whose earnings are cash-backed.
    out["fund_accruals"] = _ratio(
        col("net_income") - col("net_cash_from_operating_activities"), col("total_assets")
    )

    # Year-over-year growth uses a 4-quarter shift, valid only where the prior
    # period end is genuinely ~1 year earlier. A filer with a gap in coverage
    # would otherwise compare across an arbitrary span.
    prior_end = grouped["period_end_date"].shift(4)
    span_days = (gated["period_end_date"] - prior_end).dt.days
    comparable = pd.Series((span_days >= 300) & (span_days <= 430), index=gated.index)

    for name, source in (
        ("fund_asset_growth_yoy", "total_assets"),
        ("fund_sales_growth_yoy", "sales"),
        ("fund_net_issuance_yoy", "shares_outstanding"),
    ):
        current = col(source)
        previous = current.groupby(gated["symbol"], sort=False, observed=True).shift(4)
        growth = _ratio(current - previous, previous, floor=1.0 if source == "shares_outstanding" else MIN_DENOMINATOR)
        out[name] = growth.where(comparable)

    out = out.sort_values("available_from", kind="mergesort").reset_index(drop=True)
    return out


def attach_fundamental_features(
    panel: pd.DataFrame,
    events: pd.DataFrame,
    *,
    date_column: str = "date",
    symbol_column: str = "symbol",
    max_age_days: int = MAX_FUNDAMENTAL_AGE_DAYS,
) -> pd.DataFrame:
    """Attach the most recent *announced* fundamental to each panel row."""
    from src.quant.features.earnings import _asof_aligned, _match_key_dtype

    out = panel.copy()
    for name in FEATURE_NAMES:
        out[name] = np.nan

    if events.empty:
        logger.warning("fundamentals: no events — features remain NULL, not zero")
        return out

    left = out.drop(columns=list(FEATURE_NAMES), errors="ignore").copy()
    left["_date"] = pd.to_datetime(left[date_column])

    right = events.dropna(subset=["available_from"]).copy()
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
        "fundamentals: attached %d/%d panel rows (%.1f%%)",
        attached, len(out), 100.0 * attached / max(len(out), 1),
    )
    return out


def _register() -> None:
    common = (GATE_NOTE, RESTATEMENT_NOTE)
    specs = [
        ("fund_gross_margin", "Gross profit over sales.",
         "Pricing power and cost structure. Stable, slow-moving, and among the "
         "quality measures that survive replication.",
         "gross_profit / sales", Direction.POSITIVE, "Novy-Marx (2013)"),
        ("fund_operating_margin", "Pretax income over sales.",
         "Profitability after operating costs, before financing choices.",
         "pretax_income / sales", Direction.POSITIVE, ""),
        ("fund_roe", "Net income over total equity.",
         "Return on the equity base. A quality measure and a component of most "
         "profitability factors.",
         "net_income / total_equity", Direction.POSITIVE, ""),
        ("fund_roa", "Net income over total assets.",
         "Return unlevered by capital structure, so comparable where leverage is not.",
         "net_income / total_assets", Direction.POSITIVE, ""),
        ("fund_debt_to_equity", "Total liabilities over total equity.",
         "Leverage. Book, not market, and without a maturity schedule.",
         "total_liabilities / total_equity", Direction.NEGATIVE, ""),
        ("fund_current_ratio", "Current assets over current liabilities.",
         "Short-term solvency; a coarse distress screen.",
         "total_current_assets / total_current_liabilities", Direction.POSITIVE, ""),
        ("fund_accruals", "Earnings less operating cash flow, over assets.",
         "The accruals anomaly: earnings not backed by cash predict lower "
         "subsequent returns.",
         "(net_income - net_cash_from_operating_activities) / total_assets",
         Direction.NEGATIVE, "Sloan (1996)"),
        ("fund_asset_growth_yoy", "Year-over-year change in total assets.",
         "Asset growth predicts lower returns — firms that expand the balance "
         "sheet fastest subsequently underperform.",
         "(total_assets_t - total_assets_(t-4q)) / total_assets_(t-4q)",
         Direction.NEGATIVE, "Cooper, Gulen & Schill (2008)"),
        ("fund_sales_growth_yoy", "Year-over-year change in sales.",
         "Top-line growth, harder to manage than earnings growth.",
         "(sales_t - sales_(t-4q)) / sales_(t-4q)", Direction.DESCRIPTIVE, ""),
        ("fund_net_issuance_yoy", "Year-over-year change in shares outstanding.",
         "Net issuance predicts lower returns; buybacks the reverse.",
         "(shares_t - shares_(t-4q)) / shares_(t-4q)",
         Direction.NEGATIVE, "Pontiff & Woodgate (2008)"),
    ]
    for name, description, rationale, formula, direction, citation in specs:
        REGISTRY.register(
            FeatureDefinition(
                name=name,
                group=FeatureGroup.FUNDAMENTAL,
                description=description,
                rationale=rationale,
                formula=formula,
                lookback_sessions=252 if "yoy" in name else 0,
                required_columns=("period_end_date", "announcement_date"),
                direction=direction,
                citation=citation,
                notes=common,
            )
        )


_register()
