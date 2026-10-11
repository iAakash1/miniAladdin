# Research state (canonical checkpoint)

Single source of truth for progress. A new session reads this first, then verifies live values. Last updated 2026-10-12.

- **Branch:** `research/market-signal-review-2026-10-11`, cut from `1b3e6c7764ad` (`origin/main`). `main` is untouched. The
  unmerged `origin/continuation/search-intent-quality` branch (3 commits by another identity, `screen_service.py` and a CI
  workflow) is unrelated and was neither merged nor altered.
- **Identity:** every commit is authored and committed by `iAakash1 <aakashjawle101@gmail.com>`, checked on the commit objects;
  no trailers. No AI attribution anywhere in the repository (scanned before each commit; exit codes read, not inferred).
- **Protected:** EXP-006/EXP-007 results, artifacts, folds, 10 bp cost, selection contract, promotion status and the sealed
  holdout. Baseline file fingerprints (sha256 prefixes): `final_selection.json a69f54e5a309ec3f`, `configs.jsonl
  d0251b4cc4e21d03`, `search.json 9ada5cda42234782`. Adding new files under `experiments/` or `src/quant/study/` changes
  directory tree hashes by design; protection is verified per file.

## Verified baseline facts

EXP-007 verdict `NO PRODUCTION CANDIDATE`; best recorded net Sharpe `+0.1106` (config `9d1651c56782`, hist-gradient-boosting,
`C_base`, 27 features, 10 bp half-spread; gross 0.498, mean Rank IC 0.0332, turnover 18.5x); PBO 0.929 over 6 finalists;
1,029 cumulative trials; holdout untouched. Holdout window is `2025-08-26..2026-08-26` in the EXP-007 artifact and
`2025-08-28..2026-08-28` in `CURRENT_QUANT_RESEARCH_AUDIT.md` (documentation discrepancy, not edited). Later: EXP-010A/B and
EXP-011 (`IMPROVES_ONLY_LINEAR`) complete; **no EXP-008 folder exists; the next unused identifier is EXP-012.**
`NEXT_RESEARCH_DECISION_2026.md` asked the owner to choose Direction A (data completion) or B (freeze); the owner's 2026-10-11/12
instructions authorise new, separately registered work and keep the holdout sealed (Direction A character).
All seed identifiers (7 DOIs, 4 arXiv ids) were resolved against Crossref/arXiv.

## Done

| Item | Where | Status |
|---|---|---|
| Query bank (143 queries, 12 families), logged retrieval | `code/queries.json`, `code/lit_search.py`, `search_log.csv` | Crossref, arXiv, NBER complete; OpenAlex partial (keyless daily budget exhausted after 67 pages; rerun after 00:00 UTC) |
| Dedup + pool (11,217 distinct works -> 2,311 screening pool) | `prisma_counts.json`, `code/build_candidates.py` | done |
| Title/abstract screening | `screening_log.csv`, `screening_summary.json` | 2,011 of 2,311 rubric-screened; 300 classifier-triaged; agreement kappa 0.887 (3-class) |
| Recovery of the stopped runs | `recovery_inventory.md`, `recovery/` | done: 9 of 13 failed agents had written valid files; 4 batches lost |
| Signal registry from code | `signals_core.csv`, `code/export_signal_registry.py` | 114 rows; reconciles to EXP-007's 103 frozen columns |

## Token accounting (measured from transcripts; not billing)

27 screening agents 4.46M (new input + output + cache creation); baseline-audit workflow 5.13M over two runs with no output;
dataset-landscape workflow 0.74M with no output. Details and caveats: `recovery_inventory.md`. **No further model screening and no
new agent swarm.** Any further agent needs a stated question, why existing artifacts cannot answer it, and a named deliverable.

## Known limits of the search

OpenAlex keyless budget (about 100 requests a day); SSRN search behind bot protection (HTTP 403, not circumvented);
IDEAS/RePEc native search not parseable; Semantic Scholar 429; Crossref total hits are fuzzy. Publisher platforms were reached
through Crossref/OpenAlex metadata only. Titles and identifiers are retained in the ledger; abstracts are not redistributed.

## Method statement (not attribution)

Title/abstract screening was automated and rubric-driven (`code/screening_rubric.md`), with a second independent automated screen
on a hash-sampled 10% and a measured agreement; no human screened records. The repository credits no tool as author. Journals
generally require disclosure of such tools in a manuscript and forbid listing one as an author; that declaration is separate
from repository attribution and must be settled with the target journal before submission (`10_JOURNAL_POSITIONING.md`).

## Next executable step

1. From `screening_log.csv`, list the nearest prior art for the reliability hypothesis (families G, K, F, H, A with
   `candidate_overlap` A/B/H, relevance 3) and read their abstracts; decide whether the gap survives.
2. If it survives: build the SEC-submissions reliability table for the EXP-011 universe (public, free, User-Agent with contact)
   and register EXP-012 (validation folds only, holdout sealed) as an exploratory, predeclared comparison.
3. If it does not: pivot to the strongest remaining gap and record why.
