# Earnings calendar and history — data forensics

Date: 2026-09-19. Aggregates: `experiments/EXP-009-forensics/earnings.json`
(`python -m scripts.quant.data_forensics earnings`). Nothing after 2025-05-09
was read; the holdout is untouched.

## 1. What the data is

| Table | Rows | Keys / fields | Point-in-time status |
|---|---:|---|---|
| `earnings_calendar` | 117,601 (93,647 read) | `symbol`, `date`, `when` | `publication_lagged`, **a current snapshot** |
| `earnings_eps_history` | 168,473 | `symbol`, `period_end_date`, `reported`, `estimate` | `publication_lagged`; **no announcement date** |

* The calendar covers **2020-01-22 → 2026-10-01** only (7,359 symbols; 13.9k–20.3k
  rows a year). It was retrieved 2026-08-29 and **contains 263 rows dated after its own
  retrieval** — scheduled future events. A naive read leaks "this company is about
  to report"; every consumer must bound availability at the observation date.
* `earnings_eps_history` has the reported and the estimated EPS for a fiscal
  period but **not the day it became public**. The row for a quarter ending
  2026-06-30 is dated 2026-06-30 although the figure appeared 2026-07-30 — a
  30-day leak if used as dated (verified in an earlier session on AAPL, and the
  reason the table is only admitted through the calendar join).
* The history spans back further than the calendar: **52,161 history rows have a
  period end before 2019-12-01** and can never be matched to an announcement, so
  event features begin in 2020.

## 2. Timing field (`when`)

| Value | Share of calendar rows |
|---|---:|
| After market close | 42.2% |
| Before market open | 32.6% |
| **Missing** | **25.2%** (17.2% in 2020 → 30.2% in 2023, 31.4% in 2024) |

The missing share is large and **rising**. Among *matched events* through 2025-05-09,
18.1% have unknown timing. There is no way to recover the true timing locally.

**Rule (implemented in `src/quant/features/earnings.py::_availability_date` and kept
unchanged):** before-open → usable the same trading day; after-close → the next
trading day; **unknown → treated as after-close** (the conservative direction).
Consequence: **64.6% of matched events become available one or more days after the
announcement date.** An after-close result can never enter a same-close feature —
which also means a `Before market open` mislabelled as `After market close` merely
costs one day of information, whereas the reverse would be a leak. The cost of the
conservative rule is quantifiable (a one-session delay on the ~18% unknown), and it
is the right side to be wrong on.

## 3. Matching and coverage

* Calendar dates: no duplicates on (symbol, date); 0.04% fall on a weekend
  (data-entry noise); median 4 announcements per symbol-year (p10 = 1, i.e. partial
  years).
* **86,746 events matched** through 2025-05-09 (first announcement ≥ 5 and ≤ 150 days
  after the period end): 16,763 (2020) → 15,239 (2024) → 6,289 (to 2025-05). Report
  lag from the period end: median 37 days, p5 22, p95 127.8 — a realistic 10-Q/10-K
  pattern with a slow tail from late filers. **60,755** events carry a SUE
  (need ≥ 4 prior surprises); 16,708 are for traded-universe symbols.
* `reported` is null on 6.4% of history rows, `estimate` on 14.0%; 5 reported and
  9 estimate values exceed 1,000 in magnitude (split/currency glitches) — a filter
  belongs in any surprise construction.

## 4. Look-ahead risks and how each is closed

| Risk | Status |
|---|---|
| Fiscal-period-end used as availability | Closed: the history is only usable through the calendar join. |
| Future scheduled dates in the calendar | Closed: `available_from` must be ≤ the panel date; tested. |
| After-close result in a same-close feature | Closed by the timing rule above. |
| Unknown `when` | Closed conservatively (next day). Cost: ~18% of events one day later. |
| **Calendar is a snapshot and may hold the *original scheduled* date rather than the actual one** | **OPEN and unverifiable locally.** If a company reported later than scheduled, its recorded date could be *earlier* than reality — making the event available too early. 0.04% weekend dates are the only local hint of estimated (not actual) dates. Any PEAD result should be read with this caveat. |
| SUE denominator uses only *prior* surprises | Closed: `shift(1)` before the expanding window (already in the code, tested). |
| `estimate` in the history is the *final* pre-report consensus | Assumed, not verifiable: it is a vendor field with no vintage. |

## 5. PEAD / SUE reconstruction

Standardised unexpected earnings, **SUE = (reported − estimate) / std of that
firm's prior surprises**, is implemented exactly (`sue`) and is the analyst-based
variant. The time-series seasonal-random-walk variant of the classic PEAD
literature (Bernard & Thomas 1989; Livnat & Mendenhall 2006 compare both — cited
here from general knowledge, **not re-read in this pass**) needs several quarters
of *as-first-reported* EPS, which this table does not guarantee (no vintage).
Classification:

* Analyst-based SUE, surprise %, days-since-announcement: **computationally EXACT**;
  literature match **APPROXIMATED** (vendor consensus; announcement date and timing
  partly missing).
* Seasonal-random-walk SUE with as-first-reported EPS: **NOT REPRODUCIBLE** (no
  restatement vintage).
* Announcement-window abnormal return (CAR), earnings-call text, guidance:
  **NOT AVAILABLE**.

## 6. Verdict

The earnings-event features are admissible **from 2020**, with the conservative
timing rule, and only as a secondary candidate: the EXP-009 decision matrix ranks
them below turnover, ranking loss and the analyst arm, and their window (2020–2025,
~5 years, ~4 folds' worth) is short. They are **not** part of EXP-009C's arm; they are
a later isolated experiment, and the open calendar-snapshot risk is a precondition
to state next to any result.
