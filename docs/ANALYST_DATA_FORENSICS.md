# Analyst-estimate data forensics

Date: 2026-09-19. Aggregate output: `experiments/EXP-009-forensics/analyst.json`
(reproduce with `python -m scripts.quant.data_forensics analyst`). Rows dated
after the last training-side date (2025-05-09) were **not read**; the sealed
holdout is untouched. No vendor row is copied into the repository.

## 1. What the data is

Two local tables, `dolthub_earnings_eps_estimate` and `..._sales_estimate`, each
**7,060,412 rows** (6,051,912 read through 2025-05-09), 7,029 symbols, four
relative periods per (symbol, date) — *Current Quarter*, *Current Year*, *Next
Quarter*, *Next Year* — with `consensus`, `high`, `low`, `count`, `year_ago` (EPS
also `recent`, whose meaning is undocumented and which is not used). Vintage dates
run 2017-10-26 → 2026-08-23 (414 distinct dates read). The manifest classifies it
`point_in_time` and says `date` is the vintage. What supports that locally: the
schema has no forward-looking field, each (symbol, date, period) is unique, and an
earlier session verified AAPL's down-then-up revision sequence week by week. The
**vendor's own timestamp semantics cannot be verified locally** (a Dolt scrape of
an unnamed source, with no second vintage source to compare against); that is a
standing residual risk, not a resolved one.

## 2. Findings

| Check | Result | Consequence |
|---|---|---|
| Duplicate (symbol, date, period) rows | **0** | keys are unique |
| Vintage cadence | 89.9% of vintage dates are Sundays; **93.0%** of per-symbol gaps are exactly 7 days — but only **56% in 2017, 73% in 2018**, ≥ 95% from 2019; 2.6% of gaps are 1–6 days, 4.0% are > 7 | a fixed-row lookback (`shift(4)`) is not a 4-week lookback early in the sample or across gaps |
| Non-Sunday vintages | 10.1% of distinct vintage dates (5.2% of vintage rows), concentrated 2017-18 (Mon/Tue) | intraday capture time unknown; same-day use is unsafe |
| **Fiscal rollover** ("Current Year" changes period) | **31,708 events** (2.1% of consecutive pairs), 71% in Feb–Mar; median absolute relative change **19.6% at rollover vs 0.0% otherwise** (sales 8.9%) | a naive difference manufactures a revision on a predictable calendar — must be NULL |
| `period_end_date` moving backward | 49 events | vendor glitches; handled by the same-period rule |
| **Staleness** | 75.5% of consecutive vintages have an *identical* consensus (sales 71.8%); identical runs: median 2 weeks, p90 10, p99 17, **max 52**; 19,299 runs ≥ 13 weeks, **856 runs ≥ 26 weeks** | unchanged consensus is normal, so it is not by itself stale; runs of half a year or more are suspect and are measurable (`stale run length`) |
| Contributor count | median 3, p90 9; **20.1% of rows have `count = 1`**; 0.9% null (sales: 10.1% null) | a lone analyst has no dispersion; missing counts stay missing |
| `high ≥ consensus ≥ low` | holds on **100%** of rows where all three are present; 0 rows with `high < low` | internal consistency is good |
| `high − low` when `count = 1` | exactly **0 on 99.98%** of rows (sales 100%) | the old `est_eps_dispersion` scores a single analyst as "no disagreement" — semantically wrong |
| Null consensus | EPS 0.9% (sales 10.1%); null `year_ago` 4.2% (sales 12.7%) | missing must stay missing |
| Consensus exactly 0 / |consensus| < 0.05 | 1,777 rows / 1.85% (sales 51 / 0.003%) | percentage revisions on these are meaningless → NULL |
| **ID stability** | **308 symbols with a gap > 365 days** between vintages (318 events), max gap 2,371 days | ticker reuse / dropped-and-reinstated coverage: a revision across the gap compares different situations |
| Coverage of the traded universe | **98.1%** of in-universe rows since 2017-10-26 have a usable (non-null, ≤ 45-day-old) vintage; by year 94.1% (2017), 97.5%, 98.5%, 98.4%, 96.6%, 97.6%, 99.4%, 98.9%, 98.7% (2025); median vintage age 3 days, p95 5; 22 of 740 universe symbols never appear | coverage is good from 2019; 2017-18 thinner |
| Same-day vintage matches | 0.7% of panel rows | resolved by a strictly-earlier attach |

