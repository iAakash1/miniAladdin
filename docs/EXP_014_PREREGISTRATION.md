# EXP-014 preregistration - does the restating-amendment signal survive in firms the discovery never saw?

Definition fingerprint: `eefc4cc03454c3dcf0125f20cf45800fdc583e47f077fc5f18d5032960e3a435`

Parent: EXP-012 and EXP-013. Status: **CONFIRMATORY on an independent firm sample - holdout sealed - promotion not assessed.** This document is committed and pushed to the research branch before any
arm is fit on the real label and before any relation between an amendment variable and a return is computed on the registered samples. The fingerprint is the SHA-256 of the canonical definition (`src/quant/study/exp014.py`,
`DEFINITION`) and of the bytes of every method file in section 14. If the definition or a method file changes after registration, the gate refuses to run.

## 1. Purpose, and what this is not

EXP-012 and EXP-013 used the 250 most liquid US names each month. On that sample, firms with a recent amendment to a periodic report earn lower next-month return ranks; the whole effect sits in amendments
that change the reported numbers; and it rests on a small number of firms (60 with any amendment, 18 with a changing amendment). **The sign is not settled by the literature.** Studies of restatement announcements
disagree about what follows: negative long-run abnormal returns in several older studies, no drift where the news is about cash flows, and, in the one paper read in full for this registration (Frieder and
Shanthikumar 2008), no significant negative drift and a significant POSITIVE return 64 to 126 trading days after the announcement; a 2025 paper finds negative drift after material-weakness disclosures
(`16_FRIEDER_SHANTHIKUMAR_FULLTEXT_REVIEW.md`, `17_RECENT_LITERATURE_2022_2026.md`). None of the studies found treats content-classified amendments to periodic reports as a cross-sectional predictor. This study
asks the narrower, testable question: **in firms the discovery never saw, with a point-in-time construction, valid inference for few treated firms and the established controls, is a value-changing amendment followed by
lower return ranks (the registered direction), by higher ones (the opposite direction, reported if the data show it), or by neither; and does it add to a conventional ranking and to a cost-aware portfolio?**

It does not scale the discovery model, claims no investment value, and does not touch the holdout (2025-08-26 onward). A failure is a result.

## 2. What was known and done before registration (disclosure)

* **Discovery sample, exploratory, already analysed** (`validation/phase2_*.json`, `docs/EXP_012_RESULTS.md`, `docs/EXP_013_RESULTS.md`): coefficient on any amendment in two years -0.092 (60 treated firms), on
  changing amendments -0.245 (18 treated firms), on unchanged-number amendments -0.049; wild-cluster bootstrap p about 1e-4 for both; still -0.126 after removing the ten most influential treated firms; the
  paired rank-IC gain of the machine-learning model is fragile. The category definitions, the 730-day window and the control list used here come from that analysis and are therefore **not** independent of it;
  only the sample is.
* **Choices fixed after seeing the discovery results and before touching the independent sample:** the four exhaustive amendment categories, the 730-day window, the controls, the fixed effects (date x
  Fama-French 12), the wild-cluster bootstrap as the decision statistic, and the gates below.
* **Independent sample, what has been looked at:** universe construction (membership counts only), price ingestion checks, the baseline frame's row and label coverage, identity coverage, the
  label-free counts of treated companies in section 4, and a size calibration with placebo events. **No relation between an amendment variable and a return, rank or label has been computed on it.**
* **Label-only descriptives computed on the independent sample** (no amendment variable involved): mean return rank by tenure and by time to a firm's last row (end-of-life rows carry systematically low ranks:
  -0.083 in the final quarter), and by firm lifespan. They motivated the within-firm gate R7 and the position-neutral placebo windows.
* **Literature-driven amendments, made before registration and before any relation between an amendment variable and a return was computed on the independent sample.** After a full-text reading of Frieder and
  Shanthikumar (2008) and an update of the literature to 12 October 2026, the protocol gained (a) the label REVERSED (a positive H1 coefficient with two-sided wild-cluster p < 0.05), because the sign is contested;
  (b) secondary S11, the age of a past core amendment in four bins, because the only significant post-restatement drift in that paper is positive and sits in trading days 64 to 126; (c) secondary S12, H1 in the
  more and the less liquid half, because the machine-learning and design-sensitivity literature finds effects concentrated in difficult-to-trade stocks. None of the three can change SURVIVES, FRAGILE or INCONCLUSIVE.
