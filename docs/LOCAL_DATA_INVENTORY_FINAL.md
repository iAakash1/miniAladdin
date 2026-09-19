# Local data inventory (final)

Generated 2026-09-19T18:45:07+00:00 by `python -m scripts.quant.data_inventory` from measured file metadata.
Machine-readable: `data/manifests/data_inventory.json`. Row counts, sizes, columns and hashes are measured; the
PIT, licence and usability columns are explicit judgements (`UNASSESSED` if none was recorded). Nothing listed
as `NOT_COMMITTED` is in git.

## Normalised research partitions (`data/research/raw/*`)

| Dataset | Provider | Rows | Symbols | Dates | Size | PIT status | Research use | Caveats |
|---|---|---:|---:|---|---:|---|---|---|
| `dolthub_earnings_balance_sheet_assets` | DoltHub post-no-preference/earnings | 284,371 | 9998 | 2012-10-31 → 2026-07-31 | 4.2 MiB | NOT point-in-time | EXCLUDED_FROM_HISTORICAL_MODELS | as income statement |
| `dolthub_earnings_balance_sheet_equity` | DoltHub post-no-preference/earnings | 284,716 | 9998 | 2012-10-31 → 2026-07-31 | 3.3 MiB | NOT point-in-time | EXCLUDED_FROM_HISTORICAL_MODELS | as income statement |
| `dolthub_earnings_balance_sheet_liabilities` | DoltHub post-no-preference/earnings | 284,714 | 9998 | 2012-10-31 → 2026-07-31 | 2.8 MiB | NOT point-in-time | EXCLUDED_FROM_HISTORICAL_MODELS | as income statement |
| `dolthub_earnings_calendar` | DoltHub post-no-preference/earnings | 117,601 | 7360 | 2020-01-22 → 2026-10-01 | 0.2 MiB | partial (event date; 2020-01-22 onward) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | cannot time pre-2020 announcements |
| `dolthub_earnings_cash_flow_statement` | DoltHub post-no-preference/earnings | 176,631 | 9513 | 2012-10-31 → 2026-07-31 | 3.2 MiB | NOT point-in-time | EXCLUDED_FROM_HISTORICAL_MODELS | as income statement |
| `dolthub_earnings_eps_estimate` | DoltHub post-no-preference/earnings | 7,060,412 | 7029 | 2017-10-26 → 2026-08-23 | 35.0 MiB | point_in_time (weekly consensus vintage) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | consensus snapshots, no analyst id; 2017-10-26 onward |
| `dolthub_earnings_eps_history` | DoltHub post-no-preference/earnings | 168,473 | 7029 | None → None | 0.5 MiB | NOT point-in-time (period-dated, no announcement) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | usable only behind the earnings calendar gate |
| `dolthub_earnings_income_statement` | DoltHub post-no-preference/earnings | 270,925 | 9292 | 2012-10-31 → 2026-07-31 | 5.9 MiB | NOT point-in-time (as-of-today values, period end only) | EXCLUDED_FROM_HISTORICAL_MODELS | restatements overwritten; superseded by the SEC as-reported store |
| `dolthub_earnings_sales_estimate` | DoltHub post-no-preference/earnings | 7,060,412 | 7029 | 2017-10-26 → 2026-08-23 | 34.8 MiB | point_in_time (weekly consensus vintage) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | as EPS estimates |
| `dolthub_options_chain_daily` | DoltHub post-no-preference/options (aggregated locally) | 1,918,396 | 2317 | 2019-02-09 → 2026-08-28 | 45.0 MiB | point_in_time (snapshot-dated) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | 2019 onward; irregular cadence |
| `dolthub_options_volatility_history` | DoltHub post-no-preference/options | 691,007 | 745 | 2019-05-10 → 2026-08-28 | 8.0 MiB | point_in_time (snapshot-dated) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | 2019-05-10 onward; partial universe |
| `dolthub_rates_us_treasury` | DoltHub post-no-preference/rates | 9,158 | - | 1990-01-02 → 2026-08-28 | 0.2 MiB | point_in_time for the daily curve (one-session lag in model) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | not an ALFRED vintage series |
| `dolthub_stocks_dividend` | DoltHub post-no-preference/stocks | 494,438 | 10570 | 1970-01-19 → 2026-08-21 | 1.7 MiB | point_in_time (ex-date) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED |  |
| `dolthub_stocks_ohlcv` | DoltHub post-no-preference/stocks | 2,910,092 | 998 | 2012-01-03 → 2026-08-28 | 45.8 MiB | point_in_time (unadjusted close-date bars) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | no adjusted close; delisting bars partial before 2017-10-26; symbol is not a stable identity |
| `dolthub_stocks_ohlcv_monthly` | DoltHub post-no-preference/stocks | 1,346,864 | 20923 | 2011-01-31 → 2026-07-31 | 24.8 MiB | derived aggregate | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | monthly aggregate; not used by the frozen dataset |
| `dolthub_stocks_split` | DoltHub post-no-preference/stocks | 3,993 | 2625 | 2014-03-28 → 2026-08-21 | 0.0 MiB | point_in_time (ex-date) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | pre-2014 adjustments need caution |
| `dolthub_stocks_symbol` | DoltHub post-no-preference/stocks | 24,058 | 24058 | 2017-10-26 → 2026-08-22 | 0.5 MiB | NOT point-in-time (current snapshot) | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | descriptive fields are today's; last_seen is only a delisting bound |
| `french_factors_daily` | Kenneth R. French Data Library | 15,854 | - | 1963-07-01 → 2026-06-30 | 0.2 MiB | evaluation series (published with lag) | RESEARCH_ONLY | attribution only, never a feature |

