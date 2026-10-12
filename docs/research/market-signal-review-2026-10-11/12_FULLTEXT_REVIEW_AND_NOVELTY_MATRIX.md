# Full-text review of the decision-critical papers, and the closest-work novelty matrix (Phase II)

Status: **newly generated 2026-10-12.** It replaces the abstract-level reading in `06_PRIOR_ART_AND_NOVELTY.md` for the works named below; that page's other rows still stand at their stated read level.
Machine-readable: `fulltext_ledger.csv` (built by `code/make_fulltext_ledger.py`) and `validation/fulltext_papers_verification.json` (identifier checks).

## 1. How the reading was done, and what it covers

* Thirteen open-access PDFs (NBER working papers and arXiv preprints) were downloaded into separate directories outside the repository, text-extracted with `pypdf` in an isolated virtual environment, and read
  in the pages listed in section 2. One PDF (NBER w8308) uses glyph-index fonts and was decoded with a character map first. **None of the 13 was read cover to cover**: the long NBER papers (90 to 130
  pages) were read for abstract, introduction, data and design, and searched for the specific claims used here. The ledger states the pages; "read" never means more than that.
* Identifiers, venues and preprint-to-publication links were verified against Crossref and the arXiv API on 2026-10-12. No contact address was sent to either service.
* No venue ranking or quartile is stated. SCImago returned HTTP 403 and the Journal Citation Reports are paywalled.
* Works whose full text could not be reached are listed in section 5. SSRN answered the in-app browser with a bot-verification page; it was not completed or worked around.

## 2. The thirteen papers read in full-text extract

| ID | Work | Version chain (verified) | Pages read | What was learned that matters here |
|---|---|---|---|---|
| F01 | Chan, Chan, Jegadeesh, Lakonishok, *Earnings Quality and Stock Returns* | NBER w8308 (2001) = *J. Business* 79(3):1041-1082 (2006) | 1-14 of 38 | Accruals predict returns negatively; annual data assumed public at each April; high-accrual decile earns 8.8 points less in year one. No restatements. **Accruals stay in the control set.** |
| F02 | Harvey, Liu, Zhu, *... and the Cross-Section of Expected Returns* | NBER w20592 (2014) = *Rev. Financial Studies* 29(1):5-68 (2016) | 2-3 of 101 | Hurdle t > 3.0 over 313 papers (working-paper version). Reported alongside the Holm-adjusted p. |
| F03 | Hou, Xue, Zhang, *Replicating Anomalies* | NBER w23394 (2017) = *RFS* 33(5):2019-2133 (2020) | 2-4 of 130 | Working-paper version: of 447 anomalies, 64% are insignificant at 5% and 85% at t = 3 with NYSE breakpoints and value weights. **Prior belief for a discovered signal should be low.** The published counts differ and are not quoted. |
| F04 | Cohen, Malloy, Nguyen, *Lazy Prices* | NBER w25084 (2018) = *J. Finance* 75(3):1371-1415 (2020) | 1-20 of 90 | Changes in 10-K/10-Q language (sample: 10-K, 10-K405, 10-KSB, 10-Q, 1995-2014; **no amendments**) earn 188 bp/month alpha with no announcement effect. Closest filing-derived inattention signal; design (Fama-MacBeth, firm clustering) borrowed. |
| F05 | Bali, Kelly, Mörke, Rahman, *Machine Forecast Disagreement* | NBER w31583 (2023, rev. 2025); no journal version found | 2-4 of 101 | Model-side dispersion as a belief-disagreement measure. Peripheral. |
| F06 | Goulding, Harvey, Kurtović, *Disagreement of Disagreement* | NBER w35049 (2026); no journal version found | 2-4 of 100 | Major disagreement proxies are nearly uncorrelated. Peripheral (proxy reliability). |
| F07 | Daniel, Sornette, Wöhrmann, *Look-Ahead Benchmark Bias* | arXiv 0810.1922 = *J. Portfolio Management* 36(1):121-130 (2009) | 1-5, 8-10 of 16 | Constituents known only at the end of 2001-2006 earn 6.4% a year against 2.3% for those known at the start; constrained random portfolios on the same data calibrate the bias. **Supports the survivorship-free universe and the placebo arms.** |
| F08 | Glasserman, Lin, *Assessing Look-Ahead Bias ... GPT Sentiment* | arXiv 2309.17322 = *J. Financial Data Science* 6(1):25-42 (2023) | 1, 9-10 of 17 | Language-model memory leaks outcomes; anonymising names changes responses. Relevant if the live news sentiment uses a language model (Path B). |
| F09 | Benhenda, *Look-Ahead-Bench* | arXiv 2601.13770 (2026) | all 8 | Five technology stocks, two six-month windows, no intervals, vendor models; low evidence weight. |
| F10 | Sanderink, *When Alpha Breaks* | arXiv 2603.13252 (2026) | 1-8 + limitations of 34 | Reports Sharpe 2.73 on a **fixed 100-ticker "AI-exposed" list** whose construction date is not discussed; delisting returns not modelled. A cautionary example of universe look-ahead; effect sizes not used. |
| F11 | Bracher, Funk, *Information leakage from data revisions* | arXiv 2608.05883 (2026) | all 4 | The reported gain comes from revised data: 9 of 1,430 state-weeks give 20% of it; relative score 0.69 where the last point was later revised by >= 25%, 1.00 where revised by <= 1%. **The same mechanism as restatements and the same concentration diagnostic.** |
| F12 | Agyekum, Obese, *Forecasting in the Fog* | arXiv 2608.09033 (2026) | 1-4 of 27 | Real-time (ALFRED) versus revised macro data: small accuracy gaps, large changes in what the model relies on (mean absolute SHAP of PCE inflation 0.778 versus 0.039). Preprint, modest evidence. |
| F13 | Li et al., *A Survey on Truth Discovery* | arXiv 1505.02463 = *ACM SIGKDD Explorations* 17(2):1-16 | 1-6 of 16 | Vocabulary for estimating source reliability from conflicting claims; no finance application. |