* **Rehearsal:** the whole pipeline (regressions, machine-learning arms, economics, saved-artifact reload) was run with the label shuffled across firms within each date, to prove that every code path runs
  and that nothing is reported as a result of that run (the regression stage alone had also been rehearsed in an earlier session, before the literature-driven amendments). Its outcome was NOT_REPLICATED with H1 Holm-adjusted p 0.929, as it must be on a shuffled label.

## 3. Data

All inputs are verified by SHA-256 before the study runs (`docs/EXP_014_INPUTS.json`).

| Input | Path | sha256 |
|---|---|---|
| `calendar` | `data/research/derived/exp010b_calendar.json` | `484076244e61292e4b1addd3383982d0665ec6aed66e8ec19374468980747e3c` |
| `classification` | `data/research/derived/amendment_classification_v1.parquet` | `d3ccba49096f873061cb53f420c649e2ea1a30b0a712ccee1ccfccf4c816c509` |
| `edgar_filings` | `data/curated/edgar_filings_v1/filings.parquet` | `422b219b11deb74f6bc158c8bd213d2abb54370fb9932b0620a297280a5720b9` |
| `frozen_identity` | `data/curated/security_master_v3/security_identity_interval.parquet` | `e51d062a93691686d6b00f76be0cc00d7f1deff1049230857a41e1c7669a6130` |
| `frozen_panel` | `data/research/derived/rich_pit_panel.parquet` | `2b8993da1e80a1279d24fe1f6b0b4c49d144cb6f6b0a7c7f785a3203a5e4240a` |
| `fsds_filings` | `data/curated/sec_v3/filings.parquet` | `4e62004745eebd9b7e669adb091ff53a01f2440e5bdd83b7da5efbb660b7ebb6` |
| `mid_panel` | `data/research_mid/derived/rich_pit_panel_mid.parquet` | `3cb9e32a309e768e428860ac4518e60289336b704472ead95c6bf15abb2a2e72` |
| `mid_panel_manifest` | `data/manifests/rich_pit_panel_mid_manifest.json` | `44087208039a44971aab33c25764e7424fea799c32e9687ad026e59373013ba9` |

* **Prices and labels:** the community `post-no-preference/stocks` Dolt dataset (commit recorded in `data/manifests/mid_sample_ingest.json`), read from the local clone into a NEW store
  `data/research_mid/`, capped at 2025-06-30 (holdout starts 2025-08-26; the listing-snapshot table that runs to 2026-08 was deliberately not copied). Its redistribution terms have not been reviewed
  (`datasets.csv` L04): derived statistics are published, prices are not.
* **Universe:** liquidity ranks 251 to 1,000 by three-month median dollar volume (non-ETF, non-test issue, close >= 5), read from each month's whole-market cross-section so that delisted names are present in
  the months they were liquid (171 snapshots, 2,778 members; size-250 rebuild equals the frozen universe on all 171 snapshots).
* **Identity:** ticker to company links graded by name history and exit evidence (`security_master_mid`); only rows with a trusted identity enter. Trusted share of rows: 80.8%.
* **SEC filings:** Financial Statement Data Sets (public domain) for amendments and their content; the EDGAR submissions registry for filing history (2,098 companies,
  481,027 filings of interest). The registry's acceptance stamps were audited against the FSDS and found unreliable for 28.2% of matched 10-K/10-Q filings
  (`data/manifests/edgar_filings_v1.json`, `clock_audit`); the study uses only the FSDS stamps for availability.
* **Panel:** 76 point-in-time features (26 price/liquidity, 50 SEC characteristics), size and industry-relative controls withheld as in the frozen panel; 417,346 rows,
  559 dates, 2,424 symbols.

## 4. Samples, and how many companies carry each treatment (label-free)

**Confirmatory** (mid-liquidity universe, trusted identity, company never in the discovery universe, 2014-04-01 to 2025-05-09): 150,884 labelled rows, 1,141 firms, 559 dates.
**Time-separate** (discovery firms on 2014-04-01 to 2017-03-31, used by EXP-011 to EXP-013 only for training): 35,654 rows, 458 firms.

| Treatment (trailing 730 days) | Confirmatory rows | Confirmatory firms | Time-separate rows | Time-separate firms |
|---|---|---|---|---|
| core_730 | 2,277 | 65 | 161 | 9 |
| other_730 | 59 | 5 | 52 | 1 |
| unchanged_730 | 4,616 | 104 | 1,262 | 44 |
| unclass_730 | 1,075 | 36 | 352 | 9 |
| any_730 | 7,456 | 180 | 1,798 | 58 |

