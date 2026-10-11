# Research state (canonical checkpoint)

Single source of truth for progress. A new session reads this first, then verifies live values (`git log` on the branch, `experiments/EXP-012/manifest.json`). Last updated 2026-10-12.

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
| EXP-012 preregistration | `docs/EXP_012_PREREGISTRATION.md` (written by `code/make_prereg_doc.py`) | written; registered when committed and pushed |

## Not done, and why

- Full-text reading of the closest works (no access; SSRN refuses automated access).
- Quartiles of target journals (SCImago returned 403; Journal Citation Reports is subscription-only).
- A complete OpenAlex pass (keyless daily limit; a free key needs an account, which is the owner's decision).
- Any test of vendor disagreement or provider health: no history exists.
- The registered EXP-012 run, its naive reference and the executive decision, until the registration is pushed: see the next steps.

## Token accounting (measured from transcripts; not billing)

27 screening agents 4.46M (new input + output + cache creation); baseline-audit workflow 5.13M over two runs with no output; dataset-landscape workflow 0.74M with no output. Details and caveats:
`recovery_inventory.md`. **No further model screening and no new agent swarm.**

## Disclosures

- The account email was placed in the User-Agent and `mailto` fields of the first scholarly-API calls on 2026-10-11 (OpenAlex, Crossref, arXiv, NBER). It was removed from the code and sent in no later request; requests already made carried it,
  and the first commit of this review still contains the constant. History was not rewritten.
- Title and abstract screening was automated and rubric-driven; no person screened records. The repository credits no tool as author. A journal manuscript will need a truthful declaration of how the work was prepared; that is
  separate from repository attribution and is for the owner to settle (`10_JOURNAL_POSITIONING.md`).
- One reference quantity (the naive 12-1 momentum rank's IC) was computed once while testing its script, before registration; it is disclosed in the preregistration.

## Next executable steps

1. Commit and push the branch (no force); verify the remote SHA and the three identities; `python -m scripts.quant.exp012 gate` must pass.
2. Run the registered study once: `caffeinate -dimsu .venv/bin/python -m scripts.quant.exp012 run --workers 6` (outside the sandbox); read the acceptance block in `experiments/EXP-012/manifest.json` first.
3. Run `code/naive_reference.py`; reload `model/A1.joblib` and `model/A5.joblib` in a fresh process; write `00_EXECUTIVE_RESEARCH_DECISION.md`, the results section of the panel simulation and the manuscript draft from the actual files.
4. Run the whole test suite, scan the diff for attribution wording, secrets and large files, commit, push, verify the remote and the repository's secret-scan workflow.