## 2b. Independent evidence that the vintages are real as-of snapshots (added before EXP-009C)

A vendor `date` column that *says* "vintage" proves nothing on its own. The strongest local test
ties it to a **second, independently sourced table**: the earnings calendar's announcement dates.
For 19,499 matched (symbol, quarter) events through 2025-04, the estimate table's "Current Quarter"
label should roll to the next period **just after** the company reports — if the snapshots were
backfilled from a later state, the roll would not line up with an announcement date recorded elsewhere.
(`experiments/EXP-009-forensics/analyst_timing.json`.)

| Test | Result |
|---|---|
| Last vintage still labelling the announced quarter as "Current Quarter", minus the announcement date | median **−3 days** (p25 −4, p75 −2, p95 −1); **99.3%** within +8 days |
| First vintage labelled with a *later* period, minus the announcement date | median **+4 days** (p25 +3, p75 +5, p95 +10) — the label rolls right after the report |
| Last pre-announcement consensus **equals the realised EPS** (±0.5¢) | **5.7%** (median absolute surprise $0.07) — consensus is not contaminated by the answer |
| Last pre-announcement consensus equals `eps_history.estimate` (±0.5¢) | 87.4% — the two tables describe the same pre-report consensus |
| 8% of events roll ≥ 30 days *before* the announcement | early or unusual quarter handling; these are exactly the cases a same-period rule already NULLs |

Real-data gates (`exp009c.pit_gates`, run before registration; 16 s): truncation invariance ✓,
rewriting every vintage after 2022-12-31 changes no earlier feature over 352,161 panel rows ✓, and none of
34,090 attached rows draws from a vintage dated on or after its own date ✓.

Coverage of the eight PIT features on in-universe rows (non-null share; `analyst_feature_coverage.json`):
`rev_4w` 76% (2018), 86-91% (2019-24); `rev_13w` 56-72% (lower in the first months of each year, when
fiscal rollover nulls a 13-week comparison — a *predictable calendar of missingness* the study must not
mistake for signal); dispersion and coverage 95-99%; acceleration 60-82%. Nothing before 2017-10.

## 3. What `estimates.py` (the earlier construction) got right and wrong

Right: revisions only where `period_end_date` is unchanged; NULL for near-zero
denominators; NULL for a vintage older than 45 days; backward as-of attach; the
alignment-by-label fix.

Not handled: (1) **row-shift lookbacks** — `shift(4)` / `shift(13)` count vintage
rows, not time; (2) **exact-match attach** — a vintage dated the same day as the
panel row is usable; (3) **dispersion at `count = 1`**; (4) **gaps and reuse** —
a revision across a >28-day hole or a 6-year hole is still computed if the
`period_end_date` happens to match. None of these is a look-ahead of *future*
information; (2) is the only one that could be, and only for the 0.7% of rows
that matched a same-day vintage of unknown intraday time.

## 4. The PIT-safe construction (`src/quant/features/analyst_pit.py`)

| Feature | Definition | Computational | Against the literature |
|---|---|---|---|
| `analyst_eps_rev_4w` | (c(t) − c(t−28d)) / \|c(t−28d)\|, prior vintage within ±3 days, same `period_end_date` | EXACT | APPROXIMATED (consensus revision; vendor unknown, FY1 only, weekly) |
| `analyst_eps_rev_13w` | same at 91 days, ±5 | EXACT | APPROXIMATED |
| `analyst_sales_rev_4w`, `_13w` | same on the sales table | EXACT | APPROXIMATED |
| `analyst_eps_dispersion` | (high − low)/\|consensus\|, NULL if `count < 2` | EXACT | APPROXIMATED (range, not std of individual forecasts) |
| `analyst_eps_coverage` | vendor `count` | EXACT | APPROXIMATED (definition undocumented) |
| `analyst_eps_coverage_chg_13w` | count(t) − count(t−91d) | EXACT | APPROXIMATED |
| `analyst_eps_rev_acceleration` | rev_4w(t) − rev_4w(t−28d), three consensus points, one period | EXACT | AUTHOR-DEFINED (no published counterpart) |
| `analyst_stickiness` | needs analyst identity | — | **NOT REPRODUCIBLE** (Cao, Tao, Wang & Yin, Review of Finance 2026) |
| recommendation change, target-price revision, analyst-level forecast error | no such data | — | **NOT REPRODUCIBLE** |

