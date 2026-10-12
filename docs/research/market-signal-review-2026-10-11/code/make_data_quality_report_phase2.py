#!/usr/bin/env python3
"""Write data_quality_report_phase2.md from the Phase II manifests: coverage, missingness, identity, clock audit, known gaps. Nothing here reads a return or relates a variable to a label.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_data_quality_report_phase2.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASE = REPO / "docs/research/market-signal-review-2026-10-11"


def load(path: str) -> dict:
    return json.loads((REPO / path).read_text())


def main() -> None:
    uni, ing, base = load("data/manifests/mid_sample_universe.json"), load("data/manifests/mid_sample_ingest.json"), load("data/manifests/mid_sample_baseline.json")
    master, panel, edgar = load("data/manifests/mid_security_master_coverage.json"), load("data/manifests/rich_pit_panel_mid_manifest.json"), load("data/manifests/edgar_filings_v1.json")
    checks = load("docs/research/market-signal-review-2026-10-11/validation/exp014_pre_registration_checks.json")
    v = edgar["validation"]
    audit = v["clock_audit"]
    years = "\n".join(f"| {y} | {r['rows']:,} | {r['symbols']:,} | {r['identity_trusted'] * 100:.1f}% | {r['identity_contradicted'] * 100:.2f}% | {(r['sic_of_identified'] or 0) * 100:.1f}% | {(r['shares_of_identified'] or 0) * 100:.1f}% |"
                      for y, r in panel["coverage_by_year"].items())
    fc = sorted(((r["coverage"], k) for k, r in panel["feature_coverage"].items()))
    low = ", ".join(f"`{k}` {c * 100:.0f}%" for c, k in fc[:6])
    high = sum(1 for c, _ in fc if c >= 0.8)
    grades = panel["identity"]["grades"]
    exit_ = panel["missingness_vs_exit"]
    conf = checks["label_free_counts"]["confirmatory"]
    doc = f"""# Data quality report, Phase II (independent firm sample and EDGAR registry)

Generated from the manifests under `data/manifests/` and `phase2_data_manifest.json`. Nothing here depends on a return, a rank label or any relation between a variable and a label. Hashes of every dataset are in
`phase2_data_manifest.json`; this page states what was checked and what was found.

## 1. Universe and prices

| Check | Result |
|---|---|
| Construction | liquidity ranks 251 to 1,000 by 3-month median dollar volume, non-ETF, non-test issue, close >= 5, read from each month's whole-market cross-section (delisted names present in the months they were liquid) |
| Size-250 rebuild against the frozen universe file | equal on {uni['snapshots_checked_against_frozen_size_250']} of {uni['snapshots']} snapshots (mismatches: {uni['mismatches']}) |
| Snapshots, members | {uni['snapshots']} monthly snapshots {uni['start']}..{uni['end']}; {uni['unique_members']:,} unique members; {uni['members_per_snapshot']['median']} per snapshot |
| Members that were ever in the frozen universe (other months) | {uni['overlap_with_frozen_universe_ever']:,}; dropped from the confirmatory sample by company |
| Price rows, partitions | {ing['verification']['dolthub_stocks_ohlcv']['partitions']} yearly partitions, checksums verified, nothing dated at or after the holdout start (2025-08-26); capped 2025-06-30 |
| Listing-snapshot table | **not copied**: its `date` column runs to 2026-08-22, inside the sealed window |
| Baseline frame | {base['rows']:,} rows, {base['symbols']:,} symbols, {base['dates']} decision dates {base['date_min']}..{base['date_max']}, {base['in_universe_rows']:,} in universe; every grid date is a market session; names per date: minimum 637, 5th percentile 735, median 749 |
| Label coverage in universe | `fwd_rank_21` 99.8%, `fwd_ret_21` 99.8%, `fwd_ret_5` 99.95%: the missing 0.2% are names with no price 21 sessions ahead (delistings and halts) |
| Baseline feature coverage in universe | minimum 96.8%, median 99.2% |
| Optional datasets (earnings, options) | absent from this store; the builder reports "absent, not zeroed"; none of the 26 baseline features uses them |

## 2. Identity (security master for the sample)

{master['symbols']:,} symbols resolved: {', '.join(f'{k} {n:,}' for k, n in master['resolution_grades'].items())}; {master['trusted_securities']:,} trusted securities; {master['exit_events']} exit events; {master['shares_vintages']:,} share-count vintages.