## 3. Works found or re-read in Phase II at abstract level

| ID | Work | Read level | What it shows | Consequence |
|---|---|---|---|---|
| A01 | Gondhalekar, Joshi, McKendall (2012), *Short- and Long-Term Share Price Reaction to Announcements of Financial Restatements*, Adv. Financial Economics 15:149-172 | ABSTRACT | 553 restatements; three-day CAR -1.58; negative CAR in each of four years after, about -22% in total | **The sign is prior art.** "Restating firms underperform for years" is not a discovery. |
| A02 | Frieder, Shanthikumar (2008), *After a Restatement: Long-Run Market and Investor Response*, SSRN 1106855 | TITLE ONLY | unknown | **Unread and probably decisive.** If it documents long-run drift, EXP-013 largely replicates known work. |
| A03 | Files, Swanson, Tse (2009), *Stealth Disclosure of Accounting Restatements*, TAR 84(5):1495-1520 | ABSTRACT | Press-release prominence goes with three-day returns of -8.3%, -4.0%, -1.5% | Disclosure route matters; quiet routes carry smaller immediate reactions. |
| A04 | Irani, Xu (2011), *Do stealth restatements convey material information?*, Accounting Research Journal 24(1):5-22 | ABSTRACT | Restatements disclosed only in a 10-K/10-Q (not an Item 4.02 8-K) show no reaction at filing or for 22 trading days | Closest on the amendment channel and short window; EXP-014 differs by horizon (state variable up to two years), content classification and controls. |
| A05 | Desai, Krishnamurthy, Venkataraman (2006), RAS 11(1):71-90 | ABSTRACT | Short sellers build positions months before restatements | Anticipation: the event-time bins in EXP-014 test whether the amendment is news or a marker. |
| A06 | Gleason, Jenkins, Johnson (2008), TAR 83(1):83-110 | ABSTRACT | Restatements depress peers, more for high-accrual peers | Sector-by-date fixed effects absorb the common part. |
| A07 | Liu (2026), *Point-in-Time SEC Financial Data: A Reproducible Benchmark for Detecting Look-Ahead and Restatement Leakage*, SSRN 7415198 | ABSTRACT | Eight-case, five-issuer conformance suite using acceptance timestamps as the event clock; abstains during non-reliance intervals; pilot run by the benchmark's own operator | **Closest on point-in-time SEC construction and restatement leakage.** A benchmark for AI systems, not a return study; it weakens any claim that PIT SEC handling is new. |

## 4. The closest studies (30), with the overlap judgement

Read levels: FT = full-text extract (pages in section 2), AB = abstract, MD = metadata only, TO = title only.

