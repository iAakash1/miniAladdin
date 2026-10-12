# Research state (canonical checkpoint)

Single source of truth for progress. A new session reads this first, then verifies live values (`git log` on the branch, `experiments/EXP-012/manifest.json`). Last updated 2026-10-12 (evening, Phase II continuation). **Start with `PHASE2_HANDOFF.md`; the literature update is `17_RECENT_LITERATURE_2022_2026.md`, the Frieder and Shanthikumar review is `16_...`; EXP-014 was registered at `fa1469c` and run once (see the Phase II continuation table).**

- **Branch:** `research/market-signal-review-2026-10-11`, cut from `1b3e6c7764ad` (`origin/main`). `main` is untouched and nothing is deployed. The unmerged
  `origin/continuation/search-intent-quality` branch (another identity; `screen_service.py` and a CI workflow) is unrelated and was neither merged nor altered.
- **Repository visibility:** `iAakash1/miniAladdin` is **public**. Nothing here redistributes third-party abstracts (the review's `data/` is git-ignored), data of unreviewed licence, secrets or the account email.
- **Identity:** every commit is authored and committed by `iAakash1` with the owner's configured address, checked on the commit objects; no trailers; no attribution of any tool in the repository.
- **Protected:** EXP-006/EXP-007 results, artifacts, folds, 10 bp cost, selection contract, promotion status and the sealed holdout. Baseline file fingerprints (sha256 prefixes):
  `final_selection.json a69f54e5a309ec3f`, `configs.jsonl d0251b4cc4e21d03`, `search.json 9ada5cda42234782`, re-checked file by file (the tracked files under the EXP-006, 007, 010A, 010B and 011
  experiment and artifact trees) before and after the commits.

## Verified baseline facts

EXP-007 verdict `NO PRODUCTION CANDIDATE`; best recorded net Sharpe `+0.1106` (10 bp, 27 features, hist-gradient-boosting); PBO 0.929 over 6 finalists; 1,029 cumulative trials; holdout untouched. Later: EXP-010A/B and
EXP-011 (`IMPROVES_ONLY_LINEAR`) complete; **no EXP-008 folder exists; EXP-012 is the identifier used here.** The owner's 2026-10-11/12 instructions authorise new, separately registered work and keep the holdout sealed.
Production on 2026-10-12: GitHub `main`, Vercel production and Cloud Run revision `omnisignal-api-poc-release-1b3e6c7` (100% of traffic) all show `1b3e6c7`.

## Done

| Item | Where | Status |
|---|---|---|
| Recovery of the stopped runs; token accounting | `recovery_inventory.md`, `recovery/` | done: 27 screening agents reconciled, 9 of 13 failed agents had valid files, 4 batches lost |
| Query bank, logged retrieval | `code/queries.json`, `search_log.csv` | Crossref, arXiv, NBER complete; OpenAlex partial (219 of 384 requests refused by the keyless limit); Semantic Scholar probe partial (2 of 8 answered) |
| Dedup, pool, screening | `prisma_counts.json`, `screening_log.csv`, `screening_summary.json` | 11,217 distinct, 2,311 in the pool, 2,011 rubric-screened, 300 unscreened (classifier-triaged); kappa 0.887 (3-class) on 132 double-screened |
| Protocol and coverage statement | `01_REVIEW_PROTOCOL.md` | done; seed sensitivity 20 of 26 |
| Literature map, annotated bibliography | `02_LITERATURE_MAP.md`, `03_ANNOTATED_BIBLIOGRAPHY.md`, `papers.bib/.csv/.json` | done: 89 works, read level stated for each (no full text read) |
| Dataset landscape and catalogue | `04_DATASET_LANDSCAPE.md`, `datasets.csv` | done: 26 datasets with verification levels |
| Signal audit and registry | `05_OMNISIGNAL_SIGNAL_AUDIT.md`, `signals.csv` | done: 162 rows (research and live scorer) |
| Prior art and novelty | `06_PRIOR_ART_AND_NOVELTY.md`, `verified_prior_art.csv` | done: novelty low to medium; 18 accounting works verified in Crossref |
| Candidates scored | `07_RESEARCH_CANDIDATES.md` | done: A+B narrowed, then C and E on file |
| Primary protocol, reproducibility, journal map, panel simulation | `08`, `09`, `10`, `11` | done (the panel is a self-critique, not an independent review) |
| Data dictionary and quality report | `data_dictionary.md`, `data_quality_report.md` | done |
| Reliability variables | `src/quant/pit/reliability.py`, `tests/quant/test_reliability.py`, `validation/` | built, 0 mismatches in 16,000 independent comparisons |
| EXP-012 pipeline, tests, rehearsal | `src/quant/study/exp012.py`, `scripts/quant/exp012.py`, `tests/quant/test_exp012.py` | 1,264 quant tests pass; label-shuffled rehearsal of all 30 fits returned NOT_SUPPORTED everywhere |
| EXP-012 preregistration | `docs/EXP_012_PREREGISTRATION.md` (written by `code/make_prereg_doc.py`) | registered: commit `639eb65`, pushed before the run; fingerprint `f9d76d2f3d68...` |
| EXP-012 registered run | `experiments/EXP-012/`, `docs/EXP_012_RESULTS.md` | **complete** 2026-10-12 02:48 IST at commit `88ec777`, clean tree, 1,016 s. T1 SUPPORTED (+0.00515 Rank IC, Holm p 0.011, 6 of 8 folds, negative in the last two); T2 and T3 NOT_SUPPORTED. A0/A1 reproduced EXP-011 to 4e-17; holdout sealed |
| EXP-013 attribution (registered, run) | `docs/EXP_013_PREREGISTRATION.md`, `experiments/EXP-013/`, `docs/EXP_013_RESULTS.md` | **complete** 2026-10-12 03:09 IST at commit `a39400f`, clean tree, 86 s. B1/B5 reproduce A1/A5 (5e-17). Labels: four filing-process ranks CARRIES (add +0.0031, 60% of the gain; amendment count alone +0.0024, t 2.50), missing-fundamentals count SHARES, composite NOT_CARRYING. Few firms (60), Holm p 0.058 |
| Pre-declared naive reference N0 | `experiments/EXP-012/reference_naive.json` | Rank IC 0.0158 (t 0.88), net Sharpe +0.39 at 10 bp |
| Saved models, fresh-process reload | `experiments/EXP-012/model/` (git-ignored) | A1 and A5 reload through the CLI and score 248 names with finite scores |
| Executive decision, panel simulation, manuscript draft, data manifests | `00`, `11`, `manuscript/draft.md`, `data_manifest.json`, `provenance_manifest.json`, `dataset_catalogue.csv` | done |

## Phase II (2026-10-12): verified, newly generated, planned, blocked

| Deliverable | Label | Where | Notes |
|---|---|---|---|
| Independent recomputation of the registered EXP-012/013 numbers | newly generated | `validation/phase2_independent_verification.json`, `code/phase2_verify_independent.py` | agrees to machine precision |
| Discovery-sample diagnostics: clustered inference, influence calibration, regression discovery, wild-cluster bootstrap, event-time bins | newly generated | `validation/phase2_*.json` | exploratory; the sample that produced the finding |
| Amendment content classification (16,576 FSDS amendments) | newly generated | `code/classify_amendments.py`, `validation/amendment_classification_summary.json` | 55% have a comparable previous version |
| Independent firm sample (liquidity ranks 251-1,000): universe, prices, baseline frame, identity layer, rich panel | newly acquired / derived | `data/research_mid/`, `data/curated/security_master_mid/`, `phase2_data_manifest.json`, `data/manifests/mid_*.json` | git-ignored except the membership file; licence of the price source unreviewed |
| EDGAR submissions registry for 2,098 companies, with request log | newly acquired | `data/curated/edgar_filings_v1/`, `data/manifests/edgar_*` | current-state download; acceptance stamps audited |
| Acceptance-clock audit of the registry | newly generated (finding) | `validation/edgar_acceptance_clock_audit.md` | 28.2% of matched stamps wrong; FSDS stamps right |
| SEC client that keeps the contact out of code, logs and manifests | newly generated | `src/quant/pit/edgar_client.py`, `tests/quant/test_edgar_client.py` | 8 tests |
| Point-in-time snapshot archive and live-scorer replay audit | newly generated | `src/quant/pit/snapshot_archive.py`, `13_PIT_ARCHIVE_DESIGN.md`, `live_scorer_replayability.csv` | 25 tests, 12 of 12 breakages caught; **no capture job exists, nothing is collected** |
| Full-text review ledger, closest-30 matrix, identifier verification | newly generated | `12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md`, `fulltext_ledger.csv`, `validation/fulltext_papers_verification.json` | 14 papers read in extract (pages stated); SSRN-only works unread |
| Path A versus Path B | newly generated | `14_PATH_A_VS_PATH_B.md` | conditional on EXP-014 |
| Repository history audit | newly generated | `15_GITHUB_QUALITY_AND_VERIFICATION.md` | email constant and path literals confirmed; no rewrite |
| EXP-014 protocol, code, tests, regression-stage rehearsal | newly generated | `src/quant/study/exp014*.py`, `scripts/quant/exp014.py`, `tests/quant/test_exp014*.py`, `code/exp014_pre_registration_checks.py`, `validation/exp014_pre_registration_checks.json` | superseded by the continuation rows below |
| ALFRED vintages for the live scorer's macro gate | blocked | | no key (owner) |
| Provider-snapshot capture for the live scorer | planned | | needs provider-terms review; library ready |
| Other SSRN-only full texts (Zhu 2026, Ahn 2026, Bangert and Myers 2023, Mammadova 2026 and others) | blocked | | SSRN bot verification, not circumvented; abstracts only |

## Phase II continuation (2026-10-12 evening): literature update, F&S reading, EXP-014 registered and run

| Deliverable | Label | Where | Notes |
|---|---|---|---|
| Full-text review of Frieder and Shanthikumar (2008), owner-supplied PDF | newly generated | `16_FRIEDER_SHANTHIKUMAR_FULLTEXT_REVIEW.md`, `fulltext_ledger.csv` (F15) | all 60 pages; **a positive rebound in trading days 64-126 (+4.3% raw), no significant negative drift: the earlier premise "the sign is prior art" is withdrawn** |
| 2022-2026 literature search, screening, evidence matrix, coverage statement | newly generated | `17_RECENT_LITERATURE_2022_2026.md`, `recent_lit_matrix.csv` (43 rows), `recent_lit_screening.csv`, `recent_lit_candidates.csv`, `recent_lit_coverage.json`, `recent_search_log.csv`, `citation_chain_log.csv` | 10,618 distinct works (OpenAlex, Crossref, arXiv), 495 titles read, 7 of the 8 named leads recalled by the queries alone; no modern study of content-classified amendments as a return predictor found; SSRN and most publishers unreachable |
| Verification of the eight named leads and 43 core DOIs | newly generated | `lead_verification.csv`, `recent_core_crossref.csv` | online dates kept apart from issue dates; one retracted record excluded |
| Open-access full text of Ghosh et al. (JBFA 2025/2026) | newly generated | local only (`research_papers/phase2_fulltext/text/`), ledger F16 | read in part |
| EXP-014 protocol amendments (REVERSED label, S11 age bins, S12 liquidity halves) | newly generated, before registration | `src/quant/study/exp014.py`, `tests/quant/test_exp014.py` (19 tests) | made after the F&S reading, before any amendment variable was related to a return on the independent sample |
| EXP-014 full shuffled-label rehearsal (all stages) | newly generated | `experiments/EXP-014_rehearsal/` (git-ignored) | 1,366 s; NOT_REPLICATED / NOT_SUPPORTED everywhere, artifact reloaded in a fresh process to 0.0 difference |
| EXP-014 registration | registered | `docs/EXP_014_PREREGISTRATION.md`, `validation/exp014_protocol_pre_run.json`, commit `fa1469c` (pushed, gate passed) | fingerprint `eefc4cc03454c3dc...`; power statement and S11/S12 reading rule included |
| **EXP-014 registered run** | **complete** 2026-10-12 21:20-21:43 IST at commit `fa1469c`, clean tree, 1,370 s | `experiments/EXP-014/` (results, manifest, regressions, ML and economics tables), `docs/EXP_014_RESULTS.md` | **FRAGILE**, interpretation MARKER_OF_PERSISTENT_TROUBLE. H1 -0.0537 (Holm p 0.0208), H2 null; R2 failed (0.497 of the estimate kept, needs 0.5) and R7 failed (within-firm p 0.0566, needs 0.05); ML increments NOT_SUPPORTED; holdout sealed. Saved model `experiments/EXP-014/model/M1.joblib` (git-ignored), sha256 `ef9866ed2864b3dd...`, reloaded in a fresh process to 0.0 difference |
| Updated executive decision, Path A/B decision, manuscript draft | newly generated | `00_EXECUTIVE_RESEARCH_DECISION.md`, `14_PATH_A_VS_PATH_B.md` (section 4), `manuscript/draft_014.md` | Path A as a measured, qualified result; no anomaly or value claim |

## Not done, and why

- Full text of the SSRN-only works (Zhu 2026, Ahn 2026, Bangert and Myers, Mammadova, Schroeder and Posch, Wang): SSRN refuses automated access and the bot verification was not completed or worked around. Frieder and Shanthikumar was supplied by the owner and read in full.
- Wiley, AAA, ScienceDirect and INFORMS full texts of closed articles; Google Scholar (no automated access); a recall estimate for the 2022-2026 search beyond the 7 of 8 named leads.
- Quartiles of target journals (SCImago 403, Journal Citation Reports subscription-only): none is stated anywhere.
- A complete OpenAlex pass (keyless daily limit).
- Any test of vendor disagreement or provider health: no history exists; the archive library is built but nothing is captured.
- Any test on the sealed holdout (the owner's decision).

## Token accounting (measured from transcripts; not billing)

27 screening agents 4.46M (new input + output + cache creation); baseline-audit workflow 5.13M over two runs with no output; dataset-landscape workflow 0.74M with no output. Details and caveats:
`recovery_inventory.md`. **No further model screening and no new agent swarm.**

## Disclosures

- The account email was placed in the User-Agent and `mailto` fields of the first scholarly-API calls on 2026-10-11 (OpenAlex, Crossref, arXiv, NBER). It was removed from the code and sent in no later request; requests already made carried it,
  and the first commit of this review still contains the constant. History was not rewritten.
- Title and abstract screening was automated and rubric-driven; no person screened records. The repository credits no tool as author. A journal manuscript will need a truthful declaration of how the work was prepared; that is
  separate from repository attribution and is for the owner to settle (`10_JOURNAL_POSITIONING.md`).
- One reference quantity (the naive 12-1 momentum rank's IC) was computed once while testing its script, before registration, on the rehearsal's rows (0.0204); the pre-declared value on the registered rows is 0.0158.
  The row sets differ because shuffling a label moves missing labels. The registration discloses the first number.
- The registered sensitivity paragraph understated the realised noise (T1 standard error 1.9 times larger than in the shuffled-label rehearsal; T3 8 times); disclosed in `docs/EXP_012_RESULTS.md`, section 7. The registered verdicts stand.
- Pushing the branch made Vercel's Git integration build two preview deployments (statuses on the pushed commit); production is unchanged (`/api/build` commit `1b3e6c7`).
- **Phase II.** The SEC contact (the account email) was sent to the SEC only, through the environment variable `EDGAR_USER_AGENT`, at the owner's explicit choice; it is in no code, document, log, manifest, commit or other service
  (tested for the client's logs and exceptions). Large downloads were run outside the tool sandbox because its network proxy truncates bodies above roughly 45 KB.
- **Phase II, before registration, on the independent sample:** only label-free counts, coverage checks, a placebo-amendment size calibration, and label-only descriptives (return rank by tenure and by time to a firm's last row) were
  computed; no relation between an amendment variable and a return. The amendment categories, the 730-day window, the controls and the gates were fixed after reading the discovery-sample diagnostics and are therefore not independent of them.
- **Phase II calibration history, disclosed:** the first placebo designs gave negative mean placebo coefficients because their windows were position-biased or the partners were not matched on length; they were replaced by position-neutral windows
  and length- and sector-matched partners before anything was registered. The pooled regression still over-rejects under that placebo (13.3% at 5%), the within-firm regression does not (6.3%); the registration therefore
  requires both.
- The rehearsal of the regression stage on a shuffled label returned NOT_REPLICATED (H1 adjusted p 0.93, H2 0.77), as it must.

- **Phase II continuation (2026-10-12 evening).** Three protocol amendments (the REVERSED label, secondary S11, secondary S12) were made after reading Frieder and Shanthikumar and the 2022-2026 literature and before any amendment variable was related to a return on the independent sample; the registration says so. The full shuffled-label rehearsal returned NOT_REPLICATED / NOT_SUPPORTED everywhere. Label-free treated counts for S11/S12 were read from the rehearsal frame.
  The registered run was started once and not restarted. Numpy prints spurious matmul warnings on this machine (reproduced on random data); results are finite and two inference code paths agree.
- **Literature search limits (continuation).** SSRN, Wiley PDFs, AAA, ScienceDirect and INFORMS refused automated retrieval and were not worked around; abstract-level evidence is labelled as such; one retracted record was found and excluded; the search is not exhaustive (7 of 8 named leads recalled by the queries alone). The account email was sent to no service in this session (SEC calls were not made).
- **The results document and manuscript draft** are generated from the output files; the interpretation sentences beyond the registered label are descriptive and say so.

## Next executable steps

Phase II has run its registered test. The single best next step is a **new registration** (not an edit of EXP-014): a within-firm, event-time study of the Item 4.02 non-reliance announcement with value-changing amendments as the later event, on firms neither sample has seen (liquidity ranks beyond 1,000 for 2014-2025, which needs
price ingestion, an identity layer and a panel build, or the sealed holdout once for one frozen design, which needs the owner). Until then: the closing checks of this session (full test suite, protected-file hashes, secret and attribution scans, push) are in the commit that adds the results; the draft `manuscript/draft_014.md` and the
decision documents are for the owner's review.
Owner decisions that remain: open the sealed holdout once for one frozen design (or not); extend the independent sample beyond liquidity rank 1,000 (data acquisition and the price source's licence); SEC contact for the live service; DoltHub licence review; access to the SSRN-only papers; provider-terms review before any snapshot capture; wording of any journal AI declaration; the Vercel previews that the pushes create.
