# Recovery inventory (2026-10-12)

Everything below is read from the transcripts and files on disk (`code/audit_transcripts.py`,
`code/make_recovery_artifacts.py`); nothing is estimated from memory. Machine-readable: `recovery/task_inventory.csv`,
`recovery/transcript_audit.csv`, `recovery/recovered_screening.{csv,json}`, `recovery/web_evidence_index.csv`.

## 1. What was run

| Group | Tasks | Displayed in the task panel | Measured from transcripts (new input + output + cache creation) | Deliverables persisted |
|---|---|---|---|---|
| Direct screening agents (27) | 14 completed, 13 failed | about 4.29M (screenshot) | **4,455,489** (cache reads, 16.1M, are separate) | **23 of 27** shard files valid on disk |
| Baseline-audit workflow, run 1 (9 agents + verifiers) | all 9 failed at the usage limit | 2,051,826 | part of 5,130,070 for both runs | **0** |
| Baseline-audit workflow, resumed run 2 (same 9 agents again) | all 9 failed | 3,397,121 | (see above) | **0** |
| Dataset-landscape workflow, run 1 | 6 agents failed in 1.2 s | 0 | 0 | 0 |
| Dataset-landscape workflow, run 2 | 6 agents failed (usage limit) | 810,079 | 741,740 | **0 files; 69 web results recovered** (below) |
| Screening workflow (65 agents) | failed in 5.6 s | 0 | 0 | 0 (superseded by the direct agents) |
| Retrieval scripts (OpenAlex, Crossref, arXiv, NBER) | shell, no model | none | none | `search_log.csv` (744+ logged requests) |

**Parent/child overlap.** A workflow's counter is the sum of its own child agents (`subagent_tokens`), and the direct
screening agents are separate tasks, so the three groups do not overlap. Workflow run 2 re-ran all nine agents of run 1 from
scratch (none had completed, so nothing was cached): the two baseline-audit counters are two spends on the same questions.
**What the interface displays** matches no single transcript counter exactly. Counting each streamed message once, the sum
of input + output + cache-creation tokens over the 27 screening agents is 4.46M against about 4.29M displayed (4% apart); the
cache-read tokens (each turn re-reading the cached context, 16.1M) are evidently not displayed. Exact displayed totals therefore
cannot be reproduced, and no figure here should be read as billing.

## 2. "11 failed" versus 13 failed

The task panel and the session notices list a task as *failed* when the API call that ended it returned a usage-limit error
(HTTP 429), whatever the agent had already done. They arrived one at a time while the limit was hit, which is why a count of 11
appeared before the final 13 (11 main batches: 013 to 023, and 2 dual batches: 001, 002). The classification says nothing about
whether a file was written, and **9 of the 13 had written their shard file before they were stopped.**

| Failed task | File on disk | Recovery |
|---|---|---|
| main 013, 014, 015, 017, 018, 019, 021, 023 and dual 002 (9) | valid, complete, record ids match the batch | recovered from the file (provenance `recovered_from_file_after_agent_stopped`) |
| main 016, 020, 022 and dual 001 (4) | none; the transcript ends with the limit message, no `Write` call, reasoning not persisted | **not recoverable**; 300 pool records |

## 3. Screening ledger after recovery

`screening_log.csv` is the single canonical ledger (identifiers, our decision fields, no abstracts); `screening_summary.json`
holds the counts.

- Pool 2,311 works (from 11,217 distinct retrieved works). Rubric-screened: **2,011 (87.0%)**; include 1,028, maybe 210, exclude 773.
- Independent second screen of a hash-sampled 10%: 132 records overlap with the screened set; **raw agreement 93.2%,
  Cohen's kappa 0.887 on include/maybe/exclude; 96.2% and kappa 0.922 on in-versus-out.** The remaining dual batches (100
  records) are not rerun: the sample is an agreement check, not a second corpus.
- The 300 unscreened records are a hash-random 13% of the pool. They are triaged by a TF-IDF logistic regression trained on the 2,011
  decisions (`recovery/classifier_validation.json`): cross-validated AUC 0.917; at the chosen threshold cross-validated recall of
  relevant records is 0.970 while 19.9% of records are removed. Applied to the 300: 69 excluded by the classifier, 231 carried
  forward; provenance `classifier_assisted`. A seed record is never excluded by the classifier.

## 4. Web documentation recovered from the stopped dataset agents

69 WebFetch/WebSearch results (115,638 characters; 48 with usable content, the rest empty or blocked) are kept untracked in
`data/web_evidence_recovered.jsonl` and indexed in `recovery/web_evidence_index.csv`. They are the fetch tool's summaries, not
verbatim primary text, and are treated as leads to confirm, not as citations. Topics: SEC EDGAR API and Financial Statement Data
Sets pages, FRED vintage (`realtime_period`, `series_observations`, `series_vintagedates`) and ALFRED, Treasury and H.15, XBRL
data-quality sources, CRSP/Compustat/Sharadar/Yahoo documentation searches, Financial PhraseBank, FNSPID, FiQA, factor libraries.

## 5. Not recoverable, and why a rerun is or is not justified

| Lost | Why | Rerun? |
|---|---|---|
| Baseline-audit shards (signals, experiments, datasets, validation, provenance, internal literature) | 5.13M tokens of reading, no output file, and the transcripts hold only the final limit message as narrative | **No agents.** The registry rows are rebuilt from code (`signals_core.csv`, verified against EXP-007's frozen 103 columns); the experiment record and the provenance question are answered directly from the artifacts and a few targeted reads |
| Dataset-landscape shards | same | **No agents.** The decision-critical data questions are answered by the 48 usable recovered pages plus direct API checks and the pilot data build itself |
| 300 screening records (main 016, 020, 022) | agents stopped before writing | **No**: classifier triage above; reconsidered only if a paper in that slice is found to matter |

## 6. Duplicate or wasted work

1. Baseline-audit run 2 repeated run 1 in full (9 agents, about 3.4M tokens) with no output from either run.
2. A 65-agent screening workflow was launched and failed immediately; the same work was then done by 27 larger direct agents.
3. 100-record screening agents carry about 55,000 tokens of fixed harness overhead each, so per-record cost was high (about 2,000
   tokens per screened record including overhead). The new rule is: no further model screening of this corpus.

## 7. Single next step

Decide the research direction from the screened ledger (nearest prior art for the reliability hypothesis, read from the records
already held), then build the one dataset that direction needs from sources already on disk plus the SEC submissions index.