## 5. Variables

- Outcome: `fwd_rank_21`, the centred cross-sectional rank of the 21-session forward return within the universe-date.
- Treatment: four exhaustive, mutually exclusive categories of amendment to a periodic report available in the trailing 730 days: **core** (some of revenue, net income, assets, liabilities, equity or operating
  cash flow differs by more than 1% from the previous version), **other_changed**, **unchanged**, **unclass** (no comparable previous version). Indicators are NaN before the firm has any original periodic report.
  Availability: the first session whose close-based decision may use the amendment (accepted before 16:00 New York time: that session, otherwise the next).
- Controls (17, rank-centred, missing set to 0): log_dollar_volume_21_xs, amihud_21_xs, mom_252_21_xs, mom_21_xs, reversal_5_xs, vol_63_xs, book_to_market_xs, roa_xs, gross_profitability_xs, asset_growth_xs, liabilities_to_assets_xs, accruals_xs, filing_lag_days_xs, days_since_report_xs, periodic_count_400_r, lag_deterioration_r, n_missing_sec_r. The full control set adds all 76 features.
- Fixed effects: date x Fama-French 12 sector.

## 6. Hypotheses and inference

- **H1:** the coefficient on core_730 is negative (with other_730, unchanged_730, unclass_730 as separate regressors).
- **H2:** the coefficient on any_730 (the EXP-012 definition) is negative.
- Holm across H1 and H2 on the wild-cluster bootstrap p-values (one-sided, negative; Webb six-point weights, null imposed, 9,999 draws, firm clusters, seed 20261014).
- The two-way (firm, date) clustered t and the firm-clustered t are reported, never used to decide.
- **Why the bootstrap:** in a simulation with three treated firms of fifty and no effect a plain firm-clustered t rejects 22.5% of the time at the nominal 5%; the bootstrap rejects 4.0% (one-sided).
- **Size on the real label structure.** Each really treated firm is paired with an untreated firm of similar length (rows within 25%) and the same sector, and the partner receives one placebo amendment: a
  730-day window starting on a day drawn uniformly, so that every row of the partner has the same chance of being flagged. The registered regression is then re-estimated and the bootstrap rejection rate counted.
  Pooled regression: 13.3% of 300 draws reject at 5% (one-sided), 2.3% at 1%, mean placebo coefficient
  -0.0147 (sd 0.0248). With a fixed effect per firm: 6.3% and 1.3%, mean coefficient +0.0019
  (sd 0.0365). The pooled regression over-rejects because flagged firms matched on length are short-lived, and short-lived firms have systematically lower return ranks (a firm-length / exit
  confound that is part of what a pooled association means); the within-firm regression is the size-correct test. That is why **SURVIVES requires both** the pooled H1 and the within-firm gate R7.
- **Power (approximate).** Taking the spread of the placebo coefficients above as the sampling standard deviation of the estimator under the null (a normal approximation, ignoring the bootstrap's own noise), the smallest
  true coefficient detected with 80% power by a one-sided 5% test is 0.062 for the pooled regression and 0.091 within firm (centred ranks run from -1 to 1, so 0.1 is
  five percentile points). Power at a true coefficient of -0.245 / -0.154 / -0.077 / -0.05: pooled 100% / 100% / 93% / 65%;
  within firm 100% / 99% / 68% / 39%. The discovery sample's estimates (-0.245 pooled, -0.154 within
  firm) are selected and probably too large; against an effect half their size the within-firm gate has roughly two chances in three. A NOT_REPLICATED outcome is therefore evidence against large effects only.
- **Two-sided reporting.** For REVERSED the two-sided wild-cluster p-value of H1 is used; it is not adjusted for multiplicity (the label is descriptive) and it carries no gate.

## 7. Robustness gates

- **R1_power**: at least 40 distinct treated firms and 150 treated firm-dates for core_730 in the confirmatory sample, else the result is INCONCLUSIVE and nothing is concluded
- **R2_influence**: after removing the 5 treated firms whose deletion moves the coefficient most, the coefficient is still negative and at least 50% of the full-sample estimate
- **R3_years**: the coefficient is negative in at least 9 of the 12 leave-one-calendar-year-out fits (2014 and 2025 are partial years)
- **R4_full_controls**: with the full control set the coefficient is negative with wild-cluster one-sided p < 0.05
- **R5_time_separate**: in the time-separate sample (label-free counts before registration: 9 treated firms for core_730, 58 for any_730) the coefficient on any_730 is negative with wild-cluster one-sided p < 0.10 and the coefficient on core_730 is negative
- **R6_sector**: the coefficient is negative in at least 8 of the 12 leave-one-sector-out fits
- **R7_within_firm**: with a fixed effect per firm added (only the timing of the amendment within a firm identifies the coefficient) the coefficient is negative with wild-cluster one-sided p < 0.05

