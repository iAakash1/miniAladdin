# Executive research decision

Written 2026-10-12 after the registered pilot (EXP-012) finished. Every number is traceable to a file named in section 6. Nothing here has been peer reviewed, and the review's reading depth is abstract level
(`01_REVIEW_PROTOCOL.md`).

## Decision

1. **Do not scale the reliability idea on this evidence.** The pilot returned one supported test of three, and that result is small, unstable in the most recent two years, confined to the linear model, and does not
   reach the frozen portfolio. A second, separately registered check (EXP-013) found that the gain is carried mainly by one column, the count of recent amendments to periodic reports, which is non-zero in 2.6% of
   validation rows and comes from 60 firms. That makes it a lead about a rare event, to be examined at the level of firms and episodes before anything else, not a finding.
2. **The most useful result for the product is about the product, not about disclosure.** The live scoring engine has never been evaluated on a point-in-time panel; most of its inputs cannot be replayed because provider
   snapshots are not archived (`05_OMNISIGNAL_SIGNAL_AUDIT.md`). A bridging experiment and an append-only snapshot archive are the next steps that change what the platform can honestly claim.
3. **Keep the work exploratory and unpromoted.** The holdout stays sealed, nothing is promoted, no production system changed, and the branch is not merged.

## Update 2026-10-12, Phase II (interim: EXP-014 is designed, partly rehearsed, neither registered nor run)

What the second phase changed in the assessment, each point traceable to a file named in `PHASE2_HANDOFF.md`:

1. **The direction is prior art.** Long-run underperformance after restatements is documented (Gondhalekar, Joshi and McKendall 2012, abstract level: negative abnormal returns in each of four years, about -22% in total);
   informed trading precedes restatements (Desai et al. 2006); restatements disclosed only in a 10-K or 10-Q ("stealth") show no short-window reaction (Irani and Xu 2011). Novelty stays **low**. One probably decisive paper,
   Frieder and Shanthikumar (2008), is unread because SSRN refuses automated access.
2. **The earlier "fragile" verdict applies to the machine-learning gain, not to the regression association.** On the discovery sample the association between a value-changing amendment and lower next-month return ranks
   survives inference built for few treated firms (wild-cluster bootstrap, 18 treated firms, p about 1e-4), the removal of the ten most influential firms (coefficient -0.126 against -0.245), and a firm fixed effect
   (about three quarters of the pooled estimate remains, p 0.008). It is not a clustering artefact and not mainly a stable firm trait. It is also not independent evidence: it is the sample that produced the finding. The
   association is concentrated in the first year after the amendment (-0.228) and the same firms already rank lower in the year before it (-0.110, ratio 0.48): informed trading or distress as much as news.
3. **A data finding with value of its own.** The acceptance time in the SEC's submissions JSON is wrong for 28.2% of 96,429 filings matched to the Financial Statement Data Sets; the Financial Statement Data Sets' stamps obey the
   EDGAR filing-date rule 99.2% of the time. Any study that takes the JSON stamp as an availability time will misplace roughly a quarter of its filings by 4 to 10 hours, some of them before they were public.
4. **An independent test is now possible and designed.** A second firm sample (liquidity ranks 251 to 1,000, delisted names included, companies from the discovery universe excluded) has 65 companies with a value-changing
   amendment against 18 in the discovery sample. EXP-014 states one hypothesis, a wild-cluster bootstrap decision statistic, seven robustness gates including a within-firm test, a mechanical decision rule and a separate machine-learning
   and portfolio assessment. On the real label structure the pooled regression over-rejects under placebo amendments (13% at a nominal 5%) because short-lived firms have low ranks; the within-firm regression does not (6%), so the
   registered rule needs both.
5. **The live scorer cannot be evaluated on the past.** About 45% of the composite's weight (momentum and reversal) is replayable from prices, 15% only through a different SEC-based definition, 40% (news and fundamentals) not at
   all. A hash-chained snapshot archive library now exists and is tested; it reconstructs nothing, and no capture job runs.

**Interim decision.** Do not describe the amendment effect as a discovery or as investment value. Run EXP-014 once, as registered. A Q1-level empirical paper on this variable is **not supported at present**: the sign is known,
the point-in-time handling of SEC data is not new (Liu 2026 at abstract level), and the economic result so far is negative. What could stand on its own, depending on EXP-014, is an independent, valid-inference replication
with the data-audit finding and the archive design; where that fits is the owner's call. If EXP-014 does not replicate, the forward-looking contribution is Path B (prospective capture and a pre-registered evaluation of the
price-derived sleeves). The single highest-value next step is the registered EXP-014 run.