Attach rule: the latest vintage **strictly before** the panel date, NULL if
older than 45 days, aligned by index label, input never mutated. The features
are deliberately **not registered** in the global `REGISTRY` (registration would
change every default dataset build and the registry hash); the EXP-009C runner
attaches them explicitly.

## 5. Leakage tests (`tests/quant/test_analyst_pit.py`, 25 tests)

Truncating the vintage table at any date changes no feature of an earlier row;
perturbing every future vintage (to absurd values) changes no earlier panel
feature; a panel row never sees a same-day vintage but sees it the next day; a
stale vintage attaches NULL; alignment is by label (shuffled panels give identical
per-row values); inputs are not mutated; symbols never borrow from each other;
a rollover yields NULL then a true 0.0 once both ends share a period; a missing
week gives NULL rather than a stretched lag; extra daily vintages do not shorten
a 28-day lookback; ticker reuse across a long gap gives NULL; near-zero
consensus gives NULL; dispersion is NULL for one analyst; missing stays missing;
and a check on the **real** vintage table (150 symbols, cutoff 2022-12-31) proves
truncation invariance and strict attach on real data.

## 6. Go / no-go for EXP-009C

| Requirement | Evidence | Status |
|---|---|---|
| Usable vintage timestamp | `date` = vintage; unique keys; weekly Sunday cadence (93% exactly 7 days, ≥ 95% from 2019); consistent with an independent table (§2b). Intraday capture time unknown → strict-before attach | **PASS** (residual: vendor semantics inferred, not documented) |
| Correct historical ordering | 0 duplicate keys; per-symbol dates sorted; 49 backward `period_end_date` moves in 6M rows, handled by the same-period rule | **PASS** |
| No future-consensus leakage | consensus equals the realised EPS on only 5.7% of events; the period label rolls 3-4 days *after* announcements; real-data truncation, perturbation and strict-attach gates pass | **PASS** |
| Safe fiscal-period mapping | revisions only where `period_end_date` is unchanged; 31,708 rollover events NULLed; tested | **PASS** |
| Rollover protection | tested on a constructed rollover and measured on the real table (median jump 19.6% vs 0.0%) | **PASS** |
| Reasonable universe coverage | 98.1% of in-universe rows have a usable vintage; 94% in 2017, 97-99% later; **but** the tables start 2017-10-26, so folds 0-2 cannot learn from them | **PASS with a preregistered evaluable-fold rule** (folds 3-7) |
| Staleness detection | 75.5% of consecutive vintages unchanged (normal); runs ≥ 26 weeks measurable (856); 45-day age rule | **PASS** |
| Known missingness semantics | consensus null 0.9% (sales 10%); missing stays missing; `count = 1` → dispersion NULL; 13-week features null around fiscal rollover (calendar-dependent) | **PASS with a documented artifact risk** |
| Source / licence for internal research | manifest and catalogue: "Open data on DoltHub"; **redistribution terms of the upstream vendor unverified** — outputs committed here are aggregates only | **PASS for internal research; redistribution NOT cleared** |

**Verdict: GO, as a single, isolated, low-prior arm.** The data passes every required check; that is not a
finding that analyst revisions help. The literature does not transfer (IBES-like monthly data with analyst
identity; the one 2026 paper that adds value needs identity this data lacks), this repository's EXP-005
ablation was negative, coverage begins 2017-10 (five evaluable folds), and the missingness has a seasonal
pattern a tree could exploit. A null result is the expected outcome, and is recorded as such in the
preregistration.