| # | Work | Read | Overlap with EXP-014 | Verdict |
|---|---|---|---|---|
| 1 | Gondhalekar, Joshi, McKendall 2012 | AB | Long-run returns after restatement announcements | Sign and persistence are known |
| 2 | Frieder, Shanthikumar 2008 | TO | Long-run response after restatements | **Unresolved; highest priority to read** |
| 3 | Palmrose, Richardson, Scholz 2001/2004 | MD | Announcement reaction | Event-study base |
| 4 | Hribar, Jenkins 2004 | MD | Cost of capital after restatements | Consequence of the event |
| 5 | Files, Swanson, Tse 2009 | AB | Disclosure route and reaction | Context |
| 6 | Irani, Xu 2011 | AB | 10-K/10-Q ("stealth") versus 8-K restatements | Closest on the channel |
| 7 | Desai, Krishnamurthy, Venkataraman 2006 | AB | Informed trading before restatements | Anticipation test needed |
| 8 | Gleason, Jenkins, Johnson 2008 | AB | Peer contagion | Sector effects |
| 9 | Wu, *Earnings Restatements: A Capital Market Perspective* (SSRN 1844265) | AB (Crossref) | Return behaviour around restatements 1977-2001 | Event-study base |
| 10 | Lev, Ryan, Wu, *Rewriting Earnings History* (SSRN 878690) | AB (Crossref) | Restatements rewrite the history investors use | Mechanism |
| 11 | Dechow, Ge, Larson, Sloan 2011 | MD | Predicting misstatements from public data | Predicts the cause, not returns |
| 12 | Karpoff, Lee, Martin 2008 | MD | Cost of misreporting | Context |
| 13 | Chan et al. 2001/2006 | FT | Reporting quality is priced | Accruals as control |
| 14 | Richardson, Sloan, Soliman, Tuna 2005 | MD | Accrual reliability | Concept of reliability |
| 15 | Sloan 1996 | MD | Accruals anomaly | Context |
| 16 | Cohen, Malloy, Nguyen 2020 | FT | Filing-derived, under-used signal | Design, not variable |
| 17 | Bannouh, Geng, Peeters 2019 | AB | Filing lag predicts returns | Reporting-delay control |
| 18 | Brooks, Cheng, Liu, Yu 2023 | AB | Early filers do better | Reporting-delay control |
| 19 | Zhang 2006 | AB | Information uncertainty and continuation | Moderator concept |
| 20 | Francis, LaFond, Olsson, Schipper 2007 | AB | Information uncertainty and drift | Moderator concept |
| 21 | Chen, Khan, Kogan, Serafeim 2020 | AB | Accounting quality and delayed processing | Channel |
| 22 | Liu 2026 | AB | PIT SEC construction; restatement leakage | **Weakens PIT novelty** |
| 23 | Bracher, Funk 2026 | FT | Revision leakage and its concentration | Analogy and method |
| 24 | Agyekum, Obese 2026 | FT | Vintage data in macro ML | Analogy |
| 25 | Daniel, Sornette, Wöhrmann 2009 | FT | Look-ahead and survivorship; random-strategy test | Placebo design |
| 26 | Glasserman, Lin 2023/24 | FT | Look-ahead through model memory | Path B note |
| 27 | Benhenda 2026 | FT | PIT benchmark for language models | Low weight |
| 28 | Sanderink 2026 | FT | PIT-safe deployment of rankers | Low weight; universe caution |
| 29 | Li et al. 2015 | FT | Source reliability estimation | Vocabulary |
| 30 | Harvey, Liu, Zhu 2016; Hou, Xue, Zhang 2020 | FT | Credibility thresholds and replication base rate | Inference standards |

Context only: Bali et al. 2023, Goulding et al. 2026, Freyberger et al. 2024, Gu, Kelly, Xiu 2020, Guo 2009.

## 5. Full texts not reached

SSRN-hosted: Frieder and Shanthikumar 2008, Palmrose et al., Hribar and Jenkins, Karpoff et al., Wu, Lev, Ryan and Wu, Bannouh et al., Brooks et al., Liu 2026. Publisher-hosted and not opened: Files et al.,
Irani and Xu, Gleason et al., Desai et al., Gondhalekar et al., Dechow et al., Richardson et al., Sloan. For these the judgement rests on the abstract or metadata, and says so.

## 6. What this changes

1. **Direction is prior art.** Long-run underperformance after restatements is documented (A01 at abstract level); informed trading precedes them (A05); the immediate reaction depends on the disclosure route (A03, A04).
   EXP-014 is therefore a test of *robustness and independence*, not of a new sign. A positive result would be a replication in a point-in-time, controlled, cross-sectional form.
2. **Point-in-time SEC construction is not new** (A07), though the cited work is a conformance suite, not a return study.
3. **What may still be new, to be claimed only if shown:** (a) the split of amendments by whether they change the reported numbers, as a point-in-time state variable; (b) the finding that an
   independent firm sample does or does not reproduce the effect; (c) the data-quality finding about EDGAR submissions timestamps (`validation` of `data/manifests/edgar_filings_v1.json`); (d) the
   cost-aware economic result, which so far is negative.
4. **Overall novelty rating: low.** Confidence moderate-low: one decisive paper (A02) is unread, SSRN and several publishers could not be searched, and the retrieval had 77% sensitivity against known anchors.

## 7. Reproducing this page

`python3 docs/research/market-signal-review-2026-10-11/code/make_fulltext_ledger.py` rewrites `fulltext_ledger.csv`. The extraction commands used `pypdf` in a throwaway environment and are not part of the repository;
the PDFs are not committed (`.gitignore` excludes `/research_papers/` and `/papers/`).
