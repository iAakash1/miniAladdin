"""
Dataset catalog — what we ingest, what it is worth, and what it may be used for.

Every entry here was **measured against the live source**, not read off a
landing page. Where a number appears below it came from a query whose shape is
recorded in `docs/dataset-catalog.md`, and where a point-in-time claim appears
it was checked against a specific column rather than assumed from the table's
name.

## The field that does the work

`point_in_time` is not documentation. `src/quant/pit/dataset.py` reads it and
**refuses** to admit a `NOT_POINT_IN_TIME` source into a historical training
set unless the caller passes an explicit, named methodology. This is the
difference between a limitation that is recorded and a limitation that is
enforced; only the second one survives contact with a deadline.

Three values, and the distinction between the last two is the one that matters:

``POINT_IN_TIME``
    Each row carries the date on which it became knowable, either because the
    row *is* a dated snapshot (`eps_estimate.date` is the vintage) or because
    the observation is knowable at the moment it describes (a daily close).

``PUBLICATION_LAGGED``
    The row describes a period and does not say when it was published, but a
    defensible publication date is obtainable from another table — for example
    `eps_history` joined to `earnings_calendar`. Usable, with the join stated.

``NOT_POINT_IN_TIME``
    The row describes a period, carries no publication date, and none is
    obtainable. Using it historically backdates today's knowledge into the
    past, which makes results *better* and is therefore the most dangerous
    class of error in this repository. Barred from historical training.

## Why the priority order in the task brief was not taken on faith

The brief proposed A) OHLCV, B) corporate actions, C) earnings, D) estimates,
E) rates, F) options chain, G) volatility history. Measurement moved two of
them:

* **`options.volatility_history` was promoted above `option_chain`.** It is a
  dated snapshot table carrying `iv_current`, `hv_current` and 52-week IV/HV
  extremes — IV rank and the IV-RV spread fall straight out of it, with no
  chain aggregation and no Greeks reconstruction. `option_chain` is 8.58 GB
  and would have to be aggregated per date per symbol to produce weaker
  versions of the same fields.
* **`earnings.income_statement` was demoted below `eps_estimate`.** Its `date`
  is a period marker with no filing date anywhere in the schema, so it is
  `NOT_POINT_IN_TIME` — while this repository *already* has genuinely
  point-in-time fundamentals from SEC XBRL `filed` dates
  (`src/panel/fundamentals.py`). Ingesting a worse version of something we
  already have correctly is negative value, not redundant value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PointInTimeClass(str, Enum):
    POINT_IN_TIME = "point_in_time"
    PUBLICATION_LAGGED = "publication_lagged"
    NOT_POINT_IN_TIME = "not_point_in_time"


class SurvivorshipClass(str, Enum):
    #: Delisted and bankrupt names are present with honest terminal dates.
    COMPLETE = "complete"
    #: Some coverage of exits, incomplete or unverified.
    PARTIAL = "partial"
    #: Only names that survived to today.
    SURVIVORS_ONLY = "survivors_only"
    UNKNOWN = "unknown"


class IngestionMode(str, Enum):
    #: One request per trading date, symbols restricted server-side.
    DATE_PARTITIONED = "date_partitioned"
    #: Small enough to page through in full.
    WHOLE_TABLE = "whole_table"
    #: One request per symbol batch, for tables keyed symbol-first.
    SYMBOL_PARTITIONED = "symbol_partitioned"
    #: Fetched over HTTP from a non-DoltHub publisher.
    HTTP_ARCHIVE = "http_archive"


@dataclass(frozen=True)
class DatasetSpec:
    """One catalog entry: a source, its measured shape, and its permitted use."""

    dataset_id: str
    source: str
    repository: str
    table: str
    description: str

    point_in_time: PointInTimeClass
    point_in_time_note: str
    survivorship: SurvivorshipClass
    survivorship_note: str

    ingestion: IngestionMode
    columns: tuple[str, ...]
    date_column: str = "date"
    symbol_column: Optional[str] = "act_symbol"

    #: Primary-key columns, in key order, as the SOURCE names them.
    #:
    #: Used for keyset pagination, which needs an ordering that is both unique
    #: (so no row is skipped or repeated at a page boundary) and index-backed.
    #: Ordering by a non-key column additionally costs: with projection,
    #: predicate and depth held fixed on `stocks.symbol`, `ORDER BY act_symbol`
    #: measured 2.3 s and 3.7 s across repeats while `ORDER BY act_symbol,
    #: last_seen` measured 5.1 s and 5.2 s. Roughly 2x, and free to avoid —
    #: the key is unique, so a second sort column cannot change the order.
    primary_key: tuple[str, ...] = ("date", "act_symbol")

    #: Measured coverage. `None` where the source is not date-bounded.
    measured_start: Optional[str] = None
    measured_end: Optional[str] = None
    measured_rows_per_date: Optional[int] = None
    measured_symbols: Optional[int] = None

    #: 1 = ingest first. Ordering is justified in the module docstring.
    priority: int = 99
    research_value: str = ""
    limitations: tuple[str, ...] = ()
    licence: str = ""
    url: str = ""
    verification: str = "live-verified"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def historical_training_allowed(self) -> bool:
        """Whether the point-in-time builder will admit this without a waiver."""
        return self.point_in_time is not PointInTimeClass.NOT_POINT_IN_TIME

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "source": self.source,
            "repository": self.repository,
            "table": self.table,
            "description": self.description,
            "point_in_time": self.point_in_time.value,
            "point_in_time_note": self.point_in_time_note,
            "survivorship": self.survivorship.value,
            "survivorship_note": self.survivorship_note,
            "ingestion": self.ingestion.value,
            "columns": list(self.columns),
            "measured_start": self.measured_start,
            "measured_end": self.measured_end,
            "measured_rows_per_date": self.measured_rows_per_date,
            "measured_symbols": self.measured_symbols,
            "priority": self.priority,
            "research_value": self.research_value,
            "limitations": list(self.limitations),
            "licence": self.licence,
            "url": self.url,
            "verification": self.verification,
            "historical_training_allowed": self.historical_training_allowed,
        }


# ── DoltHub: post-no-preference ──────────────────────────────────────────────

STOCKS_OHLCV = DatasetSpec(
    dataset_id="dolthub_stocks_ohlcv",
    source="dolthub",
    repository="stocks",
    table="ohlcv",
    description="Daily unadjusted OHLCV for US equities and ETFs.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "A daily bar is knowable at the close it describes, so as_of == date. "
        "Prices are UNADJUSTED, which is what makes this point-in-time: an "
        "adjusted series silently rewrites history every time a split occurs. "
        "Adjustment is applied downstream by src/quant/pit/adjust.py using only "
        "corporate actions whose ex-date precedes the observation date."
    ),
    survivorship=SurvivorshipClass.COMPLETE,
    survivorship_note=(
        "Delisted names are present with honest terminal bars. Verified directly: "
        "SIVB trades 267.83 on 2023-03-08, 106.04 on 2023-03-09, and then stops — "
        "the day trading was halted. Its symbol row carries financial_status="
        "'Bankrupt'. Symbol count rises 3,844 (2011) -> 12,470 (2026), consistent "
        "with names entering and leaving rather than a survivor snapshot."
    ),
    ingestion=IngestionMode.DATE_PARTITIONED,
    columns=("date", "act_symbol", "open", "high", "low", "close", "volume"),
    measured_start="2011-01-03",
    measured_end="2026-08-21",
    measured_rows_per_date=12470,
    measured_symbols=24058,
    priority=1,
    research_value=(
        "Removes the two constraints docs/PANEL.md names as binding: ~501 bars of "
        "vendor depth (§5.2) and survivors-only universes (§5.1). 15.6 years of "
        "daily bars is the difference between one usable year of panel and fifteen."
    ),
    limitations=(
        "No adjusted close: splits and dividends must be applied from the "
        "companion tables, which is a feature for point-in-time work and a cost "
        "for convenience.",
        "No intraday data, no bid/ask, no exchange venue.",
        "Volume is not adjusted for splits; the adjustment layer handles it.",
    ),
    licence="Open data on DoltHub; sourced from public end-of-day feeds.",
    url="https://www.dolthub.com/repositories/post-no-preference/stocks",
)

STOCKS_SPLIT = DatasetSpec(
    dataset_id="dolthub_stocks_split",
    source="dolthub",
    repository="stocks",
    table="split",
    description="Stock split ex-dates with to/for factors.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "ex_date is the date the split takes effect and is knowable then. "
        "Splits are announced before the ex-date, so treating the ex-date as the "
        "availability time is conservative — it never reveals a split early."
    ),
    survivorship=SurvivorshipClass.COMPLETE,
    survivorship_note="Keyed by symbol; delisted symbols retain their actions.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("act_symbol", "ex_date", "to_factor", "for_factor"),
    date_column="ex_date",
    measured_start="2014-03-28",
    measured_end="2026-08-21",
    priority=2,
    research_value=(
        "Without splits a 4:1 split reads as a -75% single-day return, which "
        "manufactures the largest reversal signal in the sample out of nothing."
    ),
    limitations=(
        "**Coverage starts 2014-03-28, while ohlcv starts 2011-01-03.** Measured, "
        "not assumed: the earliest ex_date in the whole table is 2014-03-28 across "
        "3,993 rows. Any return computed before that date is therefore "
        "split-contaminated, and a 2011-2014 study would carry fabricated "
        "single-day moves of -50% to -80% wherever a split occurred. "
        "`src/quant/pit/dataset.py` refuses to build training rows before "
        "CORPORATE_ACTION_COVERAGE_START for this reason, rather than reporting "
        "the contaminated years with a footnote.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/stocks",
    primary_key=("act_symbol", "ex_date"),
)

STOCKS_DIVIDEND = DatasetSpec(
    dataset_id="dolthub_stocks_dividend",
    source="dolthub",
    repository="stocks",
    table="dividend",
    description="Cash dividend ex-dates and amounts.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note="ex_date is knowable on the ex-date; see the split note.",
    survivorship=SurvivorshipClass.COMPLETE,
    survivorship_note="Keyed by symbol; delisted symbols retain their actions.",
    ingestion=IngestionMode.SYMBOL_PARTITIONED,
    columns=("act_symbol", "ex_date", "amount"),
    date_column="ex_date",
    priority=2,
    research_value=(
        "Separates price return from total return. A high-yield name looks like "
        "a chronic underperformer on price alone."
    ),
    limitations=(
        "494,438 rows measured — too large to page whole, and the table is keyed "
        "symbol-first, so it is fetched per symbol batch for the research "
        "universe rather than in full.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/stocks",
    primary_key=("act_symbol", "ex_date"),
)

STOCKS_SYMBOL = DatasetSpec(
    dataset_id="dolthub_stocks_symbol",
    source="dolthub",
    repository="stocks",
    table="symbol",
    description="Security master: name, exchange, ETF flag, financial status, last_seen.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "This is a CURRENT snapshot of the security master, not a history of it. "
        "`last_seen` is the one genuinely historical field and it is used only as "
        "a delisting bound: a symbol may not enter a universe after last_seen. "
        "The descriptive fields (name, exchange, is_etf) are treated as static; "
        "that assumption is recorded, and it is why this is not POINT_IN_TIME."
    ),
    survivorship=SurvivorshipClass.COMPLETE,
    survivorship_note=(
        "24,058 rows with last_seen spanning 2017-10-26 -> 2026-08-22. Delisted "
        "names verified present: TWTR (2022-10-23), ABMD (2022-12-18), SIVB and "
        "SBNY (2023-03-26, financial_status='Bankrupt'), FRC (2023-04-30), "
        "ATVI (2023-10-08), SPLK (2024-03-17)."
    ),
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=(
        "act_symbol", "security_name", "listing_exchange", "market_category",
        "is_etf", "is_test_issue", "financial_status", "last_seen",
    ),
    date_column="last_seen",
    measured_symbols=24058,
    priority=1,
    research_value=(
        "The delisting bound is what makes a survivorship-free universe possible. "
        "is_etf separates funds from operating companies, which otherwise pollute "
        "any cross-sectional fundamental study."
    ),
    limitations=(
        "last_seen begins 2017-10-26, so exits before that date are not dated by "
        "this table. Universes built earlier than 2017 fall back to price-activity "
        "evidence and are marked PARTIAL rather than COMPLETE.",
        "Descriptive fields are current values applied to history.",
    ),
    licence="Open data on DoltHub; derived from Nasdaq's published symbol files.",
    url="https://www.dolthub.com/repositories/post-no-preference/stocks",
    primary_key=("act_symbol",),
)

RATES_TREASURY = DatasetSpec(
    dataset_id="dolthub_rates_us_treasury",
    source="dolthub",
    repository="rates",
    table="us_treasury",
    description="Daily US Treasury par yield curve, 1M to 30Y.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "Treasury publishes the par yield curve after the close of the day it "
        "describes. The ingestion records publication as date + 1 business day, "
        "which is conservative: a same-day model never sees that day's curve."
    ),
    survivorship=SurvivorshipClass.COMPLETE,
    survivorship_note="Not applicable — a single national curve, no cross-section.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=(
        "date", "1_month", "3_month", "6_month", "1_year", "2_year",
        "3_year", "5_year", "7_year", "10_year", "20_year", "30_year",
    ),
    symbol_column=None,
    measured_start="1990-01-02",
    measured_end="2026-08-28",
    priority=3,
    research_value=(
        "9,158 rows covering 36 years for 12.7 MB — the cheapest macro state "
        "available. Level, slope and curvature are the standard rates-regime "
        "descriptors and all three come from this one table."
    ),
    limitations=(
        "Nominal yields only; no TIPS, so real yields are not derivable here.",
        "Short tenors are sparse before 2001 (the 1-month series starts then).",
    ),
    licence="US Treasury publication, public domain.",
    url="https://www.dolthub.com/repositories/post-no-preference/rates",
    primary_key=("date",),
)

OPTIONS_VOLATILITY = DatasetSpec(
    dataset_id="dolthub_options_volatility_history",
    source="dolthub",
    repository="options",
    table="volatility_history",
    description="Dated implied and historical volatility snapshots with 52-week extremes.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "Each row IS a snapshot: `iv_current` is the implied volatility observed "
        "on `date`, and the year high/low columns describe the trailing year as "
        "at that date. Nothing in the row describes the future, and the "
        "*_year_high_date / *_year_low_date columns are backward-looking bounds."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note=(
        "Covers optionable names only — 531 symbols in 2019 rising to ~1,530 in "
        "2026. Membership in that set is itself a liquidity filter, so studies "
        "restricted to it are not representative of the full cross-section."
    ),
    ingestion=IngestionMode.DATE_PARTITIONED,
    columns=(
        "date", "act_symbol", "hv_current", "hv_week_ago", "hv_month_ago",
        "hv_year_high", "hv_year_low", "iv_current", "iv_week_ago",
        "iv_month_ago", "iv_year_high", "iv_year_low",
    ),
    measured_start="2019-02-09",
    measured_end="2026-08-28",
    measured_rows_per_date=1531,
    priority=4,
    research_value=(
        "IV rank, IV percentile and the implied-minus-realised spread fall "
        "directly out of these columns. The volatility risk premium is the most "
        "durable documented effect in options data and this is the cheapest "
        "honest measurement of it available."
    ),
    limitations=(
        "Cadence is irregular: weekly (Saturdays) from 2019 to roughly 2021, "
        "daily afterwards. Features must not assume a uniform grid.",
        "No term structure and no skew — those need the option chain.",
        "The provider's IV methodology is not published, so the level is a "
        "vendor measurement rather than a reconstructible quantity.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/options",
)

EARNINGS_EPS_ESTIMATE = DatasetSpec(
    dataset_id="dolthub_earnings_eps_estimate",
    source="dolthub",
    repository="earnings",
    table="eps_estimate",
    description="Analyst EPS consensus by vintage date and forecast period.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "The rare and valuable case. `date` is the VINTAGE — what consensus was "
        "on that day — and `period_end_date` is what it forecasts. That pair is "
        "what makes estimate revisions computable without lookahead. Most free "
        "estimate data carries only the current consensus, which backdates "
        "today's revised view across the whole history."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="Covered names are those with analyst coverage on each vintage date.",
    ingestion=IngestionMode.DATE_PARTITIONED,
    columns=(
        "date", "act_symbol", "period", "period_end_date",
        "consensus", "recent", "count", "high", "low", "year_ago",
    ),
    measured_start="2017-10-26",
    measured_end="2026-08-28",
    priority=5,
    research_value=(
        "Estimate revision is among the better-documented cross-sectional "
        "predictors, and it is only measurable with vintages. `high`/`low`/`count` "
        "additionally give analyst dispersion, a disagreement proxy."
    ),
    limitations=(
        "Starts 2017-10-26, so it covers roughly half the OHLCV history.",
        "Vintage cadence is irregular; revisions must be computed against the "
        "previous available vintage, not a fixed lag.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

EARNINGS_CALENDAR = DatasetSpec(
    dataset_id="dolthub_earnings_calendar",
    source="dolthub",
    repository="earnings",
    table="earnings_calendar",
    description="Earnings announcement dates and session timing.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "An announcement date is a fact about when information arrived, which is "
        "exactly what a publication date is. It is PUBLICATION_LAGGED rather than "
        "POINT_IN_TIME because the table is a current snapshot that also contains "
        "FUTURE scheduled dates — a naive read leaks the knowledge that a company "
        "is about to report. Consumers must bound it at the observation date."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="Coverage follows the estimate universe.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("act_symbol", "date", "when"),
    priority=6,
    research_value=(
        "Supplies the announcement date that turns eps_history from "
        "NOT_POINT_IN_TIME into something usable, and gates any earnings-window "
        "feature."
    ),
    primary_key=("act_symbol", "date"),
    measured_start="2020-01-22",
    measured_end="2026-10-01",
    limitations=(
        "**Contains 263 future-dated rows** (measured 2026-08-29: max date "
        "2026-10-01). Must be bounded by the observation cutoff or it leaks the "
        "knowledge that a company is about to report — which is itself tradeable.",
        "Starts 2020-01-22, so earnings features are unavailable before then even "
        "though price history reaches 2011.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

EARNINGS_INCOME_STATEMENT = DatasetSpec(
    dataset_id="dolthub_earnings_income_statement",
    source="dolthub",
    repository="earnings",
    table="income_statement",
    description="Quarterly and annual income statement lines.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "RECLASSIFIED for EXP-005, from NOT_POINT_IN_TIME. `date` is a fiscal "
        "PERIOD END, not a filing date — verified on AAPL, where the quarter "
        "ending 2026-06-30 was announced 2026-07-30, and where 270,888 of "
        "270,925 rows fall on a month end. The original BARRED classification "
        "was correct at the time, because nothing gated it. "
        "What changed is the gate, not the data: src/quant/features/"
        "fundamentals.py joins every period forward to its first "
        "`earnings_calendar` announcement and emits nothing for a period whose "
        "announcement cannot be established — the mechanism that has governed "
        "`eps_history` since EXP-002. Two tables of the same shape now carry the "
        "same class. "
        "The TIMING leak is closed. The RESTATEMENT leak is NOT: one row per "
        "period, no vintage column, so a later correction overwrites the "
        "original irrecoverably. Features derived here are marked "
        "restatement_risk=UNQUANTIFIED and isolated in their own ablation arm so "
        "their contribution can be measured and discounted separately. "
        "src/panel/fundamentals.py remains strictly better wherever SEC "
        "companyfacts can be fetched, because it carries real `filed` dates."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note=(
        "9,292 symbols from 2012-10-31. Filers that stop filing stop appearing; "
        "there is no explicit termination marker, so exits are inferred from the "
        "price panel rather than from this table."
    ),
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("act_symbol", "date", "period", "sales", "cost_of_goods",
             "gross_profit", "pretax_income", "net_income", "average_shares",
             "diluted_net_eps", "depreciation_and_amortization", "interest_expense"),
    primary_key=("date", "act_symbol", "period"),
    measured_start="2012-10-31",
    measured_end="2026-07-31",
    measured_symbols=9292,
    priority=3,
    research_value=(
        "Margins, profitability and their trends — the quality and growth legs "
        "of the cross-section, none of which is recoverable from price. "
        "Admissible only through the announcement gate, and only with the "
        "restatement caveat attached."
    ),
    limitations=(
        "No filing date in the table: availability comes entirely from "
        "`earnings_calendar`, which begins 2020-01-22. Periods before that "
        "cannot be gated and are dropped rather than assumed.",
        "No restatement history. A restated figure silently replaces the "
        "original and the magnitude of that effect cannot be measured from this "
        "table alone. UNQUANTIFIED.",
        "Quarterly rows for some filers are year-to-date cumulative rather than "
        "discrete.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

OPTIONS_CHAIN = DatasetSpec(
    dataset_id="dolthub_options_option_chain",
    source="dolthub",
    repository="options",
    table="option_chain",
    description="Full US equity option chains with bid/ask, IV and Greeks.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note="Each row is a dated quote snapshot; nothing describes the future.",
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="Optionable names only.",
    ingestion=IngestionMode.DATE_PARTITIONED,
    columns=(
        "date", "act_symbol", "expiration", "strike", "call_put",
        "bid", "ask", "vol", "delta", "gamma", "theta", "vega", "rho",
    ),
    priority=8,
    research_value=(
        "The only source here for term structure and skew. Deferred, not "
        "rejected: at 8.58 GB a single date is thousands of rows per symbol, and "
        "volatility_history already supplies IV level, IV rank and the IV-RV "
        "spread at a fraction of the cost. Ingesting the chain before those are "
        "shown to carry signal would be paying the largest engineering cost in "
        "the catalog for an unmeasured return."
    ),
    limitations=(
        "8.58 GB; needs per-date, per-symbol partitioning and a strike/expiry "
        "filter to be tractable.",
        "Greeks are vendor-supplied under an unpublished model; they are "
        "measurements, not reconstructions.",
        "No open interest column, so several classic positioning proxies are not "
        "computable from it.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/options",
    verification="schema-verified (not ingested)",
)

# ── Non-DoltHub sources ──────────────────────────────────────────────────────

FRENCH_FACTORS = DatasetSpec(
    dataset_id="french_factors_daily",
    source="kenneth_french_data_library",
    repository="tuck.dartmouth.edu",
    table="F-F_Research_Data_5_Factors_2x3_daily + F-F_Momentum_Factor_daily",
    description="Daily Fama-French 5 factors, the risk-free rate, and the momentum factor.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "Factor returns for a day describe that day and are published with a lag "
        "of weeks. The series is also periodically revised when CRSP is revised, "
        "so this is a REVISED series and is marked as such. It is admitted for "
        "one specific use — evaluating a strategy's exposure after the fact — and "
        "barred from features. Revision affects the benchmark's level, not the "
        "strategy's returns, so an attribution computed on it is defensible in a "
        "way a feature built from it would not be."
    ),
    survivorship=SurvivorshipClass.COMPLETE,
    survivorship_note="CRSP-based; constructed from the full historical cross-section.",
    ingestion=IngestionMode.HTTP_ARCHIVE,
    columns=("date", "mkt_rf", "smb", "hml", "rmw", "cma", "rf", "mom"),
    symbol_column=None,
    measured_start="1963-07-01",
    measured_end="2026-06-30",
    priority=3,
    research_value=(
        "The single most important non-price source here, because it is what "
        "makes one specific word usable. A strategy's return minus a benchmark's "
        "is a RETURN DIFFERENCE. Only a regression of strategy returns on these "
        "factors produces an intercept that can be called alpha, and this "
        "repository's stated terminology standard requires exactly that "
        "distinction. Also answers 'does the model add information beyond simple "
        "factors' directly rather than by assertion."
    ),
    limitations=(
        "Revised series; not usable as a feature input.",
        "US-only, and the factor definitions are Fama-French's, not ours.",
        "Ends at the library's last publication, which lags the price data.",
    ),
    licence=(
        "Provided free for research use by Kenneth R. French. Copyright Eugene F. "
        "Fama and Kenneth R. French. Redistribution of the raw files is not "
        "assumed; the ingestion fetches from source and stores locally."
    ),
    url="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
)


#: The same table as :data:`STOCKS_OHLCV`, sampled monthly across the WHOLE
#: market rather than daily across a chosen universe.
#:
#: This exists to break a circularity. A survivorship-free universe has to be
#: chosen from what was liquid at each point in the past, but liquidity comes
#: from the price table, and pulling the price table for 24,058 symbols to pick
#: 500 of them is exactly the waste the date-partitioned design avoids. One
#: full-market cross-section per month is ~12 paginated requests; 187 of them
#: cover 2011-2026 and are enough to rank names by dollar volume at every
#: month-end. The daily ingestion then runs only over names that were actually
#: eligible.
STOCKS_OHLCV_MONTHLY = DatasetSpec(
    dataset_id="dolthub_stocks_ohlcv_monthly",
    source="dolthub",
    repository="stocks",
    table="ohlcv",
    description="Whole-market month-end OHLCV cross-sections, for universe construction.",
    point_in_time=STOCKS_OHLCV.point_in_time,
    point_in_time_note=STOCKS_OHLCV.point_in_time_note,
    survivorship=STOCKS_OHLCV.survivorship,
    survivorship_note=(
        "Whole-market by construction: every symbol trading on the sampled date "
        "is present, so a universe ranked from it contains the names that were "
        "actually eligible then, including those that later failed."
    ),
    ingestion=IngestionMode.DATE_PARTITIONED,
    columns=STOCKS_OHLCV.columns,
    measured_start=STOCKS_OHLCV.measured_start,
    measured_end=STOCKS_OHLCV.measured_end,
    measured_rows_per_date=STOCKS_OHLCV.measured_rows_per_date,
    priority=1,
    research_value=(
        "The input to point-in-time universe membership, which docs/PANEL.md §5.1 "
        "records as having no free source. It does now."
    ),
    limitations=(
        "Monthly cadence: a name that listed and delisted inside one month is "
        "never sampled and cannot enter a universe.",
        "Dollar volume on a single day is a noisy liquidity estimate; the "
        "universe builder smooths it across sampled months.",
    ),
    licence=STOCKS_OHLCV.licence,
    url=STOCKS_OHLCV.url,
)


OPTIONS_CHAIN_DAILY = DatasetSpec(
    dataset_id="dolthub_options_chain_daily",
    source="dolthub_local_clone",
    repository="options",
    table="option_chain",
    description="Per (date, symbol) option-chain aggregates: ATM IV, 25-delta skew, term slope, spread.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "Each row aggregates quotes observed on `date`. Nothing in it describes a "
        "later date: the near/far split is by time to expiry measured FROM `date`, "
        "which is forward-looking about the option's life and backward-looking about "
        "information — an expiry is known when the contract is listed."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note=(
        "Optionable names only — 2,317 symbols. Membership in that set is itself a "
        "liquidity and size filter, so studies restricted to it are not "
        "representative of the full cross-section."
    ),
    ingestion=IngestionMode.DATE_PARTITIONED,
    columns=(
        "date", "act_symbol", "contracts", "expirations", "atm_iv",
        "put_25_iv", "call_25_iv", "atm_iv_near", "atm_iv_far", "rel_spread",
    ),
    primary_key=("date", "act_symbol"),
    measured_start="2019-02-09",
    measured_end="2026-08-28",
    measured_rows_per_date=None,
    priority=4,
    research_value=(
        "The only source here for SKEW and TERM STRUCTURE. `volatility_history` "
        "already supplies IV level, IV rank and the IV-RV spread, so the chain is "
        "ingested for what that table cannot express: the 25-delta put/call IV "
        "difference, and the near-versus-far ATM IV slope. Aggregating inside Dolt "
        "means 116,487,570 raw rows never cross the process boundary — a year "
        "reduces to ~278,000 rows in ~88 s."
    ),
    limitations=(
        "**Irregular cadence.** Distinct dates per year: 48 (2019), 155 (2020), "
        "156 (2021), 151 (2022), 155 (2023), 183 (2024), 259 (2025). Roughly weekly "
        "early and daily late, so features must not assume a uniform grid and must "
        "be joined as 'latest available on or before'.",
        "Snapshot dates do not always fall on trading days — 2024-01-01 is a market "
        "holiday and carries 93,956 rows. Alignment to the trading calendar is the "
        "consumer's responsibility.",
        "No volume and no open interest columns, so put/call ratios and every "
        "positioning proxy that needs them are NOT computable from this source.",
        "Greeks and IV are vendor-supplied under an unpublished model; they are "
        "measurements, not reconstructions.",
        "Delta buckets are wide (0.45-0.55 for ATM, 0.20-0.30 for 25-delta) because "
        "listed strikes are discrete — an exact-delta interpolation would imply a "
        "precision the strike grid does not support.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/options",
)

EARNINGS_EPS_HISTORY = DatasetSpec(
    dataset_id="dolthub_earnings_eps_history",
    source="dolthub_local_clone",
    repository="earnings",
    table="eps_history",
    description="Reported EPS against the estimate that stood into the print, by fiscal period.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "Keyed (act_symbol, period_end_date) with NO announcement date, so on its "
        "own it is not usable: the row for a quarter ending 2026-06-30 is dated "
        "2026-06-30, while the figure became public on 2026-07-30 — a 30-day leak, "
        "verified directly on AAPL. It becomes usable ONLY when joined to "
        "`earnings_calendar` to recover the announcement date, and "
        "src/quant/features/earnings.py performs exactly that join and drops any "
        "period whose announcement date cannot be established."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="7,029 symbols; coverage follows analyst coverage.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("act_symbol", "period_end_date", "reported", "estimate"),
    primary_key=("act_symbol", "period_end_date"),
    date_column="period_end_date",
    priority=5,
    research_value=(
        "Earnings surprise and post-earnings-announcement drift are among the most "
        "replicated cross-sectional effects there are, and `reported - estimate` is "
        "the surprise directly. This is the highest-value non-price feature source "
        "in the corpus."
    ),
    limitations=(
        "No announcement date of its own — unusable without the earnings_calendar join.",
        "168,473 rows; a single estimate per period, not a vintage series.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)



# ── DoltHub earnings: the tables the first study left on the table ───────────
#
# All five are keyed by FISCAL PERIOD END, not by publication date. Verified on
# AAPL: the quarter ending 2026-06-30 was announced 2026-07-30, and the quarter
# ending 2025-12-31 was announced 2026-01-29 — a 29-30 day lag, and 270,888 of
# 270,925 `income_statement` rows fall on a month end. Treating `date` as an
# availability date would grant a model a month of hindsight on every quarterly
# figure, which is why each carries PUBLICATION_LAGGED and why the feature layer
# refuses to emit them without an announcement date from `earnings_calendar`.

EARNINGS_SALES_ESTIMATE = DatasetSpec(
    dataset_id="dolthub_earnings_sales_estimate",
    source="dolthub",
    repository="earnings",
    table="sales_estimate",
    description="Weekly analyst revenue-estimate vintages: consensus, dispersion, coverage.",
    point_in_time=PointInTimeClass.POINT_IN_TIME,
    point_in_time_note=(
        "`date` is the OBSERVATION date of the estimate, not the period it "
        "describes — the row says what analysts believed on that Sunday. "
        "Verified on AAPL for period_end_date 2026-06-30: consensus holds at "
        "1.70 from 2026-02-01, moves to 1.68 on 2026-04-12 and 1.73 on "
        "2026-04-19. A revision series is therefore recoverable without any "
        "hindsight, which is what makes this the one fundamental-adjacent table "
        "needing no announcement gate."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note=(
        "Coverage begins 2017-10-26 and tracks 7,029 symbols. Names that lost "
        "analyst coverage stop appearing, so the estimate panel thins before a "
        "delisting rather than ending abruptly."
    ),
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("date", "act_symbol", "period", "period_end_date", "consensus",
             "count", "high", "low", "year_ago"),
    primary_key=("date", "act_symbol", "period"),
    measured_start="2017-10-26",
    measured_end="2026-08-23",
    measured_rows_per_date=None,
    measured_symbols=7029,
    priority=2,
    research_value=(
        "Revenue-estimate revisions are the second leg of the revisions anomaly "
        "and are not recoverable from price. 7,060,412 vintages at a weekly "
        "cadence over 8.8 years."
    ),
    limitations=(
        "Weekly, so a revision is located to within a week and no finer.",
        "`period` is relative ('Current Quarter', 'Next Year'), so the target "
        "period moves as time passes; period_end_date is the stable key.",
        "No revision timestamp within the week, and no per-analyst detail.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

EARNINGS_BALANCE_ASSETS = DatasetSpec(
    dataset_id="dolthub_earnings_balance_sheet_assets",
    source="dolthub",
    repository="earnings",
    table="balance_sheet_assets",
    description="Quarterly and annual asset-side balance sheet, keyed by fiscal period end.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "`date` is the FISCAL PERIOD END. The figure was not public until the "
        "results were announced, typically 30-90 days later. Usable only after "
        "an as-of join to `earnings_calendar`; periods with no matching "
        "announcement are dropped, never estimated."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note=(
        "9,998 symbols from 2012-10-31. Filers that stop filing simply stop "
        "appearing; there is no explicit termination marker in this table."
    ),
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("date", "act_symbol", "period", "cash_and_equivalents", "receivables",
             "inventories", "total_current_assets", "net_property_and_equipment",
             "intangibles", "total_assets"),
    primary_key=("date", "act_symbol", "period"),
    measured_start="2012-10-31",
    measured_end="2026-07-31",
    measured_symbols=9998,
    priority=3,
    research_value=(
        "Asset composition supports accruals and asset-growth measures, both "
        "documented cross-sectional effects that price data cannot express."
    ),
    limitations=(
        "No publication date in the table; availability comes entirely from "
        "`earnings_calendar`, which starts 2020-01-22.",
        "One row per period with no vintage column, so a restatement OVERWRITES "
        "the original figure and the original is unrecoverable.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

EARNINGS_BALANCE_LIABILITIES = DatasetSpec(
    dataset_id="dolthub_earnings_balance_sheet_liabilities",
    source="dolthub",
    repository="earnings",
    table="balance_sheet_liabilities",
    description="Quarterly and annual liability-side balance sheet, keyed by fiscal period end.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "Fiscal period end, identical treatment to the asset side: gated on "
        "`earnings_calendar` or not emitted."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="Same filer-attrition behaviour as the asset side.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("date", "act_symbol", "period", "accounts_payable",
             "total_current_liabilities", "long_term_debt", "total_liabilities"),
    primary_key=("date", "act_symbol", "period"),
    measured_start="2012-10-31",
    measured_end="2026-07-31",
    measured_symbols=9998,
    priority=3,
    research_value="Leverage and its change; the denominator for balance-sheet quality.",
    limitations=(
        "No publication date; no restatement vintage.",
        "Debt is book, not market, and carries no maturity schedule.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

EARNINGS_BALANCE_EQUITY = DatasetSpec(
    dataset_id="dolthub_earnings_balance_sheet_equity",
    source="dolthub",
    repository="earnings",
    table="balance_sheet_equity",
    description="Quarterly and annual equity, shares outstanding and book value per share.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "Fiscal period end. `shares_outstanding` and `book_value_per_share` are "
        "as of the period end and became public at the announcement."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="Same filer-attrition behaviour as the rest of the statement set.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("date", "act_symbol", "period", "common_stock", "retained_earnings",
             "treasury_stock", "total_equity", "shares_outstanding",
             "book_value_per_share"),
    primary_key=("date", "act_symbol", "period"),
    measured_start="2012-10-31",
    measured_end="2026-07-31",
    measured_symbols=9998,
    priority=3,
    research_value=(
        "`book_value_per_share` against price is book-to-market, the oldest "
        "documented value measure and the one HML is built from. "
        "`shares_outstanding` gives net issuance."
    ),
    limitations=(
        "No publication date; no restatement vintage.",
        "Shares outstanding is period-end, so buybacks inside a quarter are invisible.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

EARNINGS_CASH_FLOW = DatasetSpec(
    dataset_id="dolthub_earnings_cash_flow_statement",
    source="dolthub",
    repository="earnings",
    table="cash_flow_statement",
    description="Quarterly and annual cash-flow statement, keyed by fiscal period end.",
    point_in_time=PointInTimeClass.PUBLICATION_LAGGED,
    point_in_time_note=(
        "Fiscal period end; announcement-gated like the rest of the statement set."
    ),
    survivorship=SurvivorshipClass.PARTIAL,
    survivorship_note="9,513 symbols from 2012-10-31, with the same filer attrition.",
    ingestion=IngestionMode.WHOLE_TABLE,
    columns=("date", "act_symbol", "period", "net_income",
             "net_cash_from_operating_activities", "property_and_equipment",
             "net_cash_from_investing_activities", "net_cash_from_financing_activities",
             "payment_of_dividends_and_other_distributions"),
    primary_key=("date", "act_symbol", "period"),
    measured_start="2012-10-31",
    measured_end="2026-07-31",
    measured_symbols=9513,
    priority=3,
    research_value=(
        "Operating cash flow less capex is free cash flow, and accruals — the "
        "gap between earnings and cash — is among the better-replicated "
        "cross-sectional predictors."
    ),
    limitations=(
        "No publication date; no restatement vintage.",
        "Quarterly cash-flow figures are sometimes cumulative year-to-date "
        "rather than discrete; the feature layer differences them and drops "
        "the first quarter of each year where the convention is ambiguous.",
    ),
    licence="Open data on DoltHub.",
    url="https://www.dolthub.com/repositories/post-no-preference/earnings",
)

CATALOG: tuple[DatasetSpec, ...] = (
    OPTIONS_CHAIN_DAILY,
    EARNINGS_EPS_HISTORY,
    STOCKS_OHLCV_MONTHLY,
    STOCKS_OHLCV,
    STOCKS_SYMBOL,
    STOCKS_SPLIT,
    STOCKS_DIVIDEND,
    RATES_TREASURY,
    FRENCH_FACTORS,
    OPTIONS_VOLATILITY,
    EARNINGS_EPS_ESTIMATE,
    EARNINGS_CALENDAR,
    OPTIONS_CHAIN,
    EARNINGS_INCOME_STATEMENT,
    EARNINGS_SALES_ESTIMATE,
    EARNINGS_BALANCE_ASSETS,
    EARNINGS_BALANCE_LIABILITIES,
    EARNINGS_BALANCE_EQUITY,
    EARNINGS_CASH_FLOW,
)

_BY_ID = {spec.dataset_id: spec for spec in CATALOG}


def get(dataset_id: str) -> DatasetSpec:
    if dataset_id not in _BY_ID:
        raise KeyError(f"unknown dataset {dataset_id!r}; known: {sorted(_BY_ID)}")
    return _BY_ID[dataset_id]


def by_priority(max_priority: int = 99) -> list[DatasetSpec]:
    return sorted(
        (spec for spec in CATALOG if spec.priority <= max_priority),
        key=lambda spec: (spec.priority, spec.dataset_id),
    )


def training_admissible() -> list[DatasetSpec]:
    """Datasets the point-in-time builder will accept without a named waiver."""
    return [spec for spec in CATALOG if spec.historical_training_allowed]


def catalog_payload() -> list[dict[str, Any]]:
    """Serialisable catalog for the API and the data-quality surface."""
    return [spec.as_dict() for spec in by_priority()]