| Year | Rows | Symbols | Trusted identity | Contradicted | SIC of identified | Shares of identified |
|---|---|---|---|---|---|---|
{years}

Row grades in the panel: {', '.join(f'{k} {n:,}' for k, n in grades.items())}. **The repository's identity gate fails** (it demands 95% trusted in every year and fold; the sample reaches about 80-82%): small and delisted
names are harder to tie to a company, and 10.9% of rows belong to securities for which no 10-K or 10-Q was found (for example foreign filers or trusts; the grade D rows were not examined one by one). The size and industry-relative controls are therefore withheld (as in the frozen panel). Only trusted rows enter the
confirmatory sample, which selects on identity. Rows leaving the sample within 30 days have a lower trusted share ({exit_['share_identity_trusted_if_exiting_soon'] * 100:.1f}% against {exit_['share_identity_trusted_otherwise'] * 100:.1f}%)
and a lower share of present fundamentals ({exit_['share_present_if_exiting_soon'] * 100:.1f}% against {exit_['share_present_otherwise'] * 100:.1f}%): missingness is slightly informative about a coming exit.

## 3. Panel

{panel['rows']:,} rows, {panel['securities']:,} securities, {panel['symbols']:,} symbols, {panel['dates']} dates; 76 features (26 baseline, 50 SEC characteristics), feature hash equal to the frozen rich panel's. Lowest feature coverage: {low}. {high} of the 50 new features are present in at least 80% of rows.

## 4. EDGAR registry

| Check | Result |
|---|---|
| Companies, filings kept | {v['companies']:,}; {v['rows']:,} (periodic reports, amendments, 8-Ks, late-filing notices, deregistrations; accepted 2009-01-01..2025-06-30) |
| Page chains | {v['chain']['chains_with_all_pages_read']:,} of {v['chain']['companies']:,} complete; {v['chain']['companies_with_history_before_2011']:,} reach back before 2011 |
| Duplicates | {v['duplicate_accessions_across_companies']} accession numbers appear under more than one company (co-registrants); keyed by company and accession |
| Dates | filing date minus acceptance date is 0 to 4 days for {v['filing_date_minus_acceptance_date_days']['share_within_0_to_4_days'] * 100:.2f}% of filings; {audit['backdated_filings']['count']} filings are back-dated by more than a day (largest {-audit['backdated_filings']['min_gap_days']} days) |
| Acceptance-clock audit | on {audit['matched_filings']:,} matched filings only {audit['shares']['utc_correct (+4/+5 h)'] * 100:.1f}% of registry stamps are correct UTC; {audit['shares']['double_converted (+8/+10 h)'] * 100:.1f}% are 8-10 hours ahead; {audit['shares']['clock_unconverted (0 h)'] * 100:.1f}% are New York time labelled UTC (`validation/edgar_acceptance_clock_audit.md`) |
| Amendments | {v['amendments']['registry_periodic_amendments']:,} periodic-report amendments, of which {v['amendments']['in_fsds']:,} are in the Financial Statement Data Sets; {v['amendments']['not_in_fsds']:,} are not (Part III, exhibits) |
| Item 4.02 8-Ks, late notices | {v['item_4_02_8k']['filings']} filings by {v['item_4_02_8k']['companies']} companies; {v['late_notices']['NT 10-K']} NT 10-K, {v['late_notices']['NT 10-Q']} NT 10-Q |
| Nature of the download | current-state registry retrieved 2026-10-12, not a historical snapshot; acceptance times of accepted filings do not change, but withdrawn filings, if any, would be absent |

## 5. Confirmatory sample (label-free)

{conf['rows']:,} labelled rows, {conf['firms']:,} firms, {conf['dates']} dates. Rows without any original periodic report on the date: {conf['rows_without_history']:,}. Treated rows and companies (trailing 730 days):
{'; '.join(f"{k} {t['rows']:,} / {t['firms']}" for k, t in conf['treatments'].items())}.

## 6. Known gaps (not fabricated, not filled)

* No historical snapshot of provider data exists for the live scorer; the archive library records only from the day capture starts.
* Delisting returns are not modelled; names with no price 21 sessions ahead lose their label (0.2% of rows).
* Amendment content is known for 55% of amendments (a previous version with comparable facts is needed); the rest enter as their own category.
* Prices are unadjusted for dividends and the split table starts 2014-03-28; the panel therefore starts in April 2014.
* The price source's licence has not been reviewed.
"""
    out = BASE / "data_quality_report_phase2.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(doc):,} characters)")


if __name__ == "__main__":
    main()
