# Detailed local research-data inventory

Audit date: 2026-09-19. Inspection used manifests, Parquet metadata and key
columns only; no multi-gigabyte contract table was loaded into memory. Raw Dolt
clones total about 14 GB; normalized research Parquet is about 219 MB.

## Important interpretation

The current selected EXP-006 model uses 27 price/volume/volatility/macro
features. Richer families are locally present **and already have point-in-time
feature builders**, but they are not wholly untested: EXP-005's fixed feature-
arm ablation found `C_base` IC 0.0290 versus 0.0275 with options, 0.0229 with
estimates, 0.0124 with earnings/fundamentals, and 0.0151 with all families.
Thus the gap is not “we never tried these files.” It is “the selected model
does not use them, and the first additive specification did not add signal.”
Any revisit must change one preregistered design axis at a time.

## Normalized inventory

| Dataset / exact files | Schema summary | Rows / names / dates | Nulls and duplicates | Availability/PIT | Usability |
|---|---|---|---|---|---|
| `dolthub_stocks_ohlcv/part-YYYY.parquet` | date, symbol, OHLC, volume | 2,910,092; 2012-01-03--2026-08-28; 657--901 names/year | Manifest-controlled; no adjusted close | Close-date observation; actions applied downstream | READY core; earlier delisting metadata partial |
| `dolthub_stocks_split/part-all.parquet` | symbol, ex-date, factors | 3,993; 2014-03-28--2026-08-21 | Keyed event rows | Ex-date PIT | READY, but pre-2014 adjustments need caution |
| `dolthub_stocks_dividend/part-all.parquet` | symbol, ex-date, amount | 494,438; 1970-01-19--2026-08-21 | Manifest-controlled | Ex-date PIT | READY for total-return adjustment |
| `dolthub_earnings_eps_estimate/part-all.parquet` | vintage date, symbol, relative period, period end, consensus/recent/count/high/low/year-ago | 7,060,412; 7,029 names; 483 vintages; 2017-10-26--2026-08-23 | 0 duplicate `(date,symbol,period,period_end)` keys; consensus 4.60% null, count 4.57%, recent 27.58% | `date` is weekly consensus vintage; no analyst id | READY for consensus revisions, not analyst-level stickiness |
| `dolthub_earnings_sales_estimate/part-all.parquet` | same, without `recent` | 7,060,412; 7,029 names; 483 vintages | 0 duplicate keys; consensus 12.30% null; count/high/low 13.58% | Observation-dated vintage | READY with explicit missingness |
| `dolthub_earnings_eps_history/part-all.parquet` | symbol, period end, reported, estimate | 168,473; 7,029 names | 0 duplicate `(symbol,period_end)`; reported 6.36% null; estimate 13.98% | Period-dated alone; must join announcement | RESEARCH_ONLY behind calendar gate |
| `dolthub_earnings_calendar/part-all.parquet` | symbol, date, before/after marker | 117,601; 7,359 names; 2020-01-22--2026-10-01 | 0 duplicate `(symbol,date)`; symbol 0.009% null; `when` 25.17% null | Event date; unknown session treated as after-close; scheduled future rows are not “known since” dates | Gate for realized earnings; cannot build `days_to_next_earnings` |
| Statement Parquets: income, assets, liabilities, equity, cash flow | period date, symbol, period, statement fields | 176,631--284,716 rows/table; 9,291--9,997 names; 2012-10-31--2026-07-31 | 0 duplicate income `(symbol,date,period)`; core field nulls mostly <8%, D&A 74.97% | Period end is not publication; joined forward to first plausible earnings announcement | RESEARCH_ONLY; unquantified restatement contamination |
| `dolthub_options_volatility_history/part-YYYY.parquet` | date, symbol, historical/implied vol current/week/month/year extrema | 691,007; 745 names; 1,222 dates; 2019-05-10--2026-08-28 | 0 duplicate `(date,symbol)`; IV current 1.93% null; month-ago 51.60% null | Snapshot dated; IV vendor model unpublished | RESEARCH_ONLY; partial optionable universe |
| `dolthub_options_chain_daily/part-YYYY.parquet` | daily symbol aggregates: contracts/expirations/strikes, ATM/25-delta/near/far IV, spread | 1,918,396; 2,317 names; 1,276 dates; 2019-02-09--2026-08-28 | 0 duplicate `(date,symbol)`; ATM IV 28.58% null; near 38.26%; far 52.74%; spread 0.04% | Aggregated from 116,487,570 contract rows; latest-on-or-before join, 21-day cap | RESEARCH_ONLY; no volume/open interest, irregular cadence, only ~2019 onward |
| `dolthub_rates_us_treasury/part-all.parquet` | daily 1m--30y Treasury curve | 9,158; 1990-01-02--2026-08-28 | Manifest-controlled | One-session lag in model | READY, but ALFRED needed for revised macro series beyond Treasury curve |
| `french_factors_daily/part-all.parquet` | FF5 + momentum + RF | 15,854; 1963-07-01--2026-06-30 | Manifest-controlled | Evaluation series, publication lag | READY for attribution; raw redistribution not assumed |

