# Review protocol and coverage statement

This is the protocol that was actually followed, written after the fact from the logs; where the plan and the execution differ, the execution is
what is described, and the differences are listed in the last section. Every number below can be recomputed from the files named beside it.

## Question and scope

*What determines whether public information about a company improves a cross-sectional ranking of US equity returns, and which of those
determinants can be measured point in time without a vendor?* Eligible works study equity (and closely related asset) return or risk prediction,
signal evaluation, the data behind signals, or the credibility of the evidence. Twelve topic families (A-L, defined in `code/screening_rubric.md`)
cover return predictability, technical signals, machine learning, time-series foundation models, financial language models, multimodal data,
data fusion and reliability, regimes and decay, costs and portfolios, research credibility, cross-field reliability methods, and datasets.
English-language works from 1985 to 2026-10-12.

## Sources, dates, and what each search could and could not reach

| Source | Access | Requests logged | Outcome |
|---|---|---|---|
| Crossref | public REST API | 143 | complete: all 143 queries, journal and preprint records |
| arXiv | public API (q-fin, econ.EM, stat.ML, cs.LG and related) | 172 | complete, after widening queries that returned too few records |
| NBER | public working-paper listing API | 143 | complete |
| OpenAlex | public API, no key | 384 (165 returned data, 219 refused for exceeding the daily limit) | **partial**: the keyless daily budget ran out; queries not served are listed in `search_log.csv` (`http_status` 429) and can be re-run after the limit resets |
| Targeted prior-art search | Crossref, arXiv, NBER | 12 queries on 2026-10-12 | `targeted_search_log.csv` |
| Semantic Scholar (keyless public API) | spot check of the novelty claim | 8 queries on 2026-10-12 | **partial**: the API throttled the keyless caller after two queries (S01 and S02 answered, S03 to S08 refused with HTTP 429, one retry sequence stopped on purpose); `semantic_scholar_log.csv` |
| Metadata verification of accounting works | Crossref | 18 lookups on 2026-10-12 | `verified_prior_art.csv`, all 18 matched on title and first author |

All broad retrievals ran on 2026-10-11, the targeted ones on 2026-10-12. Raw responses are kept with a SHA-256 in `search_log.csv`; the raw files
and the 11,217-record candidate set are git-ignored because they hold third-party abstracts (`data/`), the identifiers and decisions are not.

**Not searched.** SSRN (automated access is refused with a bot-protection response; it was not circumvented), Google Scholar, Scopus, Web of Science,
JSTOR, EBSCO, RePEc/IDEAS, and publisher sites. Journals in accounting (The Accounting Review, Journal of Accounting and Economics, Review of Accounting
Studies, Contemporary Accounting Research) are reached only through Crossref. Conference proceedings without a DOI are largely missed. Consequently the
review is strong on arXiv, NBER and DOI-bearing journal articles and weak on unpublished working papers elsewhere, on non-English work, and on anything
indexed only by the services above. This is a **limited-coverage systematic review**, not an exhaustive one, and is described as such throughout.

## Query bank

143 queries in twelve families (A 14, B 11, C 14, D 8, E 14, F 10, G 18, H 9, I 11, J 16, K 10, L 8), text in `code/queries.json`. The bank was fixed before any
result was read. Twelve further queries were added on 2026-10-12 after the research question narrowed (`code/targeted_search.py`), and are reported separately.

## Selection of records for screening (PRISMA-style counts, `prisma_counts.json`)

| Stage | Records |
|---|---|
| Retrieved (OpenAlex 3,350; Crossref 4,290; arXiv 3,538; NBER 2,860) | 14,038 |
| Duplicates removed (DOI, arXiv id, or normalised title and year) | 2,821 |
| Distinct works | 11,217 |
| Excluded before screening: off-domain 2,296; below the pool threshold 6,539; type or date 71 | 8,906 |
| **Screening pool** | **2,311** |
| Screened at title and abstract by the rubric | 2,011 |
| Not screened by an agent (three lost batches; see below) | 300 |
| Included 1,028; maybe 210; excluded 773 | 2,011 |

The pool rule is deliberate and is a source of bias: a work enters if at least three queries return it, or it ranks in the top five of any query, or it has at
least 300 citations, or it is a seed, or it is a 2023-2026 record in the top ten of a query. Highly cited and well-matched works are favoured; obscure works
that match one query weakly are not read. The rule and the counts it removed are in `prisma_counts.json`.

