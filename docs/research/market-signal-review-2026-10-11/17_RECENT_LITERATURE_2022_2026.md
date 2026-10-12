# Recent literature (2022 to 12 October 2026): search, full-text reading, matrix, novelty, and what it does to EXP-014

Written 2026-10-12 (Phase II continuation). It **updates** `12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md` and `06_PRIOR_ART_AND_NOVELTY.md` and replaces their statements that the direction of the effect "is prior art" and that the one decisive
paper was unread: that paper has now been read in full (`16_FRIEDER_SHANTHIKUMAR_FULLTEXT_REVIEW.md`) and it does not say what was assumed. Machine-readable files: `recent_lit_matrix.csv` (long per-paper field set), `recent_lit_screening.csv`
(every work whose title I read, with the decision and reason), `recent_lit_candidates.csv` (all 10,618 deduplicated works with their stage), `recent_lit_coverage.json`, `recent_search_log.csv`, `citation_chain_log.csv`,
`lead_verification.csv`, `recent_core_crossref.csv`. Scripts: `code/recent_lit_search.py`, `recent_lit_sweeps.py`, `citation_chains.py`, `merge_recent_lit.py`, `verify_leads.py`, `verify_core_dois.py`, `build_recent_lit_report.py`, `make_recent_lit_doc.py`.

**Evidence levels.** FULL_TEXT: every page read. FULL_TEXT_PARTIAL: the open text was read in the sections the matrix names. ABSTRACT: the abstract from Crossref, OpenAlex or a repository page, nothing more. TITLE_ONLY: title and venue verified, no abstract
retrievable. A claim in this page never rests on a higher level than the paper has. No journal ranking or quartile is asserted anywhere (see section 10).

## 1. Findings in brief

1. **What the older literature established (before 2022).** Restatement announcements are followed by large short-window losses. What happens afterwards is **disputed**: negative abnormal returns over several years (Gondhalekar et al. 2012; Moon, Lee and Waggle 2019/2020,
   both abstract level), no drift where the news is about cash flows (Hong, Lee, Park and Patro, online 2021, abstract level), and, in the one paper read in full, no significant negative drift and a significant **positive** return 64 to 126 trading days after the announcement
   (Frieder and Shanthikumar 2008: +4.3% raw, +5.0% characteristic-adjusted; sample 238 NYSE announcements 1993-2002).
2. **What changed in 2022 to 2026.** (a) Restatement research moved to mechanisms (who trades, spillovers, auditors, lenders) and to detection (machine-learning misstatement prediction, detection lag). (b) The only modern long-run drift paper found on a reliability
   disclosure finds **negative** drift after material-weakness disclosures (Ghosh et al., online September 2025: about 1.2% a month, confined to firms with low institutional ownership and milder at higher price floors). (c) A cluster of 2026 working papers turned filing-process
   variables into cross-sectional signals (Zhu: filing discipline; Ahn: late-filing narratives; Hong: a preregistered timeliness test). (d) Evaluation-design literature matured (nonstandard errors, computational reproducibility, microcap and cost effects in machine learning).
3. **What challenges the amendment-signal interpretation.** The rebound in Frieder and Shanthikumar; the persistence of the disclosure failure itself (79% of material-weakness firms report another next quarter), which makes a pooled association a firm-type association; Zhu's finding that the
   content of filing-process signals is in the cross-sectional level, not in a firm's own deviations; partial observability (an amendment is a detection); effects that live in cheap, volatile stocks; and several nulls (Jwara and Charteris; the Claremont thesis; Zhu's within-firm version).
4. **Does novelty survive?** No study found treats content-classified amendments to periodic reports (10-K/A, 10-Q/A) as a cross-sectional return predictor. The broader idea, that disclosure-reliability and filing-process variables carry cross-sectional return information,
   is partly established and crowded with unrefereed 2026 working papers. Verdict: **low to moderate** for the idea, **moderate** only as an independent-sample, preregistered, point-in-time test of a specific treatment; **not a new anomaly**. Confidence moderate-low
   (sensitivity 7 of 8 named leads found by the queries alone; SSRN and most publishers could not be searched in full).
5. **Direct versus adjacent evidence.** Direct: none found. Closest: A01 (event class, long run), A02 (reliability disclosure, long-run drift), B01 and B02 (filing-process signals with portfolio tests).
6. **Experiment needed.** The registered EXP-014 test, made two-sided and given an age decomposition (section 8). A positive result is a replication-type statement; a negative result closes the amendment direction and strengthens the case for the point-in-time scorer path.
7. **Paper options.** (i) a narrow, honest paper: preregistered independent-sample test of content-classified amendments with the clock-audit finding; (ii) the point-in-time scorer reproducibility work as the forward-looking contribution; (iii) neither is a basis for a claim of
   eligibility for any particular tier of journal.

## 2. How the search was done, and how much it covers

