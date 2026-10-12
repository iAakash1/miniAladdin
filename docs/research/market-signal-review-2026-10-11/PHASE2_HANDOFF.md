# Phase II handoff: read this first

> **STATUS AFTER THE CONTINUATION (2026-10-12 evening) - read this block, then `RESEARCH_STATE.md`; sections 0 to 8 below are the history of the pause and still describe the data, the rules and the gotchas correctly.**
>
> * Done since the pause: Frieder and Shanthikumar read in full (`16_...`); literature updated to 12 October 2026 (`17_RECENT_LITERATURE_2022_2026.md`, `recent_lit_*.csv/json`); three pre-registration protocol amendments (REVERSED label, S11 age bins, S12 liquidity halves);
>   full shuffled-label rehearsal (1,366 s, all stages); **EXP-014 registered at commit `fa1469c` (pushed, gate passed) and run once: FRAGILE**, interpretation MARKER_OF_PERSISTENT_TROUBLE (`docs/EXP_014_RESULTS.md`, `experiments/EXP-014/`); decision documents and `manuscript/draft_014.md` updated.
> * Result in one line: pooled value-changing-amendment coefficient -0.0537 (Holm p 0.0208) at about a fifth of the discovery size; fails the influence gate (0.497 against 0.5) and the within-firm gate (p 0.0566 against 0.05); sits before the amendment and 1-2 years after it, not in the first year; the Item 4.02 announcement carries it (secondary S8/S9, descriptive).
> * Single best next step: a NEW registration (within-firm, event-time study of Item 4.02 announcements with amendments as the later event) on firms neither sample has seen; it needs data acquisition (liquidity ranks beyond 1,000) or the owner's decision to open the sealed holdout once. EXP-014 itself must not be rerun or edited.
> * Section 4 below ("What remains") is DONE through step 5; step 6 (closing checks) is recorded in the final commit and `RESEARCH_STATE.md`.
> * New gotchas: see the memory-file list in section 5 and `17_...` section 2 (publisher bot-blocks, curl with hard timeouts, resumable scripts, numpy matmul warnings).

