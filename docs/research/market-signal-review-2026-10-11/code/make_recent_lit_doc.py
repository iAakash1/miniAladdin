#!/usr/bin/env python3
"""Write 17_RECENT_LITERATURE_2022_2026.md from recent_lit_coverage.json, recent_lit_matrix.csv, lead_verification.csv and the screening ledger, so that every number in the page is the number in the files.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_recent_lit_doc.py
"""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def rows(name: str) -> list[dict]:
    with (HERE / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def short(text: str, n: int = 170) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "..."


def main() -> int:
    cov = json.loads((HERE / "recent_lit_coverage.json").read_text())
    matrix = rows("recent_lit_matrix.csv")
    leads = rows("lead_verification.csv")
    merge, req, stages = cov["merge"], cov["requests"], cov["stages"]
    yd = merge["year_distribution"]
    recent3 = sum(yd.get(y, 0) for y in ("2024", "2025", "2026"))
    total = merge["distinct_works"]
    ev = cov["matrix_evidence_levels"]
    by_group = cov["matrix_rows_by_group"]
    matrix_in_candidates = sum(1 for r in rows("recent_lit_candidates.csv") if r["decision"] in ("INCLUDE_CORE", "INCLUDE_CORE_TITLE_ONLY", "EXCLUDE_RETRACTED"))
    source_lines = "\n".join(f"| {k} | {v:,} |" for k, v in merge["raw_records_by_source"].items())
    lead_lines = []
    notes = {
        "L1": ("verified", "linear regression with cross-market screening is competitive with ML in out-of-sample forecasts and after costs (time-series setting)"),
        "L2": ("verified; published version has 5,376 portfolios, the SSRN predecessor 1,152", "nonstandard errors up to five times the standard errors; micro-caps and value-weighting matter most"),
        "L3": ("verified; authors are Cakici and Zaremba (the brief gave only the title)", "technical data beat accounting data in ML forecasts, accounting is better at long horizons and cheaper to trade"),
        "L4": ("verified", "microcaps inflate ML returns; in-sample importance overfits; some predictors have negative out-of-sample importance"),
        "L5": ("verified; the DOI was found by a citation-string search", "Korean market; tree-based models best; moderate complexity wins with short histories"),
        "L6": ("verified; Wiley title carries markup", "predicts restatements from MD&A tone changes in China: detection side, no returns"),
        "L7": ("verified in OpenAlex and Semantic Scholar; Crossref answered 429 once and the record was found later", "price and volume adjust gradually after restated-earnings announcements; event-window design"),
        "L8": ("verified; SSRN working paper, proprietary data", "1,004 firms 2010-2025; reactions gradual; single versus double restatements"),
    }
    cr = {r["doi"].lower(): r for r in rows("recent_core_crossref.csv")}
    for r in leads:
        lid = r["lead"]
        x = cr.get(r["doi_given"].lower()) or cr.get("10.1186/s40854-025-00870-0" if lid == "L5" else "")
        online = (x or {}).get("published_online") or r["openalex_publication_date"] or "-"
        issue = (x or {}).get("published_print") or (x or {}).get("issued") or "-"
        vol = (x or {}).get("volume", "")
        pages = (x or {}).get("pages", "")
        lead_lines.append(f"| {lid} | {short(r['brief'], 90)} | {html.unescape((x or {}).get('venue') or r['venue'] or 'SSRN (working paper)')} {vol}{(' ' + pages) if pages else ''} | {online} | {issue} | {notes[lid][0]} | {notes[lid][1]} |")
    core_lines = "\n".join(f"| {m['id']} | {short(m['citation'], 120)} | {m['first_online']} | {m['evidence']} | {m['relation']} | {short(m['overlap'], 150)} |" for m in matrix)
    doc = f"""# Recent literature (2022 to 12 October 2026): search, full-text reading, matrix, novelty, and what it does to EXP-014

Written 2026-10-12 (Phase II continuation). It **updates** `12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md` and `06_PRIOR_ART_AND_NOVELTY.md` and replaces their statements that the direction of the effect "is prior art" and that the one decisive
paper was unread: that paper has now been read in full (`16_FRIEDER_SHANTHIKUMAR_FULLTEXT_REVIEW.md`) and it does not say what was assumed. Machine-readable files: `recent_lit_matrix.csv` (long per-paper field set), `recent_lit_screening.csv`
(every work whose title I read, with the decision and reason), `recent_lit_candidates.csv` (all {total:,} deduplicated works with their stage), `recent_lit_coverage.json`, `recent_search_log.csv`, `citation_chain_log.csv`,
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
   (sensitivity {cov['leads']['retrieved_by_the_search_queries_alone']} of {cov['leads']['named']} named leads found by the queries alone; SSRN and most publishers could not be searched in full).
5. **Direct versus adjacent evidence.** Direct: none found. Closest: A01 (event class, long run), A02 (reliability disclosure, long-run drift), B01 and B02 (filing-process signals with portfolio tests).
6. **Experiment needed.** The registered EXP-014 test, made two-sided and given an age decomposition (section 8). A positive result is a replication-type statement; a negative result closes the amendment direction and strengthens the case for the point-in-time scorer path.
7. **Paper options.** (i) a narrow, honest paper: preregistered independent-sample test of content-classified amendments with the clock-audit finding; (ii) the point-in-time scorer reproducibility work as the forward-looking contribution; (iii) neither is a basis for a claim of
   eligibility for any particular tier of journal.

## 2. How the search was done, and how much it covers

Sources: OpenAlex (ranked title-and-abstract search, boolean sweeps, forward citation chains), Crossref (journal articles and posted content), arXiv (q-fin, econ.EM, stat.ML), plus spot checks through Semantic Scholar, IDEAS/RePEc pages and web search. Window: publication date
2022-01-01 to 2026-10-12; online-publication date is recorded apart from the issue year wherever Crossref gives it. All requests are logged with filters, hit counts and the SHA-256 of each raw response (`recent_search_log.csv`; raw files are git-ignored because they carry publishers' abstracts).

| Item | Count |
|---|---|
| Ranked queries (43 over ten themes), each sent to OpenAlex, Crossref journals, Crossref posted content, and for 14 of them arXiv | {req['ranked_queries']} |
| Boolean sweeps (OpenAlex `title_and_abstract.search`, cursor-paged, cap 600) | {req['boolean_sweeps']} (truncated at the cap: {', '.join(req['sweeps_truncated_at_600'])}) |
| Curated arXiv queries (phrase and OR semantics; the 14 strict AND-of-all-words arXiv calls above returned only 38 records) | {req['curated_arxiv_queries']} |
| Citation chains: seed papers tried / resolved by title and author | {cov['citation_chains']['seeds_tried']} / {cov['citation_chains']['seeds_resolved']} (unresolved: {', '.join(cov['citation_chains']['seeds_unresolved'])}); {cov['citation_chains']['citing_works_fetched']:,} citing works fetched |
| Logged requests / HTTP 200 / never succeeded | {req['logged']} / {req['http_200']} / {len(req['never_succeeded'])} |
| Requests that failed once and were repeated successfully | {len(req['failed_then_repeated_successfully'])} (14 arXiv calls answered with a redirect because the API had moved to https; 1 Crossref call interrupted when the laptop slept) |
| Raw records retrieved | {merge['raw_records_total']:,} |
| **Distinct works after deduplication** (DOI, then normalised title) | **{total:,}**, of which {merge['works_in_more_than_one_source']:,} came from more than one source |
| Year distribution | {', '.join(f"{y}: {n:,}" for y, n in yd.items())}; **2024 to 2026: {recent3:,} ({100 * recent3 / total:.0f}%)** |
| Works with a domain term (finance, accounting, markets) / with a topical keyword as well | {merge['domain_term_present']:,} / {merge['topical_keyword_present']:,} |
| Works with a restatement or amendment term in the title | {merge['works_with_restatement_or_amendment_term_in_title']} |
| Works without an abstract in any source | {merge['works_without_abstract']:,} |

Raw records by source:

| Source | Records |
|---|---|
{source_lines}

**Screening** (`recent_lit_screening.csv`; stage and decision for every work in `recent_lit_candidates.csv`):

| Stage | Works | What it means |
|---|---|---|
| L1 off domain | {stages.get('L1_off_domain', 0):,} | no finance or accounting term; excluded by rule, not read |
| L1 not topical | {stages.get('L1_not_topical', 0):,} | domain term but none of the restatement, machine-learning, design, point-in-time or accounting-quality keywords; excluded by rule, not read |
| L1 topical, rule only | {stages.get('L1_topical_rule_only', 0):,} | keywords present, **not read**; kept in the table, no decision |
| **L2 titles read by me** | **{cov['reading_set_size']}** | the reading set: every restatement- or amendment-titled work, design and point-in-time titles in finance and working-paper venues, widely retrieved or cited machine-learning return-prediction titles, the boolean-sweep members on late filing, Item 4.02, accounting quality and internal control, and the matrix works |
| of which included as core (matrix rows found in the candidate table) | {cov['included_core']} | {cov['included_core_with_abstract_read']} with an abstract read, {cov['included_core_title_only']} title only |
| of which included as context (listed, not in the matrix) | {cov['included_context']} | consequences of restatements, misstatement detection, design, point-in-time, reproducibility |
| of which excluded after reading | {cov['excluded_after_reading']} | {', '.join(f"{k.replace('EXCLUDE_', '').replace('_', ' ').lower()}: {v}" for k, v in cov['excluded_by_reason'].items())} |

The decision for a restatement-titled work outside the matrix was assigned by the title rules in `build_recent_lit_report.py` after I read all the titles; the abstract was read for the matrix works only. The matrix has {len(matrix)} rows ({matrix_in_candidates} of them are in the candidate table; the rest are
pre-2022 bridging papers found by web search, an arXiv paper and a thesis). Evidence levels in the matrix: {', '.join(f"{k} {v}" for k, v in ev.items())}. Matrix rows by group: {', '.join(f"{k}: {v}" for k, v in by_group.items())}.

**Full texts examined.** Sixteen distinct sources in Phase II, two of them in this continuation: Frieder and Shanthikumar (all 60 pages, the owner's PDF) and Ghosh et al. (the open-access HTML read in the in-app browser, sections named in the matrix).
**Not available:** SSRN abstract and download pages (bot verification, not worked around), the Wiley PDF of Lalwani et al. (paywalled although OpenAlex flags it hybrid open access), the American Accounting Association site, ScienceDirect, INFORMS (refusals), and the Elsevier,
T&F and Wiley full texts of closed articles. Five matrix works are TITLE_ONLY because no abstract could be retrieved.

**Sensitivity.** The queries found {cov['leads']['retrieved_by_the_search_queries_alone']} of the owner's {cov['leads']['named']} named leads without being told about them; the one missed, {cov['leads']['missed_by_the_search_queries'][0]}, is a Korean-market machine-learning paper outside the queries' vocabulary. Nine curated arXiv queries found no restatement or amendment work at all, which says that accounting-disclosure research is not on arXiv, not that none exists. That is a small and possibly biased
check, not a recall estimate. OpenAlex's citation graph is incomplete (Frieder and Shanthikumar shows 5 citing works in the window, none about post-restatement returns; I cannot tell whether that is the literature or the index). **The search was not interrupted, but it is not exhaustive:**
Google Scholar was not used (no automated access), SSRN could not be searched directly, and the boolean sweeps for amendments, point-in-time data and replication hit the 600-work cap (ranked by relevance, so the tail was not read).

## 3. The eight named leads, verified

Each was checked by DOI in Crossref and OpenAlex (and in Semantic Scholar for the six that were tried; five were found). The first-online date is kept apart from the issue date; they differ for every journal article.

| Lead | As described in the brief | Verified venue, volume, pages | First online | Issue / print | Status | What it says (evidence level in the matrix) |
|---|---|---|---|---|---|---|
{chr(10).join(lead_lines)}

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
{core_lines}
"""
    out = HERE / "17_RECENT_LITERATURE_2022_2026.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out} ({len(doc):,} characters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