Sources: OpenAlex (ranked title-and-abstract search, boolean sweeps, forward citation chains), Crossref (journal articles and posted content), arXiv (q-fin, econ.EM, stat.ML), plus spot checks through Semantic Scholar, IDEAS/RePEc pages and web search. Window: publication date
2022-01-01 to 2026-10-12; online-publication date is recorded apart from the issue year wherever Crossref gives it. All requests are logged with filters, hit counts and the SHA-256 of each raw response (`recent_search_log.csv`; raw files are git-ignored because they carry publishers' abstracts).

| Item | Count |
|---|---|
| Ranked queries (43 over ten themes), each sent to OpenAlex, Crossref journals, Crossref posted content, and for 14 of them arXiv | 43 |
| Boolean sweeps (OpenAlex `title_and_abstract.search`, cursor-paged, cap 600) | 12 (truncated at the cap: S2, S5, S6, S7, S8, S12) |
| Curated arXiv queries (phrase and OR semantics; the 14 strict AND-of-all-words arXiv calls above returned only 38 records) | 9 |
| Citation chains: seed papers tried / resolved by title and author | 20 / 14 (unresolved: HJ2004, BGH2011, GBRS2012, AZZ2015, BK2006, BGPR2020); 3,714 citing works fetched |
| Logged requests / HTTP 200 / never succeeded | 179 / 164 / 0 |
| Requests that failed once and were repeated successfully | 15 (14 arXiv calls answered with a redirect because the API had moved to https; 1 Crossref call interrupted when the laptop slept) |
| Raw records retrieved | 13,733 |
| **Distinct works after deduplication** (DOI, then normalised title) | **10,618**, of which 648 came from more than one source |
| Year distribution | 2022: 1,608, 2023: 1,751, 2024: 1,862, 2025: 2,366, 2026: 3,031; **2024 to 2026: 7,259 (68%)** |
| Works with a domain term (finance, accounting, markets) / with a topical keyword as well | 8,041 / 4,409 |
| Works with a restatement or amendment term in the title | 233 |
| Works without an abstract in any source | 2,871 |

Raw records by source:

| Source | Records |
|---|---|
| Crossref | 1,720 |
| Crossref-preprints | 1,290 |
| OpenAlex | 6,763 |
| OpenAlex-chain | 3,714 |
| arXiv | 246 |

**Screening** (`recent_lit_screening.csv`; stage and decision for every work in `recent_lit_candidates.csv`):

| Stage | Works | What it means |
|---|---|---|
| L1 off domain | 2,547 | no finance or accounting term; excluded by rule, not read |
| L1 not topical | 3,613 | domain term but none of the restatement, machine-learning, design, point-in-time or accounting-quality keywords; excluded by rule, not read |
| L1 topical, rule only | 3,963 | keywords present, **not read**; kept in the table, no decision |
| **L2 titles read by me** | **495** | the reading set: every restatement- or amendment-titled work, design and point-in-time titles in finance and working-paper venues, widely retrieved or cited machine-learning return-prediction titles, the boolean-sweep members on late filing, Item 4.02, accounting quality and internal control, and the matrix works |
| of which included as core (matrix rows found in the candidate table) | 36 | 31 with an abstract read, 5 title only |
| of which included as context (listed, not in the matrix) | 110 | consequences of restatements, misstatement detection, design, point-in-time, reproducibility |
| of which excluded after reading | 349 | determinants audit governance: 108, not finance: 35, off question: 205, retracted: 1 |

The decision for a restatement-titled work outside the matrix was assigned by the title rules in `build_recent_lit_report.py` after I read all the titles; the abstract was read for the matrix works only. The matrix has 43 rows (37 of them are in the candidate table; the rest are
pre-2022 bridging papers found by web search, an arXiv paper and a thesis). Evidence levels in the matrix: ABSTRACT 35, FULL_TEXT 1, FULL_TEXT_PARTIAL 1, RETRACTED 1, TITLE_ONLY 5. Matrix rows by group: A restatement returns: 16, B filing-process signals: 9, C design and ML: 18.

**Full texts examined.** Sixteen distinct sources in Phase II, two of them in this continuation: Frieder and Shanthikumar (all 60 pages, the owner's PDF) and Ghosh et al. (the open-access HTML read in the in-app browser, sections named in the matrix).
**Not available:** SSRN abstract and download pages (bot verification, not worked around), the Wiley PDF of Lalwani et al. (paywalled although OpenAlex flags it hybrid open access), the American Accounting Association site, ScienceDirect, INFORMS (refusals), and the Elsevier,
T&F and Wiley full texts of closed articles. Five matrix works are TITLE_ONLY because no abstract could be retrieved.

**Sensitivity.** The queries found 7 of the owner's 8 named leads without being told about them; the one missed, Kang, Ryu and Webb (2025, Financial Innovation), is a Korean-market machine-learning paper outside the queries' vocabulary. Nine curated arXiv queries found no restatement or amendment work at all, which says that accounting-disclosure research is not on arXiv, not that none exists. That is a small and possibly biased
check, not a recall estimate. OpenAlex's citation graph is incomplete (Frieder and Shanthikumar shows 5 citing works in the window, none about post-restatement returns; I cannot tell whether that is the literature or the index). **The search was not interrupted, but it is not exhaustive:**
Google Scholar was not used (no automated access), SSRN could not be searched directly, and the boolean sweeps for amendments, point-in-time data and replication hit the 600-work cap (ranked by relevance, so the tail was not read).

## 3. The eight named leads, verified

Each was checked by DOI in Crossref and OpenAlex (and in Semantic Scholar for the six that were tried; five were found). The first-online date is kept apart from the issue date; they differ for every journal article.

| Lead | As described in the brief | Verified venue, volume, pages | First online | Issue / print | Status | What it says (evidence level in the matrix) |
|---|---|---|---|---|---|---|
| L1 | Cheng, Jiang, Zhao & Zhao (2025), Journal of Empirical Finance 81:101598 | Journal of Empirical Finance 81 101598 | 2025-02-25 | 2025-03 | verified | linear regression with cross-market screening is competitive with ML in out-of-sample forecasts and after costs (time-series setting) |
| L2 | Lalwani, Meshram & Jindal, Empirical Asset Pricing via Machine Learning: The Role of... | European Financial Management 32 816-833 | 2025-11-07 | 2026-06 | verified; published version has 5,376 portfolios, the SSRN predecessor 1,152 | nonstandard errors up to five times the standard errors; micro-caps and value-weighting matter most |
| L3 | Accounting vs Technical Information: What Matters More for Stock Return Predictability?... | Journal of International Financial Markets, Institutions and Money 104 102207 | 2025-08-25 | 2025-10 | verified; authors are Cakici and Zaremba (the brief gave only the title) | technical data beat accounting data in ML forecasts, accounting is better at long horizons and cheaper to trade |
| L4 | Jo & Kim (2026), Financial Analysts Journal, Rethinking Variable Importance in Machine... | Financial Analysts Journal 82 92-135 | 2026-02-27 | 2026-04-03 | verified | microcaps inflate ML returns; in-sample importance overfits; some predictors have negative out-of-sample importance |
| L5 | Kang, Ryu & Webb (2025), Financial Innovation 11:128 | Financial Innovation 11 128 | 2025-11-27 | 2025-11-27 | verified; the DOI was found by a citation-string search | Korean market; tree-based models best; moderate complexity wins with short histories |
| L6 | Du & Tu (2025), Accounting & Finance 65(3):2420-2453 | Accounting & Finance 65 2420-2453 | 2025-02-14 | 2025-09 | verified; Wiley title carries markup | predicts restatements from MD&A tone changes in China: detection side, no returns |
| L7 | Trading Behavior and Price Adjustment Following Earnings Restatement Disclosures by US... | Journal of Corporate Accounting & Finance 37 148-161 | 2025-12-02 | 2026-04 | verified in OpenAlex and Semantic Scholar; Crossref answered 429 once and the record was found later | price and volume adjust gradually after restated-earnings announcements; event-window design |
| L8 | Mammadova (2026), SSRN 6564098 (working paper) | SSRN Electronic Journal  | 2026-01-01 | 2026 | verified; SSRN working paper, proprietary data | 1,004 firms 2010-2025; reactions gradual; single versus double restatements |

Other facts found while verifying: the SSRN predecessor of Lalwani et al. had 1,152 strategies and a different title; Ghosh et al. is in Volume 53 Issue 1 (February 2026) although first published 16 September 2025; Yang and Zhu is TAR 101(2), online 9 February 2026; one record (`10.1016/j.jacceco.2022.101573`) is **retracted** and is
excluded from every conclusion.

## 4. Evidence by theme (matrix row ids in brackets)

**T1 Restatements and returns.** Announcement-window studies continue (A08, A09, A10 and unread A11, A12). Investor trading after restatements is slow for retail investors (A05) and institutional holdings fall, more so for high-trust investors (A04); short sellers use restatement spillovers and
their trading predicts negative returns for exposed peers (A06). Post-restatement underperformance appears again in a modern sample but only for firms with aggressive policy choices (A03). Long-run drift evidence is older and split (A15, A16 against A01). **Nothing modern re-estimates the rebound of A01.**

**T2 Amendments and economic content.** The 10-K/A appears as an outcome (B07: CAM persistence predicts a later 10-K/A; B02: late-filing narratives predict 8-K Item 4.02 / 10-K/A / 10-Q/A) and in industry-level descriptives, never as a classified return predictor. Stealth and little-r revisions are studied for disclosure choices and
auditors (Files et al. citations), not for returns. Search for amended-filing market reactions in OpenAlex returned no relevant work.

**T3 Filing delays, accounting revisions, point-in-time fundamentals.** Timeliness predicts returns (B06; B01) but, per B01, as a level. Point-in-time construction is now a topic with many unrefereed frameworks (C13 and others in the screening ledger); the rigorous evidence is on revisions and look-ahead in other settings (Bracher and Funk; Levy C12; Glasserman and Lin).
Detection lag inflates misstatement-prediction performance (C14, C15).

**T4 Accounting information quality and uncertainty.** Misstatement-prediction scores earn cross-sectional alpha in one 2026 working paper (B03) and none in another form (B09). Accounting information is weaker than technical information for 21-session ML forecasts (C03).

**T5 Reactions to corrections and material disclosures.** Material weaknesses: negligible announcement reaction, large later drift (A02). Restatements: weak short-window reactions in small markets (A09), non-GAAP credibility spillover (A10).

**T6 Modern machine learning for equity prediction.** A linear approach can match machine learning (C02); tree models do well with modest data (C05); gains concentrate in hard-to-trade stocks and vanish with costs and microcap exclusion (C04, C06).

**T7 Reproducibility.** Computational reproducibility is 52% in a large test (C10); nonstandard errors are sizeable (C07, C08, C01); a registered mechanical rule is the answer the field has, and A13 shows a published result overturned by design choices.

**T8 Design sensitivity, model selection, multiple testing.** C01, C07, C08 (nonstandard errors), C09 (replication is better than feared; a counterweight to the pessimistic prior), plus the false-discovery working papers in the screening ledger.

**T9 News and text features.** Not in EXP-014. Text-based misstatement prediction (B08, A-series detection context) and look-ahead in language models (C12) are noted for any future arm.

**T10 Data provenance, freshness, staleness.** The vendor-discrepancy paper found is retracted (C16). Fresh-versus-stale signal papers are unrefereed working papers (screening ledger). The Phase II finding that EDGAR's submissions JSON carries a wrong acceptance time for 28.2% of matched filings remains unmatched in the literature found.

## 5. Treatment comparison

| Work | Treatment | Unit and outcome | Clock | Overlap with EXP-014's treatment |
|---|---|---|---|---|
| EXP-014 | content-classified amendment to a periodic report (value-changing, other, unchanged, unclassifiable; also Item 4.02, late notices, amendments without statements as comparators), trailing 730 days, age bins | firm-date, 21-session forward return rank, date x sector effects, 17 controls | FSDS acceptance stamp, usable the next session if after 16:00 | - |
| A01 Frieder and Shanthikumar | first public restatement announcement | event windows to 252 days, calendar-time portfolios | newswire date | different event (announcement), long run, pre-XBRL |
| A02 Ghosh et al. | material weakness disclosed in a quarter | BHAR 60/120 days, calendar-time alpha | earnings date assumed | different event; persistent firm type |
| A03 Ecker et al. | restatement versus non-restatement, conditional on aggressiveness | pre- and post-restatement abnormal returns | not stated in the abstract | restatement firms only |
| B01 Zhu | late quarterly filing, NT notices, 8-K irregularity (levels and deviations) | quintile portfolios, six-factor alpha | filing timestamps | filing-process variables, not amendments |
| B02 Ahn | language-model class of NT narratives | 90-day long-short basket; amendments as outcome | acceptance timestamp, next trading day | uses 10-K/A as outcome, not treatment |
| B03 Wang | misstatement-prediction scores | cross-sectional alpha | not stated | score, not event |

How EXP-014 compares on the dimensions the brief lists:

* **Any amendment versus value-changing.** No modern study splits amendments by whether the numbers change. EXP-014's H2 (any) and H1 (value-changing) do; S3 (unchanged numbers), S4 (unclassifiable) and S10 (amendments without statements) are the comparators.
* **Initial restatement versus later filings.** Restatement papers date the first public announcement; an amendment filing usually follows an earnings release or an Item 4.02 8-K by days to months. S9 adds Item 4.02 and late notices as competing indicators and S11 shows where in time after the amendment any effect sits.
* **Restatement versus non-restatement amendments.** The literature found is about restatements. Amendments that restate nothing (unchanged numbers, Part III, exhibits) are untouched.
* **Event-window reactions versus cross-sectional prediction.** Event windows: A06, A08 to A10. Cross-sectional prediction with portfolios: B01 to B03 (different variables). EXP-014 is a regression of forward ranks on a trailing exposure with fixed effects and controls.
* **Static quality versus time-varying content.** B03 and restatement-likelihood scores are static quality; EXP-014's windows, age bins and R7 are time-varying.
* **Long-run performance versus incremental forecasts.** A01, A02, A16 measure long-run abnormal performance. EXP-014 reports a conditional coefficient plus a paired machine-learning increment and a cost-aware portfolio, kept separate from the decision.
* **Historical availability versus what an investor could observe.** A02 assumes the earnings date; A01 uses newswire dates; B02 uses acceptance timestamps; EXP-014 uses audited acceptance stamps and records that EDGAR's own submissions stamps are wrong for 28.2% of matched filings.

## 6. Novelty assessment

* **Covered by prior work:** announcement reactions to restatements; the existence of slow processing and informed trading around restatements; drift after another reliability disclosure (material weaknesses); filing-timeliness as a return predictor; point-in-time SEC construction (a language-model benchmark exists).
* **Not found:** a cross-sectional return test of content-classified periodic-report amendments; an amendment-versus-restatement comparison; the acceptance-clock audit of EDGAR's submissions JSON; a preregistered independent-sample test of any of these.
* **Verdict.** Not a new anomaly and not a basis for a claim of one. The defensible contribution is a preregistered, point-in-time, independent-sample test of a specific treatment under a mechanical rule, with a data-quality finding. Confidence moderate-low (section 2, sensitivity).
* **What would change the verdict:** a 2024 to 2026 paper on 10-K/A return effects that this search could not reach (SSRN-only working papers are the likeliest place); a published follow-up of Frieder and Shanthikumar outside OpenAlex's index.

## 7. Stress test of EXP-014 against the machine-learning, design and point-in-time literature

| Issue | Evidence | Response in the protocol |
|---|---|---|
| Training window | C01: window length matters more for neural networks; boosted trees need about five years | arms and folds are the recorded EXP-006 plan, no hyperparameter is chosen on any data; sensitivity to the window is **not** tested (limitation) |
| Filters, liquidity, microcaps | C04, C06, C08, C01 | universe is liquidity ranks 251 to 1,000 with close >= 5; S12 reports the more and the less liquid half |
| Baseline strength | C02, C03, C05 | ridge (M0) and boosted (G0) baselines on 76 features; an increment is judged against both; a conventional model matching the approach is reported as such |
| Model family | C01, C05, C11 | ridge and boosted trees only; target is a relative rank; no neural networks in the registered arms |
| Feature selection and importance | C04 | none used; no importance ranking informs any decision |
| Portfolio construction, rebalancing, turnover, costs | C06, C08 | the frozen EXP-010B 21-session portfolio, reported at 10, 30 and 50 bp with the cost share of gross; not part of the decision |
| Evaluation period, regimes | C06, C09 | eight recorded folds; gates R3 (calendar years) and R6 (sectors) |
| Inference and repeated experimentation | C07, C09, A13 | one registered run; Holm over H1 and H2; wild-cluster bootstrap with the null imposed; trial ledger; no post-hoc change (a material revision would be a separate study) |
| Partial observability, detection lag | A14, C14, C15 | treatment dated at the amendment's own availability session; the coefficient is the price relevance of a detection event, stated as a limit |
| Reproducibility | C10 | definition fingerprint, input hashes, deterministic seeds, fresh-process reload of the saved model |
| Vendor discrepancies | C16 (retracted) | not used as evidence |

## 8. Decision on EXP-014 (the six questions)

1. **Is the question genuinely unresolved?** Yes. The sign of any post-disclosure effect is contested (A01 against A02, A03, A16), and no study of content-classified amendments exists in what was found. The discovery sample (18 treated firms) is suggestive only.
2. **Is the treatment distinguishable from the closest recent studies?** Partly. Value-changing amendments overlap with restatement events, but the filing-based, point-in-time, trailing-exposure treatment and its comparators (S3, S4, S10), and the cross-sectional estimand, differ from every study in section 5.
3. **Are sample, timing and inference adequate?** For large effects. 65 treated firms, 2,277 treated rows; acceptance stamps audited; wild-cluster inference whose size was measured on the real label structure (pooled over-rejects 13.3%, within firm 6.3%, hence the R7 requirement). Power against half the discovery effect is roughly two in three within firm (section 6 of the preregistration).
   A null excludes only large effects.
4. **Would the registered result change the research decision?** Yes. SURVIVES or FRAGILE keeps the amendment direction as the primary line; REVERSED redirects it to the rebound hypothesis; NOT_REPLICATED or INCONCLUSIVE moves the weight to the point-in-time scorer work (`14_PATH_A_VS_PATH_B.md`).
5. **Can it run without the sealed holdout?** Yes: the sample ends 2025-05-09, prices are capped 2025-06-30, the holdout starts 2025-08-26 and the guard checks it.
6. **Is the data adequate and legally usable?** SEC data are public. Prices come from a community dataset whose redistribution terms have not been reviewed: derived statistics may be published, prices may not, and the owner's licence decision stays open.

**Decision: EXP-014 remains the best next test.** Because the full-text reading and this update change what the data may show, three changes were made before registration and before any amendment variable was related to a return on the independent sample: the label REVERSED (positive coefficient, two-sided
p < 0.05), the age bins S11 and the liquidity halves S12. None can change SURVIVES, FRAGILE or INCONCLUSIVE. If recent work had made the test redundant the smallest alternative would have been the point-in-time scorer audit (Path B); it is not redundant.

## 9. Contrary evidence, unresolved points, items not verified

* Contrary to a negative sign: A01 (rebound), A15 (no drift when cash-flow news dominates), A09 (negligible reactions), B09 (null strategy), Zhu's within-firm null. Supporting a negative sign: A02, A03, A16, A06, B03.
* Web-search leads **not verified at source** and not used for any conclusion: an Audit Analytics note reporting positive long-term abnormal returns (up to 3.28%) after the resolution of non-reliance restatements 2005 to 2016; a figure of 27% downward drift over 36 months from an older study.
* The SSRN-only working papers (A05, A07, A11, B01 to B05, B08, C13, C17, C18) are unrefereed and their abstracts are the only evidence read; their large reported alphas are concentrated in small and volatile stocks.
* Unresolved: whether any 2024 to 2026 work on 10-K/A returns exists outside the indexes reached; the full text of every ABSTRACT-level paper; the Item 4.02 event studies (A11) and executive-turnover study (A12).

## 10. Journal positioning

No claim of eligibility for any tier of journal is made and no ranking is quoted: SCImago and the Journal Citation Reports could not be reached in Phase II. Candidate venues will be named only after the contribution is settled by the registered result and each ranking claim is checked against a reliable current source.

## 11. Core matrix (summary; full fields in `recent_lit_matrix.csv`)

"First online" is the Crossref online-publication date for journal articles, the Crossref creation date for SSRN working papers, and the draft date for Frieder and Shanthikumar; NR means not retrieved.

| ID | Work | First online | Evidence | Relation | Why it matters |
|---|---|---|---|---|---|
| A01 | Frieder, L. & Shanthikumar, D. M. (2008). After a Restatement: Long-Run Market and Investor Response. SSRN working... | 2008-07-07 (date of the draft) | FULL_TEXT | CHALLENGES_SIGN | closest long-run return evidence for the event class; its sign contradicts the premise that the negative sign is prior art; motivates S11 and the... |
| A02 | Ghosh, A., Ikaheimo, S., Myllymaki, E.-R. & Sihvonen, J. Long-Run Stock Returns Following Internal Control... | 2025-09-16 | FULL_TEXT_PARTIAL | SUPPORTS_NEGATIVE | closest modern long-run-drift analogue for a disclosure-reliability variable; supports the negative direction for a persistent firm type; no... |
| A03 | Ecker, F., Francis, J., Olsson, P. M. & Schipper, K. Payoffs to Aggressiveness. The Accounting Review | 2023-10-23 | ABSTRACT | SUPPORTS_NEGATIVE | post-restatement underperformance in a modern sample, conditional on aggressiveness; not amendments |
| A04 | Cahan, S., Chen, C. & Chen, L. In Financial Statements We Trust: Institutional Investors' Stockholdings after... | 2024-02-05 | ABSTRACT | ADJACENT | supports an institutional-exit channel around restatements, the channel Frieder and Shanthikumar examine |
| A05 | Bangert, J. & Myers, L. The Differential Effects of Non-Reliance Restatements on Retail and Institutional Investor... | 2023-10-09 | ABSTRACT | ADJACENT | slow processing by retail investors supports an underreaction channel after restatement disclosures |
| A06 | Sun, J. & Sun, W. Short Selling and the Spillover Effect of Restatement Filings: Evidence on Disclosure-Processing... | 2026-08-27 | ABSTRACT | ADJACENT | mechanism evidence that informed traders use restatement information with frictions; peers, not the restating firm |
| A07 | Mammadova, G. Stock Market Reactions to Financial Restatements: Global Evidence from a Proprietary Company-Level Panel... | 2026-04-17 | ABSTRACT | ADJACENT | gradual adjustment to restatements in recent data; proprietary data cannot be reproduced |
| A08 | Trading Behavior and Price Adjustment Following Earnings Restatement Disclosures by US Multinational Corporations.... | 2025-12-02 | ABSTRACT | ADJACENT | gradual adjustment after restatement disclosure, event-window design |
| A09 | Jwara, N. & Charteris, A. Do financial restatements matter to investors? Evidence from South Africa. Journal of... | 2026-07-22 | ABSTRACT | CHALLENGES_SIGN | short-window null in a small market |
| A10 | Sofilkanitsch, C. Do Investors Respond Differently to Non-GAAP Earnings After Material GAAP Restatements? Accounting... | 2026-04-07 | ABSTRACT | ADJACENT | credibility spillover after restatements; not a return-prediction design |
| A11 | Schroeder, J. & Posch, P. Effects of Non-Reliance Disclosures in Form 8-K Filings on Stock Prices. SSRN working paper... | 2025-01-31 | TITLE_ONLY | ADJACENT | title indicates an Item 4.02 event study; cannot be characterised further |
| A12 | Zhang, Z., Lao, B. & Park, J. Pre-restatement executive turnovers and investor reactions. Advances in Accounting | 2025-06-13 | TITLE_ONLY | ADJACENT | title indicates an announcement-window design |
| A13 | Lewis-Western, M., Seidel, T. & Wilkins, M. Do Restatements Generate Contagion? A Re-Examination. Review of Accounting... | 2026-07-08 | ABSTRACT | DESIGN_STRESS | a replication that overturns a published result through design choices: an argument for registered, mechanical rules |
| A14 | Barton, F. J., Burnett, B. M., Gunny, K. A. & Miller, B. P. The Importance of Separating the Probability of Committing... | 2022-12-19 | ABSTRACT | DESIGN_STRESS | an amendment is a detection and disclosure event: EXP-014 measures its price relevance, not the misstatement's |
| A15 | Hong, Lee, Park & Patro. An Analysis of the Sources of Value Loss Following Financial Restatements. Journal of... | 2021-02-09 | ABSTRACT | CHALLENGES_SIGN | the sign of any post-restatement drift depends on the type of news |
| A16 | Moon, Lee & Waggle. Long-run equity performance of firms that restate financial statements. Managerial Finance... | 2019-11-18 | ABSTRACT | SUPPORTS_NEGATIVE | negative long-run drift in an older sample |
| B01 | Zhu, L. Filing Discipline: Regulatory Disclosure Behavior and the Cross-Section of Stock Returns. SSRN working paper... | 2026-09-30 | ABSTRACT | ADJACENT | the closest modern analogue of EXP-012's finding (filing-process variables carry cross-sectional content); its level-versus-deviation result is the... |
| B02 | Ahn, H. Reading the Late-Filing Notification: Form NT Body Narratives Predict Subsequent SEC Restatement Disclosures.... | 2026-07-09 | ABSTRACT | ADJACENT | uses amendments as an OUTCOME of a late-filing signal and an acceptance-timestamp clock (63.5% of filings clear the intake queue after the close); a... |
| B03 | Wang, R. Measures of Accounting Quality and the Cross-Section of Stock Returns. SSRN working paper 6881278 (2026) | 2026-06-12 | ABSTRACT | SUPPORTS_NEGATIVE | misstatement-prediction scores as return predictors: a different variable from amendment counts, same family as EXP-012's reliability variables |
| B04 | Wang, R. Beyond Binary Detection: The Information Content of Misstatement Prediction Models. SSRN working paper... | 2026-06-12 | TITLE_ONLY | ADJACENT | title suggests return content of misstatement scores; cannot be characterised |
| B05 | Hong, S. Phase 19: Filing Timeliness and Post-Earnings Announcement Drift (PEAD). OSF preregistration (2026) | NR | ABSTRACT | ADJACENT | a preregistered filing-timeliness test; shows the design (registered strata, forward-priority matching) but no result in the abstract |
| B06 | Brooks, L., Cheng, Y., Liu, L. & Yu, M. (2023). The Timeliness of 10-K Filings, Financial Performance, and Stock... | 2023-10-11 | ABSTRACT | ADJACENT | reporting-delay control; amendments not studied |
| B07 | Zhang, J., Choo, W. C., Yee, C. L., Lin, Y. & Tian, H. Critical Audit Matter Persistence and Future Reporting... | 2026-06-25 | ABSTRACT | ADJACENT | 10-K/A as an outcome, not a return predictor; small sample |
| B08 | Konchada, S. Separating Genuine Complexity from Concealment in 10-K Filings: Evidence from Income-Decreasing... | 2026-06-09 | ABSTRACT | ADJACENT | restatement prediction from text, no returns |
| B09 | Rende, J. M. Predicting Accounting Misstatements: A Strategy for Generating Abnormal Returns. Claremont Colleges... | NR | ABSTRACT | CHALLENGES_SIGN | a null for the strategy form of misstatement scores; low evidence weight |
| C01 | Lalwani, V., Meshram, V. & Jindal, V. Empirical Asset Pricing via Machine Learning: The Role of Research Design... | 2025-11-07 | ABSTRACT | DESIGN_STRESS | argues for fixing and reporting design choices; EXP-014's single registered specification is one draw, so S12 and R4 report the high-impact choices |
| C02 | Cheng, T., Jiang, S., Zhao, A. B. & Zhao, J. Is machine learning a necessity? A regression-based approach for stock... | 2025-02-25 | ABSTRACT | DESIGN_STRESS | a conventional model matching ML is meaningful evidence; EXP-014 keeps ridge arms beside boosted arms and lets neither rescue H1 |
| C03 | Cakici, N. & Zaremba, A. Accounting vs technical information: what matters more for stock return predictability?... | 2025-08-25 | ABSTRACT | DESIGN_STRESS | accounting-derived features add little at a 21-session horizon beside price features: expect small ML increments in EXP-014 (M1 versus M0) |
| C04 | Jo, Y. & Kim, Y. H. Rethinking Variable Importance in Machine Learning: An Economic Perspective on Empirical Asset... | 2026-02-27 | ABSTRACT | DESIGN_STRESS | EXP-014's universe (liquidity ranks 251-1,000, price >= $5) excludes microcaps by construction; no importance ranking is used for any decision |
| C05 | Kang, Y., Ryu, D. & Webb, R. I. How well do machine learning models in finance work? Financial Innovation | 2025-11-27 | ABSTRACT | DESIGN_STRESS | supports moderately complex (boosted tree) arms for a modest sample |
| C06 | Avramov, D., Cheng, S. & Metzker, L. Machine Learning vs. Economic Restrictions: Evidence from Stock Return... | 2022-06-29 | ABSTRACT | DESIGN_STRESS | a reason to report the economic side separately and at three cost levels (10, 30, 50 bp) on a non-microcap universe |
| C07 | Menkveld, A. J. et al. Nonstandard Errors. The Journal of Finance | 2024-04-17 | ABSTRACT | DESIGN_STRESS | supports registered, mechanical rules and published code; one specification still understates uncertainty |
| C08 | Soebhag, A., Van Vliet, B. & Verwijmeren, P. Non-standard errors in asset pricing: Mind your sorts. Journal of... | 2024-06-05 | ABSTRACT | DESIGN_STRESS | the same lesson for portfolio construction: EXP-014's portfolio is frozen from EXP-010B and reported at three cost levels |
| C09 | Jensen, T. I., Kelly, B. & Pedersen, L. H. Is There a Replication Crisis in Finance? The Journal of Finance | 2023-06-09 | ABSTRACT | DESIGN_STRESS | a counterweight to the pessimistic prior used from Hou-Xue-Zhang; EXP-014 corrects over its own two hypotheses only |
| C10 | Perignon, C. et al. Computational Reproducibility in Finance: Evidence from 1,000 Tests. Review of Financial Studies | 2024-06-21 | ABSTRACT | PIT_PIPELINE | EXP-014's fingerprint, input hashes and fresh-process reload check address exactly this |
| C11 | Howard, C. Choices Matter When Training Machine Learning Models for Return Prediction. Financial Analysts Journal | 2024-08-29 | ABSTRACT | DESIGN_STRESS | EXP-014's target is already a relative (rank) return |
| C12 | Levy, B. Caution Ahead: Numerical Reasoning and Look-ahead Bias in AI Models. Journal of Accounting Research | 2026-05-06 | ABSTRACT | PIT_PIPELINE | no language model feeds EXP-014; relevant to any future text arm |
| C13 | Liu, F. Point-in-Time SEC Financial Data: A Reproducible Benchmark for Detecting Look-Ahead and Restatement Leakage.... | 2026-09-11 | ABSTRACT | PIT_PIPELINE | point-in-time SEC construction is not new; this is a language-model conformance test, not a return study |
| C14 | Yang, L. & Zhu, M. Misstatement Detection Lag and Prediction Evaluation. The Accounting Review | 2026-02-09 | ABSTRACT | PIT_PIPELINE | EXP-014 labels nothing by detection: the treatment is dated at the amendment's own availability session, so the lag problem does not enter, but the... |
| C15 | Zavitsanos, E. et al. Financial misstatement detection: a realistic evaluation. ICAIF 2021 (arXiv 2305.17457) | NR | ABSTRACT | PIT_PIPELINE | foundational for the detection-lag point (arXiv v1 2023, conference 2021) |
| C16 | Du, K., Huddart, S. & Jiang, X. Lost in standardization: Effects of financial statement database discrepancies on... | 2022-12-26 | RETRACTED | RETRACTED | a retracted paper on vendor database discrepancies: excluded from every conclusion |
| C17 | Jo, Y. & Kim, Y. Sample Splitting Choices Matter: Evidence from Machine Learning in Empirical Asset Pricing. SSRN... | 2025-04-15 | TITLE_ONLY | DESIGN_STRESS | title is on point for training-window and split choices; cannot be characterised |
| C18 | Chen, M., Hanauer, M. X. & Kalsbach, T. Design choices, machine learning, and the cross-section of stock returns. SSRN... | 2024-12-02 | TITLE_ONLY | DESIGN_STRESS | title is on point for design sensitivity; cannot be characterised |

## 12. Postscript: what the registered run (EXP-014, commit fa1469c) says about the competing readings above

Written after the run; sections 1 to 11 were written before it and are unchanged. Registered outcome: **FRAGILE**, interpretation MARKER_OF_PERSISTENT_TROUBLE (`docs/EXP_014_RESULTS.md`).

* **Sign.** The pooled coefficient is negative (-0.0537, Holm-adjusted p 0.0208), the direction of the older long-run studies and of Ghosh et al., but it is absent in the first year after the amendment (-0.0013) and present for firms that will file one within a year (-0.0747) and in amendments one to two years old (-0.1121): it is not a drift that follows the amendment.
* **The Frieder and Shanthikumar rebound** is neither shown nor excluded: the 90-179 and 180-364 day bins are +0.0531 and -0.0150, both indistinguishable from zero. With Item 4.02 announcements and late-filing notices in the model the core-amendment coefficient turns positive (+0.0587, two-sided p 0.054), which is the direction a post-announcement rebound would take, but this is a descriptive secondary analysis.
* **Firm type versus event.** The within-firm test fails narrowly (coefficient -0.0551, one-sided p 0.0566 against 0.05) and so does the influence gate; the pattern fits the persistence of disclosure failures (Ghosh et al.) and Zhu's level-versus-deviation result, though the data cannot separate a within-firm effect from none.
* **Novelty.** The amendment-specific claim was not established as an event effect. What stands out descriptively is that the Item 4.02 announcement, in state-variable form, carries a stronger negative association (-0.0832, two-sided p 0.0006) than the amendment; it is a secondary, uncorrected result and needs its own registration before it is a finding.
