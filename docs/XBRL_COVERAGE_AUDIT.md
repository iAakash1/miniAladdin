# XBRL coverage audit

Run against live payloads for AAPL, MSFT, NVDA and WMT — the last chosen for
its January fiscal year-end, to check that fiscal-year handling is not tuned
to a September/June calendar. 207 facts in total.

**The headline: these are individually filed facts, and they do not
reconcile into a statement.** Everything below supports that, and the product
has been changed to say so rather than to imply otherwise.

## 1–2. Concept presence

| concept | AAPL | MSFT | NVDA | WMT |
|---|---|---|---|---|
| Cash & equivalents | 6 | 6 | 6 | 6 |
| Dividends paid | 1 | 6 | — | 6 |
| Long-term debt | 6 | 6 | 6 | 6 |
| Net income | 6 | 6 | 6 | 6 |
| R&D expense | 6 | 6 | 6 | — |
| **Revenue** | **1** | **1** | 6 | 6 |
| Share repurchases | 6 | 6 | 6 | 6 |
| Shareholders’ equity | 6 | 6 | 6 | 6 |
| Total assets | 6 | 6 | 6 | 6 |
| Total liabilities | 6 | 6 | 6 | — |

NVDA returns no Dividends paid. NVIDIA does pay one, so that is a tagging gap
and must never render as zero. WMT returns no R&D and no Total liabilities.

## 3. Fiscal periods

Six consecutive years per concept where coverage exists. Fiscal years differ
by company exactly as expected — AAPL 2020-2025, MSFT/NVDA/WMT 2021-2026 —
because their fiscal calendars end in September, June, January and January.

The exceptions are the orphans: **AAPL Revenue exists only for FY2018, MSFT
Revenue only for FY2010, AAPL Dividends paid only for FY2017.** A single fact
sixteen years old sitting where nine other concepts have six recent years.

## 4–6. Forms, units, observations

* Forms: `10-K` only — 207 of 207. **There is no quarterly data at all.**
* Units: `USD` only. No unit reconciliation is required or possible.
* A fact carries exactly: `fiscal_year`, `value`, `unit`, `form`, `filed`.

## 7–8. Duplicates and conflicts

**None.** At most one fact per concept per fiscal year, across all four
securities. The duplicate-fact selection hazard does not exist in this
payload — there is nothing to select between, so selection is deterministic
by construction rather than by rule.

## 9–10. Latest observation and filing date

Every fact carries its own `filed` date, and it is a filing date, not a
retrieval date. The interface renders it as "Filed".

## 11. Period type — not supplied

There is **no** `period_start`, `period_end`, `period_type` or
`fiscal_quarter` on a fact. Period type can only be inferred from the form:
a 10-K covers a fiscal year, so every fact here is annual. That inference is
sound and is labelled as coming from the form rather than reported.

Since no 10-Q facts exist, there is no annual/quarterly ambiguity to resolve.

## 12. Cross-security comparability — **no, and this is the important part**

Two independent checks say these facts cannot be combined.

**The balance sheet does not balance.** `Assets = Liabilities + Equity` is an
identity; it holds exactly in any filed balance sheet or the filing would not
have been accepted. Computed from these facts:

| | Assets − (Liabilities + Equity) | as % of assets |
|---|---|---|
| NVDA FY2026 | 57,226,000,000 | **51.3%** |
| NVDA FY2025 | 16,366,000,000 | 24.9% |
| MSFT FY2026 | 75,002,000,000 | 12.1% |
| MSFT FY2025 | 62,254,000,000 | 12.2% |
| AAPL FY2023 | −14,667,000,000 | 4.2% |
| AAPL FY2024 | −944,000,000 | 0.3% |

A 51% gap is not rounding. It means the three concepts for one labelled
fiscal year are **not drawn from one reconciled context** — different periods,
different XBRL contexts, or a concept mapped to a tag that does not mean what
its label says. Any one of those makes cross-concept arithmetic invalid.

**Revenue and Net income do not share a year for AAPL or MSFT**, so even the
most basic derived figure — a net margin — cannot be computed for them from
this source.

## What follows from this

**Do not derive anything from these facts.** No margins, no free cash flow,
no growth rates, no ratios. The brief asked for derived metrics with declared
formulas; the honest answer is that the inputs are not mutually consistent, so
the formula is not the problem — the reconciliation is. A derived figure built
on facts that fail an accounting identity is a wrong number with a citation.

**Do not present them as financial statements.** They are individual filed
observations. The interface calls the panel "Filed financials", states that
nothing is aligned or carried forward, and now runs the balance identity in
front of the reader and reports when it fails.

**Do keep showing them.** Each fact is a real observation with a real source,
form, year and filing date. Withholding them because they do not reconcile
would be its own kind of dishonesty — the reader can use a filed net income
figure perfectly well as long as nothing pretends it is part of a statement.

## Reproducing this

The audit is arithmetic on `/api/research/{ticker}` → `filings.xbrl`. The two
checks worth re-running after any provider change are the concept-count
asymmetry and the balance identity; both are self-contained and need no
external reference data.