## Other stores

| Path | Provider / source | Files | Rows | Size | PIT status | Licence / redistribution | Use | Git | Caveats |
|---|---|---:|---:|---:|---|---|---|---|---|
| `data/raw/sec` | SEC Financial Statement Data Sets | 58 | - | 4.90 GiB | as-reported (vintage-preserving source) | US government public data; SEC fair-access (<=10 requests/s, declared User-Agent); redistribution PERMITTED_BUT_NOT_COMMITTED_FOR_SIZE | RESEARCH_ONLY_PRODUCT_AFTER_ATTRIBUTION_REVIEW | not tracked | 58 quarterly ZIPs 2011Q1-2025Q2; no official checksums exist, hashes are self-recorded |
| `data/raw/security_master` | SEC company_tickers_exchange.json (current snapshot) | 1 | - | 0.5 MiB | NOT point-in-time (current only) | US government public data; redistribution PERMITTED_BUT_NOT_COMMITTED | RESEARCH_ONLY | not tracked | must never be back-dated |
| `data/curated/sec` | derived from SEC FSDS (this project) | 58 | 4,737,309 | 36.9 MiB | as-reported vintages | derived from public data; redistribution NOT_COMMITTED | RESEARCH_ONLY_UNTIL_REBUILT_V3 | not tracked | v2 store has known defects (see docs/SEC_TAG_MAP_AUDIT.md) |
| `data/curated/security_master` | derived (this project) | 5 | 113,446 | 1.3 MiB | PARTIAL (current-snapshot identity) | derived; redistribution NOT_COMMITTED | RESEARCH_ONLY | not tracked | historical intervals incomplete |
| `data/research/universe` | derived from the stocks OHLCV (this project) | 1 | - | 0.7 MiB | point_in_time by construction (trailing windows) | derived; redistribution NOT_COMMITTED | RESEARCH_ONLY | not tracked | top-250 liquid non-ETF; partial delisting inference before 2017-10-26 |
| `data/research/derived` | derived caches (this project) | 7 | 5,434,560 | 226.0 MiB | derived | derived; redistribution NOT_COMMITTED | RESEARCH_ONLY | not tracked | frozen frame/panels plus EXP-010B daily panel |
| `artifacts` | this project (EXP-006 model + runtime snapshot) | 7 | 100,496 | 1.3 MiB | derived | n/a; redistribution SMALL_ARTIFACTS_TRACKED_AS_REPO_DECIDES | PRODUCT_RUNTIME_ONLY_NOT_PROMOTED | tracked | EXP-006 model is EXPERIMENTAL, not promoted |
| `experiments` | this project (immutable experiment records) | 112 | 8,763,801 | 66.4 MiB | derived | n/a; redistribution AGGREGATES_TRACKED_PREDICTIONS_IGNORED | RESEARCH_RECORD | tracked | predictions/checkpoints are git-ignored |
| `research_vault` | generated research reports | 40 | - | 0.0 MiB | n/a | n/a; redistribution IGNORED_EXCEPT_EXAMPLE | PRODUCT_OUTPUT | tracked | runtime output |
| `research_papers` | third-party published PDFs | 19 | - | 15.0 MiB | n/a | copyrighted; redistribution MUST_NOT_BE_COMMITTED | LOCAL_READING_ONLY | not tracked | gitignored |
| `datasets` | DoltHub clones (stocks/options/earnings/rates) | 428 | - | 14.07 GiB | raw clones | open data on DoltHub; terms not reviewed; redistribution NOT_COMMITTED | RESEARCH_ONLY_UNTIL_LICENCE_REVIEWED | not tracked | source of the normalised Parquet under data/research/raw |

## Reading this table

* `usable_for_product` is true only where a licence review and attribution are complete; nothing here is currently product-cleared beyond the SEC public data.
* Dolt-sourced datasets carry an "open data on DoltHub" note, not a licence: redistribution is **not assumed**, and none is committed.
* `data/curated/sec` is the v2 store with the defects recorded in `docs/SEC_TAG_MAP_AUDIT.md`; it is superseded by the v3 rebuild.
* Every symbol-keyed dataset is keyed by ticker, which is not a stable identity (`docs/PIT_SECURITY_MASTER_PLAN.md`).