The options manifest originally lists partition metadata as `columns`; direct
Parquet schema inspection confirms the aggregate feature columns shown above.

## Existing feature preparation (already implemented)

| Module | Features | PIT defense | Current status |
|---|---|---|---|
| `src/quant/features/estimates.py` | 4/13-week EPS and sales revisions, dispersion, coverage, expected growth | Backward vintage differences; fiscal-roll changes become null; 45-day staleness | Implemented and tested; EXP-005 arm underperformed |
| `src/quant/features/earnings.py` | surprise, surprise %, SUE, sign, days since | Forward match period to announcement; after-close moves to next session; missing match dropped | Implemented and tested; calendar only since 2020 |
| `src/quant/features/fundamentals.py` | margins, ROA/ROE, leverage/liquidity, accruals, growth, issuance | Announcement gate and plausible lag; no assumed date | Implemented and tested; restatement risk remains |
| `src/quant/features/options.py` | IV, IV rank/change/premium, 25-delta skew, term slope, relative spread, expirations | Backward as-of only; 21-day staleness; invalid IV rejected | Implemented and tested; limited history/coverage |

## Analyst-data conclusion

The local tables contain consensus snapshots, not analyst-level observations.
They have vintage date, relative forecast period, forecast period end,
consensus, range and contributor count. They do **not** contain analyst id,
recommendation revisions, target-price revisions, or exact intraday publication
time. Weekly consensus-revision features are PIT-usable; analyst stickiness,
revision breadth by individual analyst, and recommendation/target-price changes
are not computable from these files.

## Fundamental-data conclusion

Statement `date` is a fiscal period end. It is unsafe on its own. The existing
builder makes features no earlier than a matched earnings announcement, but
one row per period means a later restatement may overwrite the originally
reported value. Announcement-gating fixes timing, not restatement history.
These features cannot be certified as historical-as-reported without SEC
accession/vintage data.

## Earnings-data conclusion

Actual/estimate pairs become usable only after the matched announcement. BMO
is available that session; AMC and unknown `when` become available next
session. Twenty-five percent of calendar rows lack `when`, so the conservative
rule is material. No local guidance text/direction or reliable first-published
scheduled-date history exists.

## Options-data conclusion

The local aggregate supports IV level/rank/premium, coarse 25-delta skew, term
slope and chain spread. It cannot support put/call volume, open-interest change,
dealer gamma or exact surface reconstruction. Coverage starts in 2019, is
irregular early, and selects optionable/liquid firms. Given EXP-005's negative
incremental result and recent synchronization falsification evidence, options
are not a top-three acquisition priority.

## Safe normalized research schema

For event/low-frequency features, store `security_id`, `economic_date`,
`available_at`, `source`, `feature_name`, `value`, `unit`, `period`,
`revision_id`, `retrieved_at`, and `provenance_hash`. Contract-level options
should retain a separate quote schema keyed by quote time, contract id,
expiration, strike and put/call; forcing those rows into the scalar feature
schema would erase market microstructure.