## Screening procedure

Screening is at title, abstract and metadata only, by automated agents applying the written rubric in `code/screening_rubric.md` in batches of 100 records
ordered by a hash of the record id, so that no batch is a single topic. The agents were told not to consult the web or fill a missing abstract from memory;
records without an abstract (flagged `has_abstract` false) are decided on title and venue with `confidence` low. Each decision records the exclusion code,
the topic families, an evidence type, a publication status read from the venue metadata, a relevance score 0-3, the candidate directions it bears on, and a one-line note.

**Agreement.** A hash-selected sample of about 10% of the pool was set aside for a second, independent screen, in batches of 100 that did not show the first decision. One of its batches was lost with the usage limit, so 132 of the 2,011 screened records (6.6%, short of the 10% planned) have two decisions.
Raw agreement on include / maybe / exclude was 93.2% (Cohen's kappa 0.887) and on in-versus-out 96.2% (kappa 0.922).

**Lost work and how it was recovered.** Thirteen of the 27 screening agents ended on a usage-limit error. Nine had already written valid output, which was
recovered; three main batches (016, 020, 022: 300 records) and the one dual-screen batch (001) produced nothing. `recovery_inventory.md` reconciles every agent.
The 300 unscreened records were scored with a classifier (TF-IDF features and logistic regression) trained on the 2,011 decisions: cross-validated AUC 0.917;
at the chosen threshold, recall of relevant records 0.970 while removing 19.9% of records; applied to the 300 it set aside 69 and carried 231 forward.
These records are marked `not_screened` in the ledger and **are not counted among the 1,028 included or in any family count**. The classifier is a triage
aid for a later manual pass, not a screening decision.

## Coding and reading depth

For the 1,238 included and maybe records the ledger holds the coded fields listed above (family, evidence type, status, relevance). That satisfies the
"at least 120 coded" requirement at abstract level. **The requirement to read at least 30 works in depth is not met in the full-text sense.** What was done:
67 works (`03_ANNOTATED_BIBLIOGRAPHY.md`) were selected as closest to the study, abstracts were read for the novelty comparison in
`06_PRIOR_ART_AND_NOVELTY.md`, and the metadata of 18 accounting works was verified (`verified_prior_art.csv`). No full text was read: most of the closest
works are in subscription journals or behind SSRN's refusal of automated access, and a later instruction limited full-text reading to papers that would change
the decision. None of the abstract-level comparisons changes it, but the novelty audit says exactly how far its confidence extends.

## Retrieval sensitivity check (seed records)

The brief and the repository supplied 26 known works as seed identifiers (7 DOIs, 4 arXiv ids, 15 titles; `code/queries.json`). A seed is flagged when a
retrieved record matches it, and seeds that were not retrieved are **not** added from memory. Retrieval found 20 of the 26: 6 of 7 DOIs, 4 of 4 arXiv ids,
10 of 15 titles. The six misses are one DOI (10.1016/j.compeleceng.2026.111110, which resolves in Crossref to a 2026 systematic review of AI methods for
financial market prediction) and five titles ("Dissecting Characteristics Nonparametrically"; three general-purpose time-series foundation-model papers, titled
"Chronos", "A decoder-only foundation model for time-series forecasting" and "Unified Training of Universal Time Series Forecasting Transformers"; and "FinBERT"). So the search has a measured sensitivity of about 77% against known anchors, and the five misses are mostly
general-purpose model papers outside the finance vocabulary of the queries. A claim that "the search did not return" a study is therefore weaker than
"no such study exists", and `06_PRIOR_ART_AND_NOVELTY.md` words its conclusions accordingly.

## Deviations from the plan

1. OpenAlex was cut short by its keyless limit (partial coverage, above). A free key would remove the limit; creating the account is the owner's decision.
2. The independent second screen covers 6.6% of records, not 10%, because its first batch was lost.
3. Three of twenty-four main batches were lost; 300 records are unscreened (above).
4. The plan to run a signal audit and a dataset survey as agent workflows failed on the same limit and produced nothing; both were done with scripts
   (`code/export_signal_registry.py`, direct tests in `04_DATASET_LANDSCAPE.md`).
5. Full-text depth (above).
6. An email address was placed in the User-Agent and `mailto` fields of the first scholarly API calls, which breaches the rule that the account address is never
   sent to unrelated services. It has been removed from the code. Calls already made carried it, and the first commit still contains the constant; history
   was not rewritten.
