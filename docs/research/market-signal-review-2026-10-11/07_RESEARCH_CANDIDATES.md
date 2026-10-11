# Research candidates, scored before any new result was read

Scores are 1 (poor) to 5 (strong) and are judgments; the reasons are the content. "Nearest prior art" names works in
`screening_log.csv` that were read at abstract level (`03_ANNOTATED_BIBLIOGRAPHY.md`). Nothing here is a finding.

| | A evidence-aware forecasting | B reliability-conditioned fusion | C leakage/revision-separating benchmark | D regime-conditional value | E selective prediction | F multimodal PIT | G foundation-model value | H degradation robustness |
|---|---|---|---|---|---|---|---|---|
| Novelty vs closest work | 2 | 3 | 3 | 1 | 2 | 2 | 2 | 3 |
| Importance to financial economics | 3 | 3 | 4 | 3 | 3 | 3 | 3 | 2 |
| Testable with PIT data we can legally hold | **4** | **4** | 4 | 4 | 4 | 2 | 2 | 2 |
| Methodological contribution | 2 | 3 | 4 | 2 | 3 | 2 | 2 | 3 |
| Data available and reconstructable | **4** | **4** | 3 | 4 | 4 | 1 (text vintages) | 3 | 1 (no history of failures) |
| Reproducible by another researcher | 4 | 4 | 4 | 4 | 4 | 2 | 3 | 2 |
| Statistical power on our sample | 2 | 2 | 3 | 2 | 2 | 2 | 2 | 1 |
| Cost and compute | 5 | 5 | 4 | 5 | 5 | 2 | 2 | 4 |
| Easy to falsify | 5 | 5 | 4 | 4 | 4 | 3 | 3 | 3 |
| Distinct from a product feature | 3 | 3 | 4 | 3 | 3 | 3 | 3 | 2 |
| Fit with strong target journals | 3 | 3 | 4 | 2 | 3 | 3 | 3 | 3 |
| Risk of rejection as incremental / generic ML | high | high | medium | high | high | high | high | high |

## Why each score

**A. Evidence-aware cross-sectional forecasting.** The conceptual claim (return predictability depends on the quality and uncertainty of the information
behind a signal) is old and well populated: information uncertainty and return continuation (Zhang 2006, *J. Finance*), information uncertainty and
post-earnings drift (Francis, LaFond, Olsson, Schipper 2007), forecast dispersion (Diether, Malloy, Scherbina 2002), earnings quality and returns (Chan
et al. NBER w8308), reporting lag as a predictor (Bannouh, Geng, Peeters 2019), accounting quality and delayed information processing (Chen, Khan, Kogan,
Serafeim 2020), missing characteristics (Freyberger et al. 2024). What a search of Crossref, arXiv and NBER (143 broad queries and 12 targeted ones) did
not return is a study that builds *disclosure-process* reliability variables point-in-time from SEC registry metadata alone and tests them as direct
predictors and moderators in a cost-aware ML ranking pipeline against placebos. That is a gap in *the search's reach*, not proof of absence.
**Cross-source disagreement and provider telemetry cannot be tested on genuine history.** Checked directly on 2026-10-12: the database migrations
(`supabase/migrations/`) create tables for profiles, watchlists, analysis history, saved reports, portfolio positions, sessions, notes and preferences and none for
provider health, vendor disagreement, staleness or evidence quality; a search of `src/providers`, `src/services/provenance.py`, `src/services/system_health.py` and
`src/observability` finds no write to a file or database (the caches are in-memory with a time to live). Per-user saved analyses exist only for runs users triggered
since launch. No archive exists to test against, and inventing history is ruled out; a prospective logging protocol is the only honest route to that question.

**B. Reliability-conditioned signal fusion.** The same variables used as moderators. Closest outside finance: reliability-weighted fusion (sensor fusion,
truth discovery). Inside finance: conditioning on information uncertainty (A's list). Folded into the primary study as contrast T2.

**C. A benchmark that separates predictability from revisions, leakage and selection.** Strong and practical: macro "real-time versus revised" work exists
(Guo 2009 on the consumption-wealth ratio; Ahmad 2026, Bracher and Funk 2026; "Forecasting in the Fog" 2026), and firm-level restatement look-ahead in
*ML cross-sectional pipelines* looks under-measured. Reconstruction needs original-versus-latest values per (firm, period, tag), which the curated SEC
facts appear to hold; not verified here. Kept as the **first alternative**.

**D. Regime-conditional value.** Crowded; regime labels leak; EXP-006 to EXP-011 already look at the same folds. Rejected as primary.

**E. Selective prediction / abstention.** Direct prior art: "When Alpha Breaks: Two-Level Uncertainty for Safe Deployment of Cross-Sectional Stock Rankers" (Sanderink
2026, arXiv 2603.13252, working paper), plus conformal and missing-covariate uncertainty work. Our contribution would be incremental. **Second alternative.**

**F. Point-in-time multimodal information.** Needs text and call-transcript vintages that cannot be obtained legally and point-in-time (see
`04_DATASET_LANDSCAPE.md`). Rejected as primary on data.

**G. Foundation-model and LLM value.** Needs equalised contexts, contamination controls and compute that the budget excludes; the literature on
look-ahead in language models is still moving. Not started.

**H. Data-degradation robustness.** Needs a history of real degradations. Without it the only honest version is a synthetic stress test, which proves
engineering robustness, not a scientific finding.

## Selection

**Primary: a narrowed A plus B** - disclosure-process reliability as a direct predictor and as a moderator of fundamentals signals, registered as EXP-012,
framed as an exploratory test with placebos, honest about low novelty and low power. **Alternatives kept on file: C, then E.** The study may well return a
clean null; that is a legitimate and useful outcome, and the design is built so that it can.
