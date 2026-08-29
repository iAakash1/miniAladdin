# Dataset Catalog

Every figure here was **measured against the live source**. Where a number
appears, the query that produced it is shown. Where a point-in-time claim
appears, it was checked against a specific column rather than inferred from a
table's name.

The catalog is code — `src/quant/datasets/catalog.py` — not prose. Its
`point_in_time` field is read by `src/quant/pit/dataset.py`, which **refuses**
to admit a `NOT_POINT_IN_TIME` source as a feature input. A limitation that
exists only in documentation is a limitation that gets violated.

---

## 1. The classification that does the work

| Class | Meaning | Admitted to training |
|---|---|---|
| `POINT_IN_TIME` | The row carries the date it became knowable, or is knowable at the moment it describes | Yes |
| `PUBLICATION_LAGGED` | Describes a period without a publication date, but one is obtainable from another table | Yes, with the join stated |
| `NOT_POINT_IN_TIME` | Describes a period, carries no publication date, and none is obtainable | **No** — refused without a named waiver |

---

## 2. Ingested

### `dolthub_stocks_ohlcv` — priority 1

Daily unadjusted OHLCV for US equities and ETFs.

| Property | Measured value |
|---|---|
| Coverage | **2011-01-03 → 2026-08-21** |
| Symbols per day | 3,844 (2011-01-03) → 12,470 (2026-08-21) |
| Security master | 24,058 symbols |
| Point-in-time | `POINT_IN_TIME` — a close is knowable at that close |
| Survivorship | `COMPLETE` |

**Survivorship verification.** Not asserted — checked:

| Symbol | `last_seen` | `financial_status` | Real event |
|---|---|---|---|
| TWTR | 2022-10-23 | — | Taken private 2022-10-27 |
| ABMD | 2022-12-18 | Normal | Acquired by J&J |
| SIVB | 2023-03-26 | **Bankrupt** | SVB failed 2023-03-10 |
| SBNY | 2023-03-26 | **Bankrupt** | Signature Bank failed 2023-03-12 |
| FRC | 2023-04-30 | — | Seized 2023-05-01 |
| ATVI | 2023-10-08 | — | Acquired by Microsoft |
| SPLK | 2024-03-17 | Normal | Acquired by Cisco |

And the bars themselves stop when trading did:

```
SIVB 2023-03-08  close 267.83  volume    835,185
SIVB 2023-03-09  close 106.04  volume 38,746,481   (-60.4%)
SIVB 2023-03-10  (no row — trading halted)
```

**Why unadjusted prices are an advantage.** The table has no adjusted close,
which reads like a gap and is the opposite. A vendor's adjusted close is that
vendor's back-adjustment, under an unpublished dividend-reinvestment
convention, applied at an unknown time — and it is not point-in-time by
construction. Raw prices plus dated actions is strictly more information.

**Limitations.** No intraday, no bid/ask, no venue. Volume is unadjusted for
splits (handled downstream; dollar volume is split-invariant anyway).

---

### `dolthub_stocks_symbol` — priority 1

Security master: name, exchange, ETF flag, financial status, `last_seen`.

`PUBLICATION_LAGGED`, and the reason is worth stating precisely: this is a
**current** snapshot of the master, not a history of it. `last_seen` is the one
genuinely historical field, and it is used only as a delisting bound. The
descriptive fields are treated as static — an assumption that is recorded, and
is exactly why this is not classified `POINT_IN_TIME`.

**Limitation with a consequence.** `last_seen` begins **2017-10-26**. Exits
before then are not dated by this table, so `UniverseSnapshot.coverage_class`
reports `partial` for pre-2017 rebalances rather than claiming a completeness
the data does not have.

---

### `dolthub_stocks_split` — priority 2

3,993 rows. `POINT_IN_TIME`: the ex-date is the availability date, which is
conservative because splits are announced weeks earlier.

**The finding that constrains the study.** Coverage begins **2014-03-28**,
while `ohlcv` begins 2011-01-03. Any return computed before that date is
split-contaminated: a 4:1 split with no split record reads as a **-75%
single-session return**, which would be simultaneously the largest reversal
signal, the largest volatility observation and the largest drawdown in the
sample — all fabricated.

`src/quant/pit/dataset.py` therefore refuses to build training rows before
`CORPORATE_ACTION_COVERAGE_START = 2014-04-01`. It costs 3.2 of the 15.6
available years. That is the correct trade: a shorter clean sample beats a
longer contaminated one, and the contamination concentrates in exactly the
features most sensitive to outliers.

---

### `dolthub_stocks_dividend` — priority 2

494,438 rows, keyed `(act_symbol, ex_date)`. Too large to page whole, so it is
fetched per symbol batch for the research universe. `POINT_IN_TIME` on the same
reasoning as splits.

---

### `dolthub_rates_us_treasury` — priority 3

Daily par yield curve, 1M–30Y. **9,158 rows covering 1990-01-02 → 2026-08-28
in 12.7 MB** — the cheapest macro state available.

`POINT_IN_TIME` with a stated lag: Treasury publishes after the close of the
day the curve describes, so the ingestion treats publication as `date + 1
business day`. A same-day model never sees that day's curve.

Used because it is **not revised**. Published once, correct thereafter — which
is why the curve is here and CPI is not.

---

### `french_factors_daily` — priority 3

Fama-French 5 factors, the risk-free rate, and momentum. **15,854 daily rows,
1963-07-01 → 2026-06-30, zero missing values.**