Secondary analyses (reported, not gated; `secondary_analyses` in the definition): S1: core amendment in the trailing 365 days; S2: core amendment in the trailing 1,095 days; S3: amendments without number changes (unchanged_730); S4: unclassifiable amendments (unclass_730); S5: core amendments to 10-K filings; S6: core amendments to 10-Q filings; S7: H1 with the out-of-sample ridge score held fixed; S8: 8-K Item 4.02 in 730 days; S9: core amendment with Item 4.02 and late-filing notices as competing indicators; S10: amendments that carry no financial statements; S11: age of the most informative past core amendment: four non-overlapping indicators for a core amendment first usable 0-89, 90-179, 180-364 or 365-729 calendar days before the decision day (they sum to core_730), in one regression with the other three categories; coefficients and wild-cluster p-values on both sides, descriptive; S12: H1 re-estimated separately in the more liquid and the less liquid half of the confirmatory sample (split at the date median of the 21-day dollar-volume rank), descriptive

Label-free counts for the two analyses added after the literature update (read from the rehearsal frame; treatment counts do not depend on the label): S11 core amendment first usable 0-89 days earlier: 32 firms / 275 rows; first usable 90-179 days earlier: 34 firms / 299 rows; first usable 180-364 days earlier: 41 firms / 655 rows; first usable 365-729 days earlier: 44 firms / 1,104 rows; S12 illiquid half 63 treated firms / 1,409 treated rows of 74,403; liquid half 43 treated firms / 868 treated rows of 73,940.

**Reading rule for S11 and S12, fixed now.** They are descriptive and are read only if R1 passes. The rebound reported by Frieder and Shanthikumar, if present, would appear as positive S11 coefficients in the 90-179 and 180-364 day bins (their trading days 64-126 are about 90-180 calendar days after an announcement; an amendment can come later than the announcement, so the bins are a rough guide); a negative association that concentrates in the 0-89 day bin would point to the immediate reaction instead. S12 asks whether the H1 coefficient lives in the less liquid half; a coefficient present only there is reported as such and is not a reason to change the decision.

## 8. Interpretation diagnostic

coef(core_next365) / coef(core_prev365) from one regression with the five event-time bins; below 0.5 the association is labelled TIME_SPECIFIC, otherwise MARKER_OF_PERSISTENT_TROUBLE (it is not an information event but a marker)

## 9. Decision rule (applied mechanically by `decide`)

- **SURVIVES**: H1 Holm-adjusted p < 0.05 with negative sign AND R1 to R7 all pass
- **FRAGILE**: H1 Holm-adjusted p < 0.05 with negative sign AND R1 passes AND at least one of R2 to R7 fails
- **REVERSED**: R1 passes, H1 is not significant in the registered direction, and the H1 coefficient is POSITIVE with two-sided wild-cluster p < 0.05 (the opposite sign to the registered hypothesis; descriptive, uncorrected, no gate applies)
- **NOT_REPLICATED**: R1 passes and neither SURVIVES, FRAGILE nor REVERSED applies: H1 adjusted p >= 0.05, or the sign is positive without two-sided p < 0.05
- **INCONCLUSIVE**: R1 fails: too few treated firms to conclude anything

SURVIVES permits one sentence: "in an independent sample the association survived the registered robustness checks", plus the interpretation label. It does not permit a claim of investment value,
production use or a new anomaly. REVERSED permits: "in an independent sample the association has the opposite sign to the registered hypothesis (descriptive)". NOT_REPLICATED permits: "was not reproduced at the
registered level of evidence", and with the power paragraph in section 6 it excludes only large effects.

## 10. Machine-learning increment (reported separately; cannot rescue a failed H1)