## The nine questions

1. **What is genuinely new?** Little. The idea that reporting reliability conditions how well a signal predicts is two decades old, and filing timeliness as a return predictor is published (Bannouh, Geng and Peeters 2019;
   Brooks, Cheng, Liu and Yu 2023). New here, modestly: a vendor-free, strictly point-in-time construction of four disclosure-process variables from the SEC filing registry (independently recomputed, 0 mismatches in 16,000
   comparisons), tested as predictors and moderators in a preregistered, placebo-controlled pipeline with a measured noise floor. Novelty: low to medium, confidence moderate-low (`06_PRIOR_ART_AND_NOVELTY.md`).
2. **Closest prior work.** Bannouh et al. 2019 and Brooks et al. 2023 (reporting lag and 10-K timeliness predict returns); Zhang 2006 and Francis et al. 2007 (information uncertainty moderates continuation and drift);
   Chen, Khan, Kogan and Serafeim 2020 (accounting quality and delayed processing); the restatement literature (Palmrose et al.; Hribar and Jenkins; Dechow et al.), which treats amendments as events.
3. **The exact claim tested.** Adding four point-in-time disclosure-process columns (and their composite) to a rich fundamentals set raises the ordering quality (mean Rank IC) of a ridge ranking model (T1); letting the
   composite moderate 48 fundamentals features raises it further (T2); the two reliability variables already in the set contribute (T3). Each against placebos built from the same variables.
4. **Dataset.** SEC Financial Statement Data Sets registry (371,229 filings, sha256 `4e62004745eebd9b...`), the frozen rich point-in-time panel (139,292 name-dates, 762 securities, 2014-04-03 to 2025-05-09), and the derived
   reliability table (sha256 `042ac1fc12957f25...`, coverage 91.8%). Manifests: `data_manifest.json`, `provenance_manifest.json`, `dataset_catalogue.csv`. Prices come from a community source whose terms are unreviewed.
5. **What counts as success.** Holm-adjusted one-sided p below 0.05, a positive mean difference in at least 6 of 8 folds, and a positive margin over every mapped placebo (preregistered). For the program: the same result
   survives an attribution check and a single frozen look at data not used to design it, and shows up in the stronger (boosted) model or in cost-aware portfolio terms.
6. **What falsifies it.** The same contrast not supported, or reproduced by its own placebo. T2 and T3 are not supported; T1 passes the rule.
7. **What the pilot established.**
   - The pipeline is sound and reproducible: arms A0 and A1 reproduced the parent experiment to 4e-17; a rehearsal on a label shuffled within each date returned NOT_SUPPORTED on every test; both saved models reload in fresh
     processes; 1,264 quant tests pass; protected EXP-006 and EXP-007 files are byte-identical.
   - **T1 SUPPORTED** under the registered rule: +0.00515 Rank IC (0.0149 to 0.0200), HAC t 2.68, Holm p 0.011, interval [+0.0012, +0.0091], positive in 6 of 8 folds; the permuted-across-firms placebo adds nothing
     (A5 beats it by +0.0054, t 2.85).
   - **But:** the gain is absent in the last two validation years (folds 6 and 7: -0.0121 and -0.0007); a one-year-shifted version of the same columns keeps about half of it (A5 beats that placebo by +0.0024, t 1.28), so much
     of it looks like a persistent firm trait; the boosted model gains nothing (+0.0015, t 0.77); the frozen portfolio's net Sharpe at 10 bp does not improve (A5 -0.49 against A1 -0.34, and the unfitted momentum rank scores
     +0.39); moderation (T2) lowered the ordering and the existing lag variables (T3) are positive but not significant after adjustment (Holm 0.117).
   - **EXP-013 (attribution, same folds, separately registered):** the four filing-process ranks carry the gain (adding them alone gives +0.0031, 60% of it; removing them loses 78%); within them the amendment count alone
     adds +0.0024 (t 2.50, 6 of 8 folds). The composite adds nothing, and the missing-fundamentals count shares 27% without beating its own shifted placebo. The registered prior expectation (composite and lateness
     would lead, amendments would not) was wrong. The leading group's Holm-adjusted p is 0.058, the amendment variable is non-zero for about 6 names per date, and no firm-level analysis exists.
   - The sensitivity statement in the registration was too optimistic: realised standard errors were 1.9 times larger for T1 and 8 times for T3 than in the shuffled-label rehearsal, so the T1 effect sits close to the
     smallest effect the design could detect, where estimates tend to overstate (`docs/EXP_012_RESULTS.md`, section 7).