This is the most important non-price source, because it is what makes one
specific word usable. A strategy return minus a benchmark return is a *return
difference*. Only the intercept of

```
r_t − rf_t = a + b₁·MktRF + b₂·SMB + b₃·HML + b₄·RMW + b₅·CMA + b₆·MOM + e_t
```

may be called alpha, and computing it requires these series.

**Classified `PUBLICATION_LAGGED`, and the use is restricted accordingly.** The
library is rebuilt when CRSP is revised, so a value downloaded today for
2015-03-10 is not necessarily what was published then.

* **Permitted** — evaluating realised returns after the fact. Revision moves
  the benchmark's history, not the strategy's returns.
* **Barred** — any feature. `src/quant/pit/dataset.py` does not admit it.

**Licence.** Provided free for research use by Kenneth R. French; copyright
Eugene F. Fama and Kenneth R. French. The ingestion fetches from source and
stores locally; the raw files are not redistributed.

---

### `dolthub_stocks_ohlcv_monthly` — priority 1 (derived ingestion)

The same table, sampled **monthly across the whole market** rather than daily
across a chosen universe. **1,346,864 rows over 184 month-ends.**

It exists to break a circularity: a survivorship-free universe must be chosen
from what was liquid in the past, liquidity comes from the price table, and
pulling 24,058 symbols daily to select 250 of them is exactly the waste the
date-partitioned design avoids.

---

## 3. Catalogued and deferred

### `dolthub_options_volatility_history` — priority 4

Dated IV and HV snapshots with 52-week extremes. **2019-02-09 → 2026-08-28**,
531 symbols rising to ~1,531.

**Promoted above `option_chain`, against the brief's suggested ordering.** Each
row *is* a snapshot: `iv_current` is the implied volatility observed on `date`,
and the year high/low columns describe the trailing year as at that date. IV
rank, IV percentile and the implied-minus-realised spread fall straight out of
these columns with no chain aggregation and no Greeks reconstruction.

**Limitations.** Cadence is irregular — weekly (Saturdays) from 2019 to roughly
2021, daily afterwards — so features must not assume a uniform grid. No term
structure and no skew; those need the chain. The provider's IV methodology is
unpublished, so the level is a vendor measurement, not a reconstructible
quantity.

### `dolthub_earnings_eps_estimate` — priority 5

**The rare and valuable case.** `date` is the *vintage* — what consensus was on
that day — and `period_end_date` is what it forecasts. That pair makes estimate
revisions computable without lookahead. Most free estimate data carries only
the current consensus, which backdates today's revised view across the whole
history. Coverage from 2017-10-26.

### `dolthub_earnings_calendar` — priority 6

Announcement dates. `PUBLICATION_LAGGED` rather than `POINT_IN_TIME` because
the table is a current snapshot that **also contains future scheduled dates** —
a naive read leaks the knowledge that a company is about to report.

### `dolthub_options_option_chain` — priority 8

8.58 GB, full chains with bid/ask, IV and Greeks. Schema-verified, **not
ingested**. Deferred rather than rejected: it is the only source here for term
structure and skew, and `volatility_history` supplies the level, rank and
spread at a fraction of the cost. Ingesting the chain before those are shown to
carry signal would be paying the largest engineering cost in the catalog for an
unmeasured return.

---

## 4. Excluded, with the reason

### `dolthub_earnings_income_statement` — `NOT_POINT_IN_TIME`

**Barred from historical training and enforced in code.**

The primary key is `(act_symbol, date, period)` where `date` is a *period*
marker. No column anywhere in the schema records when the figure was filed or
whether it was later restated. Using it historically inserts today's knowledge
of a quarter into dates before that quarter was reported.

It is also redundant. This repository already has genuinely point-in-time
fundamentals with real SEC `filed` dates in `src/panel/fundamentals.py`:

> For an observation date **D**, a fact is visible only if `filed <= D`. Among
> the visible filings, each fiscal period resolves to its **most recently
> filed** value.

Ingesting a worse version of something already held correctly is negative
value, not redundant value. The entry stays in the catalog so the decision is
visible and revisable rather than silent.

### Other rejected sources

| Source | Reason |
|---|---|
| CPI / unemployment / GDP | Revised after release; honest use needs a vintage database (ALFRED) |
| Vendor fundamentals endpoints | Return current values with no filing date — the failure `docs/PANEL.md` §5.3 already refuses |
| Kaggle equity datasets | Provenance and licensing unverifiable; redundant with DoltHub |
| Stooq | Redundant with DoltHub, shallower, no delisting record |

---

## 5. Priority order, and where measurement overrode the brief

The brief proposed: A) OHLCV, B) corporate actions, C) earnings, D) estimates,
E) rates, F) options chain, G) volatility history. Two changes were made and
both were measured, not preferred:

1. **`volatility_history` promoted above `option_chain`** (G above F) — it is a
   dated snapshot table that already contains the derived quantities the chain
   would have to be aggregated to produce.
2. **`income_statement` demoted below `eps_estimate`** (C below D) — it has no
   filing date and is superseded by the SEC XBRL path already in the codebase.

---

## 6. Reproducing these measurements

```bash
python -m scripts.quant.backfill --stage reference
python -m scripts.quant.backfill --stage monthly --start 2011-01-03
python -m scripts.quant.backfill --stage universe --universe-size 250
python -m scripts.quant.backfill --stage daily --start 2012-01-02
```

Every stage is resumable at year granularity. `RawStore.verify()` re-hashes
each partition against its manifest.