Arms: M0 ridge on the 76 features (alpha 10, no search); M1 adds the amendment block (core, other_changed, unchanged, unclass indicators and log1p of the count); G0 and G1 boosted equivalents (frozen
EXP-010A settings, 3 seeds); placebos of M1 (block permuted within date x 5 seeds; block shifted 252 sessions within firm). Test: paired mean Rank IC difference on identical dates, Newey-West HAC (4 lags),
moving-block bootstrap (block 6, 4,000 draws), Holm across the ridge and boosted contrasts, eight recorded folds. No hyperparameter is chosen on any data, so no selection correction is needed. The saved
M1 ridge is scored again in a fresh process and must reproduce the in-memory scores to 1e-9. Secondary S7 re-estimates H1 on the validation-period rows with the M0 out-of-sample score (ranked within date) added
to the controls.

## 11. Economics (reported separately; not part of the decision)

The frozen EXP-010B 21-session portfolio at 10 bp for M0, M1, G0 and G1 on the mid-sample daily panel, with 30 and 50 bp reported alongside. The previous result on the discovery sample was negative for every
ridge portfolio (net Sharpe -0.34 for A1, -0.49 for A5 at 10 bp) and that result is not hidden by this study.

## 12. Multiple testing and the ledger

Two confirmatory hypotheses (Holm), seven gates (mechanical, not tests), sixteen secondary regressions (S1 to S12, S11 being four) and two machine-learning contrasts (reported with their own adjustment), and the cumulative trial count
of the eight folds (1,029 before EXP-012; EXP-012 to EXP-013 added more and are counted in `docs/EXP_013_RESULTS.md`). The confirmatory regressions run on a sample that no earlier trial used.

## 13. Acceptance gates, reproducibility and compute

- every input file's sha256 equals the one recorded here
- no date after 2025-05-09
- label never shuffled outside rehearsal
- all predictions finite
- 8 folds complete for every arm

`python -m scripts.quant.exp014 rehearse` runs everything on a shuffled label (writes outside `experiments/EXP-014`); `python -m scripts.quant.exp014 run` is the registered study. Wall time on a
laptop with six workers: minutes for the regressions, under an hour in all.

## 14. Method files covered by the fingerprint

- `src/quant/study/exp014.py`
- `src/quant/study/exp014_inference.py`
- `src/quant/pit/reliability.py`
- `src/quant/pit/edgar_client.py`
- `scripts/quant/acquire_edgar_submissions.py`
- `scripts/quant/build_independent_sample.py`
- `scripts/quant/build_mid_security_master.py`
- `scripts/quant/build_mid_rich_panel.py`
- `docs/research/market-signal-review-2026-10-11/code/classify_amendments.py`
- `src/quant/study/exp011.py`
- `src/quant/study/exp012.py`
- `src/quant/validation/runner.py`
- `src/quant/models/linear.py`
- `src/quant/models/trees.py`
- `src/quant/models/base.py`
- `src/quant/pit/rich_panel.py`

## 14b. What happens next, whatever the outcome

The sealed holdout (2025-08-26 to 2026-08-28) remains untouched and is the only unused period. Opening it needs a separate, frozen design and the owner's decision; this study does not.

## 15. Known threats, stated in advance

- The independent sample shares calendar months with the discovery sample: common shocks are absorbed by date fixed effects but cannot be removed from the evidence; the time-separate sample is the only
  separation in calendar time and it has 9 treated companies for the core definition.
- Names that delist inside the 21-session window have no label and drop out; restating firms delist more often, which works against finding a negative effect and makes the economic result optimistic.
- The classification of amendments needs a previous version with comparable facts; 45.0% of amendments in the discovery registry are unclassifiable and enter as their own category.
- Identity grades are lower for small and delisted names; only trusted rows enter, which selects on identity.
- The price source's licence has not been reviewed; nothing derived from it is a basis for a product claim.
- An amendment is a detection and disclosure event, not the misstatement itself: only detected misstatements are observable (Barton et al. 2022), so the coefficient measures the price relevance of detection and
  disclosure, and an amendment can follow earlier public news (an Item 4.02 8-K or an earnings release), which is why S9 and the age bins are reported.
- Firm type: material weaknesses repeat (79% conditional against 6% unconditional probability in Ghosh et al.) and filing-discipline effects work through the level, not the within-firm change (Zhu 2026). A pooled
  association can therefore reflect which firms get amendments; the within-firm gate R7 exists for that reason and its power is lower than the pooled test's.
- Several 2026 working papers on filing-process signals (late-filing notices, filing timeliness, 8-K irregularity) are not peer reviewed and report very large alphas in small and volatile stocks; they are context,
  not evidence for or against H1.