8. **What remains unproven.** Whether the amendment effect survives firm-clustered inference and leave-one-firm-out checks (60 firms, about 6 names per date); whether it survives outside the validation folds (the sealed holdout was not used); whether it exists for smaller firms, other markets or a richer
   disclosure measure; any mechanism; any economic value; and the full-text content of the closest prior works. Cross-vendor disagreement and provider health could not be tested at all: no history exists.
9. **Ready for a full-scale study?** No. The effect is small, unstable at the end of the sample, absent for the strongest model, untranslated into portfolio terms and carried by a rare event; the novelty is low to medium
   (restatements and later returns are an old topic); the data behind the new variables are thin; the folds have been looked at many times. A full-scale study would need an event-level analysis with firm-clustered inference, a richer disclosure measure (the full EDGAR submission index with
   late-filing notices and non-reliance events), a larger universe, a single frozen look at the holdout decided by the owner, and full-text reading of the closest works.

## What was delivered, and what is still open

| Item | State |
|---|---|
| Systematic review with coverage statement, ledger, bibliography, PRISMA counts | done; 11,217 distinct works, 2,311 screened pool, 2,011 rubric-screened, kappa 0.887; sensitivity against known anchors 77%; no full text read |
| Signal registry and audit (research and live) | done; 162 rows; the live composite is unvalidated on a point-in-time panel |
| Dataset landscape | done; 26 datasets; commercial sources unobtainable; no provider history anywhere |
| Candidate directions scored | done; narrowed to EXP-012; alternatives C and E on file |
| Prior-art and novelty audit | done at abstract and metadata level |
| Registered pilot EXP-012, results, saved models | done; documented in `docs/EXP_012_RESULTS.md` |
| Peer-review panel simulation, journal map, reproducibility plan, manuscript draft | done (self-critique, not independent review); journal quartiles unverified |
| Attribution of the T1 gain | done: EXP-013, `docs/EXP_013_RESULTS.md` (amendment ranks carry it; few firms) |
| Event-level analysis of the amendment effect | proposed, separately registered, not started |

## Decisions that belong to the owner

1. Whether to open the sealed holdout once, with a single frozen design, to test whether T1 survives (this study did not).
2. Whether to commission the bridging experiment on the live composite and an append-only archive of provider snapshots.
3. A real SEC contact for `SEC_USER_AGENT`; an OpenAlex key (needs an account) to finish the retrieval; the DoltHub licence review; an XBRL US token (needs an account); the wording of any journal AI declaration.
4. What to do about the two Vercel preview deployments that the branch push created (they are previews, not production).

## Disclosures

- The account email was placed in the headers of the first scholarly-API calls (removed from the code; requests made carried it; the first commit contains the constant; history not rewritten).
- Three screening batches (300 records) were lost with the usage limit and triaged by a validated classifier; they are not counted among the included records.
- EXP-013 is a second look at the same folds. Its first draft of the attribution rule labelled two groups on a pure-noise rehearsal, so the rule was tightened before registration; its prior expectation was wrong. Both are recorded in its documents.
- The naive-reference look disclosed in the registration (0.0204) was computed on the rehearsal's row set; on the registered rows the pre-declared reference is 0.0158. The two differ because shuffling a label moves missing labels.
- Title-and-abstract screening and the drafting of this package used automated assistance; a journal declaration is the owner's to word (`10_JOURNAL_POSITIONING.md`).
- Pushing the branch caused Vercel's Git integration to build two preview deployments; production (`/api/build` commit `1b3e6c7`) is unchanged.

## Where everything is

Canonical state `RESEARCH_STATE.md`; registration `docs/EXP_012_PREREGISTRATION.md`; results `docs/EXP_012_RESULTS.md`, `docs/EXP_013_RESULTS.md` and `experiments/EXP-012/`, `experiments/EXP-013/`; review files `01` to `11` and the CSV, JSON and BibTeX
files in this folder; manuscript draft `manuscript/draft.md`.
