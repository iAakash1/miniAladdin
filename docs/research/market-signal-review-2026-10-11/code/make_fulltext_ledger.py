#!/usr/bin/env python3
"""Phase II: the full-text reading ledger and the closest-work novelty matrix, written from one table so that every claim has a read level next to it.

Read levels, strongest first:
    FULLTEXT_PARTIAL  the open-access PDF was downloaded, text-extracted and read in the pages named in `pages`; the rest was searched, not read
    ABSTRACT          the abstract was read from the publisher's or an index's metadata (Crossref, OpenAlex, arXiv)
    METADATA          title, authors, venue and year verified; no abstract available
    TITLE_ONLY        title and authors only (full text and abstract not reachable)

Identifiers were checked on 2026-10-12 with Crossref (DOI records) and the arXiv API (`validation/fulltext_papers_verification.json`). No venue quartile or ranking is stated anywhere: SCImago returned 403,
JCR is paywalled, and nothing else was checked.

    python3 docs/research/market-signal-review-2026-10-11/code/make_fulltext_ledger.py
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]

# id, short, authors, title, version_chain, venue_verified, read_level, pages, finding_read, relevance, decision_impact
FULLTEXT = [
    ("F01", "Chan et al. 2001/2006", "Konan Chan, Louis K. C. Chan, Narasimhan Jegadeesh, Josef Lakonishok", "Earnings Quality and Stock Returns",
     "NBER w8308 (May 2001, doi 10.3386/w8308) = J. Business 79(3):1041-1082 (2006, doi 10.1086/500669)", "Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 1-14 of 38 (abstract, sample, accrual deciles, discussion of manipulation vs under-reaction)",
     "Accruals are reliably negatively related to future returns; NYSE/AMEX/Nasdaq firms on CRSP and Compustat, financials excluded, variables measured each April 1971-1995 on the assumption that annual data are public; high-accrual decile earns 8.8 points less in year one than the low-accrual decile. No restatements or amendments.",
     "Reporting quality is priced in the cross-section; accruals are an established characteristic.", "Accruals stay in the control set (`accruals_xs`). 'Reliability matters' is not a new idea; the amendment variable must beat accruals to count."),
    ("F02", "Harvey, Liu, Zhu 2014/2016", "Campbell R. Harvey, Yan Liu, Heqing Zhu", "... and the Cross-Section of Expected Returns", "NBER w20592 (Oct 2014, doi 10.3386/w20592) = Rev. Financial Studies 29(1):5-68 (2016, doi 10.1093/rfs/hhv059)",
     "Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 2-3 of 101 (abstract, introduction)", "Multiple-testing framework over 313 papers (working-paper version); a newly discovered factor needs a t-ratio above 3.0.",
     "Credibility threshold for a discovered signal.", "EXP-014 reports whether |t| exceeds 3.0 alongside the Holm-adjusted p; one pre-registered hypothesis family, so Holm is the formal correction."),
    ("F03", "Hou, Xue, Zhang 2017/2020", "Kewei Hou, Chen Xue, Lu Zhang", "Replicating Anomalies", "NBER w23394 (May 2017, doi 10.3386/w23394) = Rev. Financial Studies 33(5):2019-2133 (doi 10.1093/rfs/hhy131)",
     "Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 2-4 of 130 (abstract, introduction)", "Working-paper version: 447 anomalies; with NYSE breakpoints and value weights 286 (64%) are insignificant at 5% and 380 (85%) at a cutoff t of 3. The published version's counts differ and are not quoted.",
     "Replication base rate: most published cross-sectional signals fail under stricter treatment.", "Prior belief for a discovered signal should be low; the weighting and microcap treatment must be reported (universe is liquid, close >= 5)."),
    ("F04", "Cohen, Malloy, Nguyen 2018/2020", "Lauren Cohen, Christopher Malloy, Quoc Nguyen", "Lazy Prices", "NBER w25084 (Sep 2018, rev. Mar 2019, doi 10.3386/w25084) = J. Finance 75(3):1371-1415 (2020, doi 10.1111/jofi.12885)",
     "Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 1-20 of 90 (abstract, introduction, data, calendar-time and Fama-MacBeth design)", "Changes in the language of 10-K/10-Q filings (1995-2014; 10-K, 10-K405, 10-KSB, 10-Q, main text only) predict returns: 188 bp/month alpha, no announcement effect, attributed to inattention.",
     "Closest filing-derived, point-in-time signal that investors under-use; amendments are not in its sample.", "Design borrowed: firm-level clustering, Fama-MacBeth controls. Not an overlap on the variable."),
    ("F05", "Bali, Kelly, Mörke, Rahman 2023/2025", "Turan G. Bali, Bryan T. Kelly, Mathis Mörke, Jamil Rahman", "Machine Forecast Disagreement", "NBER w31583 (Aug 2023, rev. Sep 2025, doi 10.3386/w31583); SSRN 4546456; no journal version found in Crossref",
     "Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 2-4 of 101 (abstract, introduction)", "Dispersion across machine-learning model specifications ('MFD') measures belief disagreement; value-weighted decile spread 14% a year.", "Model-side uncertainty, not source reliability.",
     "Peripheral. Relevant only to a model-disagreement direction, which EXP-014 does not take."),
    ("F06", "Goulding, Harvey, Kurtović 2026", "Christian L. Goulding, Campbell R. Harvey, Hrvoje Kurtović", "Disagreement of Disagreement", "NBER w35049 (Apr 2026, doi 10.3386/w35049); SSRN 4647471 and 6566844; no journal version found",
     "Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 2-4 of 100 (abstract, introduction)", "Major investor-disagreement proxies are nearly uncorrelated; proposes a composite (DIS) from a frictionless model.", "Measurement reliability of a latent construct through noisy proxies.",
     "Peripheral; cited as context for proxy reliability."),
    ("F07", "Daniel, Sornette, Wöhrmann 2008/2009", "Gilles Daniel, Didier Sornette, Peter Wöhrmann", "Look-Ahead Benchmark Bias in Portfolio Performance Evaluation", "arXiv 0810.1922 (Oct 2008) = J. Portfolio Management 36(1):121-130 (2009, doi 10.3905/JPM.2009.36.1.121)",
     "arXiv API journal_ref and Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 1-5 and 8-10 of 16", "Holding the S&P 500 constituents known at the end of 2006 over 2001-2006 earns 6.4% a year against 2.3% for the constituents known at the start (Sharpe 0.4 against 0.1); constrained random portfolios on the same biased data are proposed as a test of any strategy.",
     "Membership known only later inflates backtests; random strategies on the same data calibrate the bias.", "Supports building the universe from each month's cross-section (done) and keeping placebo arms."),
    ("F08", "Glasserman, Lin 2023/2024", "Paul Glasserman, Caden Lin", "Assessing Look-Ahead Bias in Stock Return Predictions Generated By GPT Sentiment Analysis", "arXiv 2309.17322 (Sep 2023) = J. Financial Data Science 6(1):25-42 (2023-12-16, doi 10.3905/jfds.2023.1.143)",
     "arXiv API and Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 1 and 9-10 of 17 (abstract, summary tables, examples)", "A language model's sentiment on headlines can carry knowledge of what happened next; replacing company names with random strings changes responses; in-sample the anonymised version does better (a 'distraction' effect).",
     "Look-ahead through model memory, relevant if the live news sentiment uses a language model.", "Path B note: any replay of the live news sleeve must state the model's training cutoff and anonymise names."),
    ("F09", "Benhenda 2026", "Mostapha Benhenda", "Look-Ahead-Bench: a Standardized Benchmark of Look-ahead Bias in Point-in-Time LLMs for Finance", "arXiv 2601.13770 (Jan 2026); no journal version found",
     "arXiv API", "FULLTEXT_PARTIAL", "all 8 pages", "Five large-cap technology stocks, two six-month windows (2021, 2024); standard language models lose 15-22 points of alpha out of sample while a vendor's point-in-time models do not; no uncertainty intervals; evaluates the commercial models of a company named in the paper.",
     "Shows demand for point-in-time evaluation; evidence is thin.", "Low evidence weight. Not an overlap on amendments."),
    ("F10", "Sanderink 2026", "Ursina Sanderink", "When Alpha Breaks: Two-Level Uncertainty for Safe Deployment of Cross-Sectional Stock Rankers", "arXiv 2603.13252 (Feb 2026); no journal version found",
     "arXiv API", "FULLTEXT_PARTIAL", "pp. 1-8 and the limitations of 34", "A boosted ranker on a fixed list of 100 'AI-exposed' tickers (2016-2025) reports shadow-portfolio Sharpe 2.73 and a CAGR of 122%; gates trading on a trailing-efficacy classifier; delisting returns are not modelled and the ticker list's date of construction is not discussed.",
     "Deployment gating under regime change; a cautionary example of universe look-ahead.", "Low evidence weight for effect sizes; supports reporting delisting handling and universe construction dates."),
    ("F11", "Bracher, Funk 2026", "Johannes Bracher, Sebastian Funk", "Information leakage from data revisions in retrospective forecasts", "arXiv 2608.05883 (Aug 2026); re-analysis of Aygün et al., Nature 654:909-916 (2026) as cited there (not read)",
     "arXiv API", "FULLTEXT_PARTIAL", "all 4 pages", "The reported 11% gain over the CDC ensemble comes from using revised data; nine of 1,430 state-weeks account for 20% of the gain; relative weighted interval score is 0.69 where the last data point was later revised by 25% or more and 1.00 where revised by 1% or less.",
     "The same mechanism as restatements: later-revised numbers leak. Their concentration diagnostic is the one used here.", "Supports the decomposition by revision size and the insistence on vintage data; the finance analogue is the restating amendment."),
    ("F12", "Agyekum, Obese 2026", "Louis Agyekum, Obed Obese", "Forecasting in the Fog: Real-Time versus Revised-Data Evidence on Machine Learning's Edge over the Phillips Curve", "arXiv 2608.09033 (Aug 2026); no journal version found",
     "arXiv API", "FULLTEXT_PARTIAL", "pp. 1-4 of 27 (abstract, introduction, related work)", "Inflation forecasts from ALFRED vintages against revised data: accuracy gaps are small and mostly insignificant, but a Random Forest's reliance on PCE inflation falls from 0.778 to 0.039 mean |SHAP| in real time.",
     "Real-time versus revised data in macro machine learning.", "Motivates ALFRED vintages for the macro gate in Path B; preprint with modest evidence."),
    ("F14", "Bannouh, Geng, Peeters 2019", "Karim Bannouh, Derek (Jiewei) Geng, Bas Peeters", "Filing, Fast and Slow: Reporting Lag and Stock Returns", "SSRN 3432446, draft of 5 Aug 2019 (47-page SSRN version revised 2021 not read); no journal version found; PDF read is an author-posted copy hosted on a corporate content network",
     "SSRN abstract page title match (Crossref lists the SSRN record)", "FULLTEXT_PARTIAL", "pp. 1-3 and 7-14 of 39 (abstract, introduction, data, quintile portfolios, Fama-MacBeth)", "Sample: 10-K and 10-Q filings from EDGAR for periods ending on or after 15 Dec 2006 to 2018; reporting lag = days from period end to filing date; equal-weighted quintile spread (fast minus slow, 10-K) 36 bp a month CAPM alpha (t 2.9), 10-Q up to 40 bp (t > 4); Fama-MacBeth slope -0.00018 (t -3.3); the premium decays and is gone after 18 months; non-timely (NT) filings are included in the slowest quintile. Amendments are not studied.",
     "Closest on reporting delay; cites evidence that late filers restate more often (Blankley et al. 2014).", "Reporting delay is an established return predictor: lag and lag deterioration stay in the control set (`filing_lag_days_xs`, `lag_deterioration_r`)."),
    ("F13", "Li et al. 2015/2016", "Yaliang Li, Jing Gao, Chuishi Meng, Qi Li, Lu Su, Bo Zhao, Wei Fan, Jiawei Han", "A Survey on Truth Discovery", "arXiv 1505.02463 (May 2015, v2 Nov 2015) = ACM SIGKDD Explorations Newsletter 17(2):1-16 (Crossref issue date 2016, doi 10.1145/2897350.2897352)",
     "arXiv API and Crossref DOI record", "FULLTEXT_PARTIAL", "pp. 1-6 of 16 plus targeted search of the rest", "Truth discovery integrates conflicting multi-source claims by estimating each source's reliability jointly with the truth; surveys input types, reliability models and streaming settings; no finance application.",
     "Vocabulary and methods for source reliability when sources conflict.", "Provenance vocabulary only. This project observes corrections directly instead of estimating reliability from conflicts."),
    ("F15", "Frieder, Shanthikumar 2008", "Laura Frieder, Devin M. Shanthikumar", "After a Restatement: Long-Run Market and Investor Response", "SSRN 1106855, draft of 7 July 2008; no journal version found (Crossref, OpenAlex, 2026-10-12); PDF supplied by the owner, SHA-256 367c1fcf4e9f358a9ca7c904b08380de92bdb79f4af7ed2fa08ee780248bb932, 604,497 bytes, 60 pages",
     "Crossref and OpenAlex records agree on title, authors and year; the PDF carries no SSRN stamp, so the match rests on those three", "FULLTEXT", "all 60 PDF pages including Tables 1-11 and Figures 1-6; reference list skimmed",
     "238 negative, non-rule-change restatement announcements by NYSE firms 1993-2002 (hand-collected from newswires): raw cumulative return +4.29% (t 2.16) in trading days 64-126, +4.96% characteristic-adjusted, +4.50% matched; days 127-252 insignificant; announcement window -3.78%; no significant negative drift; explained as an information-risk shock resolved later; institutional ownership and analyst-forecast evidence.",
     "The decisive long-run paper for the event class. Its sign is POSITIVE after day 64: the premise that the negative sign is prior art is not supported by it.", "EXP-014 gained the label REVERSED and the age bins S11 before registration; review in `16_FRIEDER_SHANTHIKUMAR_FULLTEXT_REVIEW.md`."),
    ("F16", "Ghosh et al. 2025/2026", "Aloke Ghosh, Seppo Ikaheimo, Emma-Riikka Myllymaki, Jukka Sihvonen", "Long-Run Stock Returns Following Internal Control Disclosures", "J. Business Finance & Accounting 53(1):131-149 (first published 2025-09-16, issue 2026-02; received 2024-02-07, accepted 2025-09-02; doi 10.1111/jbfa.70012); open access",
     "Crossref DOI record", "FULLTEXT_PARTIAL", "open-access HTML read in the in-app browser: abstract, sections 1-3 (sample, Tables 1-4, robustness, moderators) and 6; sections 4-5 and the online appendix not read in detail",
     "220,666 firm-quarters 2007-2023 (13,610 with a material weakness); announcement-window reaction under 1%; size-matched buy-and-hold abnormal return of material-weakness firms -3.5% (60 days) and -6.7% (120 days), a gap to effective-control firms of -3.2% and -6.2%; calendar-time four-factor alpha 1.16% a month (t 4.91); confined to low institutional ownership; milder with higher price floors; 79% of weak-control firms are weak again next quarter.",
     "Closest modern long-run drift paper on a reliability disclosure; different event, persistent firm type, event date assumed rather than time-stamped.", "Supports keeping the within-firm gate R7 and the negative registered direction; not evidence about amendments."),
]

# Works read at abstract level or below, added or re-read in Phase II
ABSTRACT_ONLY = [
    ("A01", "Gondhalekar, Joshi, McKendall 2012", "Short- and Long-Term Share Price Reaction to Announcements of Financial Restatements", "Advances in Financial Economics 15:149-172 (doi 10.1108/S1569-3732(2012)0000015008)", "ABSTRACT (OpenAlex)",
     "553 restatements (GAO database) by 437 companies; three-day CAR -1.58; CAR is negative for each of the four years after the announcement, about -22% in total (four-factor model).",
     "One of several conflicting long-run results (see `17_RECENT_LITERATURE_2022_2026.md`): negative here, a positive rebound in A02 (now F15), none where cash-flow news dominates. The sign is contested, not settled."),
    ("A03", "Files, Swanson, Tse 2009", "Stealth Disclosure of Accounting Restatements", "The Accounting Review 84(5):1495-1520 (doi 10.2308/accr.2009.84.5.1495)", "ABSTRACT (Crossref)",
     "Press-release prominence of a restatement (headline, body, footnote) goes with three-day returns of -8.3%, -4.0% and -1.5%; less prominent disclosure lowers the chance of a class action.", "How restatements are disclosed shapes the immediate reaction; amendments disclosed quietly are a subset."),
    ("A04", "Irani, Xu 2011", "Do stealth restatements convey material information?", "Accounting Research Journal 24(1):5-22 (doi 10.1108/10309611111148751)", "ABSTRACT (Crossref)",
     "Since 23 Aug 2004 restatements must be disclosed in an Item 4.02 8-K; restatements disclosed only in a 10-K or 10-Q ('stealth') are less often net-income-affecting and show no market reaction at the filing date or for 22 trading days after.",
     "Closest on the channel: amendments and periodic reports as the disclosure route, and a null for the short window. EXP-014 looks at a much longer, state-variable horizon and separates value-changing from unchanged amendments."),
    ("A05", "Desai, Krishnamurthy, Venkataraman 2006", "Do Short Sellers Target Firms with Poor Earnings Quality? Evidence from Earnings Restatements", "Review of Accounting Studies 11(1):71-90 (doi 10.1007/s11142-006-6396-x)", "ABSTRACT (Crossref, SSRN version)",
     "Short interest rises months before a restatement and unwinds after the price drop; larger for high-accrual firms.", "Informed trading before the event: pre-event returns may already be negative, so a lead (anticipation) test is needed."),
    ("A06", "Gleason, Jenkins, Johnson 2008", "The Contagion Effects of Accounting Restatements", "The Accounting Review 83(1):83-110 (doi 10.2308/accr.2008.83.1.83)", "ABSTRACT (Crossref)",
     "Restatements that hurt the restating firm lower the share prices of industry peers, more so for high-accrual peers.", "Restatements move peers; sector-by-date fixed effects absorb the common part."),
    ("A08", "Blankley, Hurtt, MacGregor 2014", "The Relationship between Audit Report Lags and Future Restatements", "Auditing: A Journal of Practice & Theory 33(2):27-57 (doi 10.2308/ajpt-50667)", "ABSTRACT (Crossref)",
     "Longer audit report lags go with a higher likelihood of a future restatement.", "A reporting-delay variable predicts restatement risk, which supports controlling for delay when testing amendments."),
    ("A07", "Liu 2026", "Point-in-Time SEC Financial Data: A Reproducible Benchmark for Detecting Look-Ahead and Restatement Leakage", "SSRN 7415198 (doi 10.2139/ssrn.7415198), Elsevier SSRN posting, 2026", "ABSTRACT (Crossref); full text not reachable",
     "An eight-case, five-issuer conformance suite built from accession-level SEC filings that uses acceptance timestamps as the event clock, requires citing the controlling accession, excludes later filings and abstains during a non-reliance interval; the pilot was run by the benchmark's own operator.",
     "**Closest on point-in-time construction from SEC filings and on restatement leakage**, but a conformance benchmark for AI systems, not a return study. Weakens any claim that point-in-time SEC handling is new."),
]

# The closest works (30) with the overlap judgement; read level per row
MATRIX_COLUMNS = ["#", "Work", "Venue / version (verified)", "Read level", "What it shows (as read)", "Overlap with EXP-014", "Verdict"]


def main() -> int:
    rows = []
    for r in FULLTEXT:
        rows.append({"id": r[0], "work": f"{r[2]} ({r[1]}). {r[3]}", "version_chain": r[4], "identifier_verified_by": r[5], "read_level": r[6], "pages_read": r[7], "finding": r[8], "relevance": r[9], "decision_impact": r[10]})
    for r in ABSTRACT_ONLY:
        rows.append({"id": r[0], "work": f"{r[1]}. {r[2]}", "version_chain": r[3], "identifier_verified_by": "Crossref/OpenAlex record", "read_level": r[4].split(" ")[0], "pages_read": "", "finding": r[5], "relevance": r[6], "decision_impact": ""})
    with (HERE / "fulltext_ledger.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote fulltext_ledger.csv with {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
