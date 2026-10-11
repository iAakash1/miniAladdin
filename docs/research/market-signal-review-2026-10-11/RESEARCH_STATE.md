# Research state checkpoint

Durable checkpoint for the market-signal review. A new session should read this first, then verify the live
values (they may have moved). Nothing here is a result; results live in the numbered documents once they exist.

- **Branch:** `research/market-signal-review-2026-10-11`, cut from `1b3e6c7764ad` (`origin/main`, the production commit at
  the time). The unmerged `origin/continuation/search-intent-quality` branch (3 commits by another identity, touching
  `screen_service.py` and a CI workflow) is unrelated to this work and was neither merged nor altered.
- **Date of this checkpoint:** 2026-10-11. **Identity for every commit:** `iAakash1 <aakashjawle101@gmail.com>`, no trailers.
- **Firewall:** EXP-006/EXP-007 results, artifacts, holdout, cost assumption (10 bp half-spread) and promotion status are
  protected. No new experiment is registered by the literature stages. The baseline fingerprints at the start were
  `final_selection.json a69f54e5a309ec3f`, `configs.jsonl d0251b4cc4e21d03`, `search.json 9ada5cda42234782`; git trees
  `experiments 3f4dea4737ee`, `artifacts 04dc1554d1f6`, `data 09cfd3be09a2`, `src/quant c32663f289a3`.

## Baseline facts verified from the artifacts (2026-10-11)

| Fact in the brief | Verified value | Source |
|---|---|---|
| EXP-007 verdict | `NO PRODUCTION CANDIDATE` (`passed: false`, 1 gate failed of 8) | `artifacts/experiments/EXP-007/final_selection.json` |
| EXP-007 best net Sharpe | `+0.1106` (config `9d1651c56782`, hist_gradient_boosting, arm `C_base`, 27 features, 10 bp half-spread); gross 0.498; mean Rank IC 0.0332; annualised turnover 18.5 | same |
| EXP-007 selection bias diagnostics | PBO 0.929 over 6 finalists; cumulative trials 1,029 (156 prior + 873 new); expected max abs t under the null 3.38 | same |
| Holdout | untouched; window recorded as 2025-08-26..2026-08-26 in EXP-007's artifact and as 2025-08-28..2026-08-28 in `CURRENT_QUANT_RESEARCH_AUDIT.md` (a documentation discrepancy to resolve, not to edit) | same, `docs/CURRENT_QUANT_RESEARCH_AUDIT.md` |
| Frozen panel | `ds-6a5ce92de4de9c48`: 506,374 rows, 977 symbols, 625 dates, 103 features, 9 labels | same |
| Later studies | EXP-010A (noise floor), EXP-010B (21-session cadence), EXP-011 (rich PIT data, `IMPROVES_ONLY_LINEAR`) complete and immutable; EXP-012 not started; no EXP-008 folder exists | `docs/NEXT_RESEARCH_DECISION_2026.md`, `experiments/` |

The seed bibliography was checked against Crossref and arXiv on 2026-10-11: all seven seed DOIs and all four seed arXiv ids
resolve to the titles given in the brief, including the 2026 items (Discover Computing, Computers and Electrical
Engineering, arXiv 2606.27100).

## What exists

| Path | Content | Status |
|---|---|---|
| `code/queries.json` | 143-query bank in 12 families (A-L), seed DOIs/arXiv ids/titles | done |
| `code/lit_search.py` | deterministic, logged, resumable retrieval (OpenAlex, Crossref, arXiv, NBER, Semantic Scholar sample) | done |
| `code/build_candidates.py` | normalise, deduplicate, domain-filter, rank, count (PRISMA identification numbers) | done, rerun after retrieval completes |
| `search_log.csv` | one row per request with the API's own hit count and the SHA-256 of the raw response | appended by the script |
| `shards/` | machine-readable audit shards written by audit agents (signals, experiments, datasets, validation, provenance, internal literature, external datasets) | in progress |

## Retrieval constraints (honest limits of the search)

- **OpenAlex without an API key** has a small shared daily budget (about 100 requests; the response says so and resets at
  00:00 UTC). 67 pages were retrieved before it was exhausted; the remaining queries must be rerun after the reset. A free key
  would lift it but requires creating an account, which this study does not do.
- **SSRN's search is behind bot protection (HTTP 403)** and is not circumvented. SSRN-hosted working papers are reached through
  their registered DOIs (10.2139/ssrn.*) in Crossref/OpenAlex and through domain-restricted web searches.
- **IDEAS/RePEc** native search could not be parsed (the POST endpoint returns a page without result items); covered via NBER's
  own API, OpenAlex/Crossref and domain-restricted web searches.
- **Semantic Scholar** answers 429 to unauthenticated requests; only a small logged sample is attempted.
- Crossref's `total-results` is a fuzzy-match count and is not interpretable as a relevance count; ranks are.
- Publisher platforms (IEEE Xplore, ACM, Springer Nature, Elsevier, Wiley, OUP, CUP) were not queried through their own
  search APIs (keys/subscriptions); their metadata is reached through Crossref and OpenAlex.

## Next steps (in order)

1. Finish arXiv retrieval; rerun `lit_search.py --only OPENALEX` after 00:00 UTC (and again the next day if needed).
2. `python3 code/build_candidates.py` -> `data/candidates_pool.jsonl`, `prisma_counts.json`.
3. Screening workflow: batches of the pool screened title/abstract by structured agents, 10% dual-screened for agreement.
4. Detailed coding of at least 120 included works; full-text reading of at least 30 (open-access only; record what was read).
5. Merge the audit shards into `signals.csv`, `datasets.csv`, `05_OMNISIGNAL_SIGNAL_AUDIT.md`, `04_DATASET_LANDSCAPE.md`.
6. Candidate generation (>= 6), prior-art audit of the leading candidate against 20-30 closest works, scoring, selection.
7. Preregistered protocol, bounded feasibility pilot only if genuine point-in-time data supports it, reviewer panel, journals.

## Resume commands

```bash
cd /Users/aakashjawle/Downloads/omnisignal-final/miniAladdin
git switch research/market-signal-review-2026-10-11
python3 docs/research/market-signal-review-2026-10-11/code/lit_search.py --only OPENALEX   # after 00:00 UTC
python3 docs/research/market-signal-review-2026-10-11/code/build_candidates.py
```