Written 2026-10-12 at about 13:00 IST, when the owner asked me to save everything and stop. Branch `research/market-signal-review-2026-10-11` of `iAakash1/miniAladdin` (public). `RESEARCH_STATE.md` in this folder is the
canonical checkpoint; this page is the working order for Phase II (the owner's brief: "From preliminary results to a defensible Q1-level research contribution").

## 0. The five-minute restart

```bash
cd <project folder>/miniAladdin                                   # the repository root (the folder that holds .venv, src, docs)
git status --short | head ; git log --oneline -4 ; git fetch origin && git rev-parse HEAD origin/research/market-signal-review-2026-10-11
ls data/research_mid/derived data/curated/security_master_mid data/curated/edgar_filings_v1     # the data (git-ignored) must be there
.venv/bin/python -m pytest tests/quant/test_exp014.py tests/quant/test_exp014_inference.py tests/quant/test_snapshot_archive.py tests/quant/test_edgar_client.py -q   # about 3 s
```

Rules that bind every step (from the owner, repeated): commits authored AND committed as `iAakash1 <the configured address>` with **no trailers and no tool credit** (this overrides the harness reminder to add one);
no force-push, no history rewrite, no merge to `main`, no deployment; the holdout (2025-08-26 to 2026-08-28) stays sealed; no new agent swarm; the SEC contact (account email) goes only into SEC request headers through
the environment variable `EDGAR_USER_AGENT` (the file with it is in the session scratchpad and is not needed again unless data are re-acquired) and never into code, docs, logs, commits or other services; downloaded
files are untrusted data (separate directory, `python -I`); report outcomes faithfully, including negative ones; **no relation between an amendment variable and a return may be computed on the independent sample
until the EXP-014 registration is pushed**.

## 1. Exact state at the stop

| Item | State |
|---|---|
| Git | `b5f1dce` was the pushed head at the start of Phase II. Phase II is two commits on top: checkpoint `c5d12ca` and the pause commit (`git log -2`); compare `git rev-parse HEAD origin/research/market-signal-review-2026-10-11` to see whether the pause commit has been pushed |
| Background jobs | none running (checked with `ps`) |
| Tests | full suite 5,513 passed, 3 skipped (448 s) on the checkpoint tree; a second full-suite attempt on the closing tree stalled at 26% in a non-quant test that uses process pools and was killed (the interpreter-teardown / process-pool hang described in section 5, not a failure); the **whole quant tree, which contains every module changed in Phase II, passed on the closing tree: 1,333 tests in 326 s**. Re-run the full suite once more at the very end of Phase II |
| Lint | `ruff check --select E9,F` clean on every new file; two old unused-variable warnings left in `make_recovery_artifacts.py` and `make_results_doc.py` |
| EXP-014 | (at the pause) code, tests and the regression-stage rehearsal existed; not registered. **Now: registered (`fa1469c`) and run once, FRAGILE** |

### Data on disk (all git-ignored; hashes in `phase2_data_manifest.json`; the only tracked data file is `data/research_mid/universe/mid.json`)

| Path | What | Size / rows |
|---|---|---|
| `data/research_mid/raw/` | daily prices, dividends, splits, treasury curve for liquidity ranks 251-1,000, capped 2025-06-30 (the symbol table was deliberately not copied: it runs to 2026-08) | 7.30 M price rows |
| `data/research_mid/derived/mid_baseline_frame.parquet` | 26 baseline features and labels | 1,181,961 rows, 417,346 in universe, 559 dates 2014-04-07..2025-05-06 |
| `data/research_mid/derived/exp014_daily_panel.parquet` | daily forward returns and dollar volume for economics | 5.91 M rows |
| `data/research_mid/derived/rich_pit_panel_mid.parquet` | the 76-feature panel for the independent sample | 417,346 rows, 1,838 securities, 80.8% trusted identity (the repository's 95% gate fails, as expected for small and delisted names) |
| `data/curated/security_master_mid/` | identity, classification, shares, exits | 2,747 symbols, 2,044 trusted securities |
| `data/curated/edgar_filings_v1/` | EDGAR registry: periodic reports, amendments, 8-K items, late-filing notices, exits | 2,098 companies, 481,027 filings, all page chains complete |
| `data/raw/sec_api/submissions`, `submissions_pages` | raw EDGAR documents | 2,456 + 1,962 files |
| `data/research/derived/amendment_classification_v1.parquet` | content class of all 16,576 FSDS amendments | 55% have a comparable previous version |
| `experiments/EXP-012`, `EXP-013` | earlier registered results (pushed) | unchanged and protected |

## 2. What Phase II established (numbers are in `validation/*.json`)

1. **Verification.** Registered EXP-012/013 numbers recomputed independently to machine precision (`validation/phase2_independent_verification.json`). Protected EXP-006/007 files unchanged.
2. **The discovery association is real by every valid inference, but it rests on few firms.** Value-changing amendment in the trailing 730 days: -0.245 rank units (18 treated firms), any amendment -0.092 (60 firms),
   unchanged-number amendments -0.049; wild-cluster bootstrap p about 1e-4 for the first two (a plain firm-clustered t over-rejects: 22.5% at 5% with three treated firms of fifty in simulation); still
   -0.126 after removing the ten most influential treated firms. The machine-learning rank-IC gain, by contrast, is fragile. Concentration: 63% of the T1 gain comes from the 2.6% of rows that are flagged.
3. **Event time (discovery sample).** Core amendment in the previous 365 days -0.228 (p 0.0004); previous 365-730 days -0.081; next 365 days -0.110 (p 0.088); next 365-730 days +0.123. Anticipation ratio 0.48.
   With a firm fixed effect the core coefficient is -0.154 (p 0.008) against -0.201 pooled: about three quarters of the association is within-firm timing, not a stable trait.
4. **The sign is prior art.** Gondhalekar, Joshi, McKendall (2012, abstract level): average abnormal return negative for each of four years after restatement announcements, about -22% in total; Irani and Xu (2011):
   restatements disclosed only in a 10-K/10-Q show no reaction in 22 trading days; Files et al. (2009), Desai et al. (2006), Bannouh et al. (2019, read in extract) for reporting delay. **Frieder and Shanthikumar (2008,
   "After a restatement: long-run market and investor response", SSRN 1106855) is unread (SSRN blocks automated access, not circumvented) and is probably the decisive paper.** Novelty rating: low.
5. **Data finding.** EDGAR's submissions JSON `acceptanceDateTime` is wrong for 28.2% of 96,429 filings matched to the Financial Statement Data Sets (25.0% shifted by +8/+10 h, 3.3% unconverted), and a further 31
   filings carry filing dates more than a day before acceptance (up to 633 days). FSDS stamps obey the 17:30 filing-date rule 99.2% of the time; six hand checks against EDGAR index pages agree
   (`validation/edgar_acceptance_clock_audit.md`). All study availability uses FSDS stamps, and registry-only events use the later of filing date and stamp date, usable the session after.
6. **Independent sample (label-free counts).** Confirmatory: 150,884 rows, 1,141 firms (companies never in the discovery universe, trusted identity, 2014-04..2025-05); core amendment 2,277 rows / 65 firms, any amendment
   7,456 / 180, Item 4.02 8-K 2,368 / 74, late-filing notice 4,295 / 122, amendments without financials 13,075 / 287. Time-separate (discovery firms 2014-04..2017-03): 35,654 rows, 458 firms; core 161 / 9, any 1,798 / 58.
7. **Size of the registered inference on the real label structure** (placebo amendments on length- and sector-matched untreated firms, position-neutral windows): pooled regression rejects 13.3% at 5% (mean placebo
   coefficient -0.0147: short-lived firms have low ranks), regression with a firm fixed effect 6.3% (mean +0.0019). Hence gate R7 (within-firm) and the rule that SURVIVES needs the pooled H1 **and** R7.
8. **Snapshot archive** (`src/quant/pit/snapshot_archive.py`, 25 tests, 12 of 12 deliberate breakages caught): append-only, hash-chained, content-addressed, with schema, licence, retention, validation status. It
   reconstructs nothing. Replay audit of the live scorer (`live_scorer_replayability.csv`): about 45% of the composite's weight is replayable from prices, 15% only through a different SEC-based definition, 40% (news,
   fundamentals) not at all.
9. **Path A versus B** (`14_PATH_A_VS_PATH_B.md`): Path A is primary conditional on EXP-014; Path B is kept as software and audit work and becomes the forward-looking contribution if EXP-014 does not replicate.
10. **Repository audit** (`15_GITHUB_QUALITY_AND_VERIFICATION.md`): both commits named in the brief confirmed (email constant in `cbce239`, `.claude` path literals in `ecd178c`); all 20 branch commits are
    `iAakash1`, no trailers; no secrets in 177 k added lines; 14 lines of `recovery/transcript_audit.csv` still hold local absolute paths (forward-only fix proposed, history not rewritten).

## 3. Design of EXP-014 (code: `src/quant/study/exp014.py`, `exp014_inference.py`; CLI `scripts/quant/exp014.py`)

H1 (primary): coefficient on a value-changing amendment (revenue, net income, assets, liabilities, equity or operating cash flow changed by more than 1% versus the previous version) available in the trailing 730 days is
negative on `fwd_rank_21`, date x Fama-French-12 fixed effects, 17 controls, firm-clustered **wild-cluster bootstrap** (Webb weights, null imposed, 9,999 draws). H2: any amendment. Holm over H1, H2. Gates R1..R7
(power >= 40 firms and 150 rows; remove the 5 most influential firms keeps >= 50%; >= 9 of 12 leave-one-year-out negative; full 76-feature controls p < 0.05; time-separate sample: any-amendment negative with p < 0.10
and core negative; >= 8 of 12 leave-one-sector-out negative; firm fixed effect p < 0.05). `decide()` gives SURVIVES / FRAGILE / NOT_REPLICATED / INCONCLUSIVE mechanically and an interpretation label from the
event-time ratio. Secondary S1..S10 (windows, 10-K/A versus 10-Q/A, Item 4.02, late notices, amendments without financials, score-augmented regression). Separately: ridge and boosted incremental rank IC (M0/M1, G0/G1,
two placebos), frozen portfolio at 10/30/50 bp, saved M1 artifact reloaded in a fresh process. Nothing is tuned; the holdout is untouched.

## 4. What remains, in order (nothing below has been done)

1. **Full rehearsal** (the only thing that can still break): unsandboxed, background, `caffeinate`:
   `caffeinate -dimsu .venv/bin/python -m scripts.quant.exp014 rehearse --workers 6 --draws 999 --rehearsal-output experiments/EXP-014_rehearsal > /tmp/exp014_rehearsal.log 2>&1`
   (the regression stage alone took about two minutes and returned NOT_REPLICATED on the shuffled label, H1 adjusted p 0.93, as it must). The ridge/boosted arms, the economics call
   (`exp011.arm_seed_report` on the mid daily panel), the artifact round trip and `ml_label` have never run on real rows: expect to fix something. Any edit to a method file changes the fingerprint.
2. If code changed: `python -m scripts.quant.exp014 inputs`, rerun `docs/research/market-signal-review-2026-10-11/code/exp014_pre_registration_checks.py` (about 3 minutes, writes `validation/exp014_pre_registration_checks.json`),
   rerun the new tests (`tests/quant/test_exp014*.py`, `test_snapshot_archive.py`, `test_edgar_client.py`: 59 tests) and ruff.
3. **Register.** `docs/research/.../code/make_prereg_doc_014.py` refuses to write until a full rehearsal is on disk; it writes `docs/EXP_014_PREREGISTRATION.md` with the fingerprint. Read it once (the previous draft's
   calibration paragraph, gate list and counts were corrected on 2026-10-12). Commit the document, `docs/EXP_014_INPUTS.json` and every method file together; push (no force); `python -m scripts.quant.exp014 gate`
   must pass. Verify the remote SHA and raw commit metadata.
4. **Run once:** `caffeinate -dimsu .venv/bin/python -m scripts.quant.exp014 run --workers 6 > /tmp/exp014_run.log 2>&1` (unsandboxed, background). Do not look at partial output and decide anything; do not rerun with changes.
5. `python3 docs/research/.../code/make_results_doc_014.py` writes `docs/EXP_014_RESULTS.md` (it can only say what `PERMITTED` allows). Then update, honestly and only with what was measured: `00_EXECUTIVE_RESEARCH_DECISION.md`,
   `RESEARCH_STATE.md`, `14_PATH_A_VS_PATH_B.md` (apply its trigger table), `manuscript/draft.md` (the generator `make_manuscript.py` is written for EXP-012 and refuses other verdicts: write a new one
   for the independent replication, the clock-audit finding and the archive), data manifests, `06_PRIOR_ART_AND_NOVELTY.md` (point to `12_...`).
6. Tests (full suite), ruff, secret scan, attribution scan, protected-file hash comparison (baselines are in `RESEARCH_STATE.md`), commit, push, verify, final report with the items the brief lists.
7. Cheap extras worth doing if time allows: forward-only fix of the 14 absolute paths in `recovery/transcript_audit.csv`; read Frieder and Shanthikumar if the owner can supply a copy.

## 5. Gotchas met in Phase II (also in memory)

* The sandbox network proxy truncates bodies above roughly 45-80 KB: run bulk SEC/Crossref fetches unsandboxed (resumable caches). SEC and Crossref both ask for no contact in scholarly APIs except the SEC.
* A Python subprocess that has done scikit-learn work intermittently never exits after printing its result; end CLI entry points with `os._exit` (done in `exp014.py` and `scripts/quant/exp014.py`). Stuck children: unsandboxed `ps aux | grep`, then kill.
* Foreground `sleep` is blocked: wait with an `until [ -f ... ]; do sleep 5; done` command in the background.
* Do not edit repo files while pytest runs (tests read them). Process pools need the sandbox off.
* `numpy` matmul `RuntimeWarning`s (divide by zero, overflow, invalid) from Apple Accelerate are spurious here.
* zsh does not word-split unquoted variables: pass file lists explicitly.
* `DatasetBuilder` prints "dataset X unavailable" warnings for the earnings/options datasets that the mid store does not have: harmless, those features are not used.

## 6. Open questions for the owner

1. Approve registration and the single registered run (section 4, steps 3-4).
2. Access to Frieder and Shanthikumar (2008) and the other SSRN-only papers (the review cannot reach SSRN).
3. DoltHub licence review (every price-based result depends on it; nothing derived is redistributed).
4. Real SEC contact for the live service (`SEC_USER_AGENT` is unset in production).
5. Whether the sealed holdout may be opened once, for one frozen design, if (and only if) EXP-014 SURVIVES.
6. Prospective provider-snapshot capture for the live scorer (needs a review of each provider's terms; the archive library is ready, no capture job exists).

## 7. Where things are

`12_FULLTEXT_REVIEW_AND_NOVELTY_MATRIX.md`, `fulltext_ledger.csv` (reading ledger and the 30 closest works) - `13_PIT_ARCHIVE_DESIGN.md`, `live_scorer_replayability.csv` - `14_PATH_A_VS_PATH_B.md` -
`15_GITHUB_QUALITY_AND_VERIFICATION.md` - `phase2_data_manifest.json` - `validation/` (`phase2_*.json`, `edgar_acceptance_clock_audit.md`, `fulltext_papers_verification.json`, `exp014_pre_registration_checks.json`) -
`code/` (every number above is produced by a script there) - `src/quant/pit/{edgar_client,snapshot_archive}.py`, `src/quant/study/exp014*.py`, `scripts/quant/{acquire_edgar_submissions,build_independent_sample,
build_mid_security_master,build_mid_rich_panel,exp014}.py`, `tests/quant/test_{edgar_client,snapshot_archive,exp014,exp014_inference}.py`.

## 8. Checklist for the Phase II final report (the brief's list), with what is already known

| Item | Known now |
|---|---|
| Datasets downloaded | prices, dividends, splits and the treasury curve for liquidity ranks 251-1,000 from the local DoltHub clone (`post-no-preference/stocks` clone commit and rates commit are in `data/manifests/mid_sample_ingest.json`); SEC submissions documents and 1,962 older pages for 2,098 companies (SEC EDGAR, public records, fair-access rules); the listing-snapshot table was not copied (runs to 2026-08) |
| Licence | SEC data: US government public data, fair access (at most 10 requests a second, declared User-Agent); DoltHub community data: licence review is an open owner action, nothing derived from it is redistributed; no data file is tracked except the membership file |
| Coverage | prices 2011-01..2025-06-30; panel 2014-04-07..2025-05-06; 559 decision dates; 2,424 symbols; identity trusted for 80.8% of rows (gate 95% fails); registry history back to 2009 for 1,503 of 2,098 companies; amendment content classifiable for 55% |
| Acquisition commands | `python -m scripts.quant.build_independent_sample universe` / `ingest` / `baseline --workers 6`; `EDGAR_USER_AGENT=... python -m scripts.quant.build_mid_security_master`; `EDGAR_USER_AGENT=... python -m scripts.quant.acquire_edgar_submissions --cohort both`; `python -m scripts.quant.build_mid_rich_panel`; `python docs/research/market-signal-review-2026-10-11/code/classify_amendments.py`; large fetches need the tool sandbox off |
| Models trained | EXP-014 ridge (M0, M1, five permuted placebos and one shifted placebo) and boosted (G0, G1, three seeds each) arms on eight folds; saved M1 ridge at `experiments/EXP-014/model/M1.joblib` (git-ignored, sha256 `ef9866ed2864b3dd...`, 81 features, reloaded in a fresh process to 0.0 difference; NOT FOR PRODUCTION); predictions per arm in `experiments/EXP-014/checkpoints/` (git-ignored); earlier A1/A5 artifacts in `experiments/EXP-012/model/` |
| Metrics | discovery diagnostics (section 2); EXP-014 in `docs/EXP_014_RESULTS.md`: H1 -0.0537 (Holm 0.0208), ML increments +0.0004 Rank IC (NOT_SUPPORTED), net Sharpe 0.3-0.6 at 10 bp for all arms |
| Full-text papers verified | 14 read in extract (pages stated) + Frieder and Shanthikumar (all 60 pages) + Ghosh et al. (open-access HTML, in part); 43 core DOIs checked in Crossref (`recent_core_crossref.csv`); list in `12_...` and `17_...` |
| Limitations | single calendar period shared by both samples; identity selection (80.8% trusted); delisted names lose their last labels; price source licence; SSRN-only papers unread; amendment content known for 55%; registry current-state download |
| Tests | 5,513 passed / 3 skipped (full suite, checkpoint tree); quant tree 1,333 passed on the closing tree; mutation checks on the archive |
| Exact SHA | the registration commit is `fa1469ce840a`; the closing commit is the head of the pushed branch (`git log -1`; stated in the final report) |
| Unverified claims | Gondhalekar et al. beyond the abstract; every ABSTRACT-level paper in `recent_lit_matrix.csv` beyond its abstract; two web-search leads (an Audit Analytics note on positive returns after restatement resolution; a 27% 36-month drift figure); the 45% / 15% / 40% weight split uses the sleeve weights recorded in the signal registry; provider equivalence of adjusted closes; novelty rating (retrieval sensitivity 77%); no venue ranking is stated |
| Q1 manuscript? | Not claimed. The registered outcome is FRAGILE: the supportable paper is a measured, qualified replication plus the data-audit finding (`manuscript/draft_014.md`); no venue ranking is asserted |
| Highest-value next experiment | a new registered within-firm, event-time study of Item 4.02 announcements (amendments as the later event) on firms beyond liquidity rank 1,000, or one frozen look at the sealed holdout if the owner agrees; EXP-014 is not to be rerun |
