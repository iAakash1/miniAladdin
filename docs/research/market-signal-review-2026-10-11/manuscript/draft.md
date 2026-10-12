# Do disclosure-process variables add to a point-in-time ranking of US stocks? A preregistered, placebo-controlled feasibility study

**Status of this draft.** Written for the owner's review; a feasibility study; exploratory; **not submission-ready.** Every number below is read from the registered study's output files
(`experiments/EXP-012/`, summarised in `docs/EXP_012_RESULTS.md`). The positions taken on the literature rest on abstracts and verified bibliographic metadata, not full texts. The declarations at the end are
incomplete on purpose and must be completed by the owner.

## Abstract

Reporting behaviour (whether a firm amends its financial reports, files late relative to its own habit, or misses periodic filings) may signal how far its fundamentals can be trusted. We construct four such
disclosure-process variables strictly point in time from the SEC's filing registry and ask, in a preregistered test, whether they improve a ridge ranking of about 250 liquid US stocks over 404 decision dates (2017-2025,
eight yearly validation folds) beyond a 76-feature point-in-time set. Adding them raised the mean Rank IC from 0.0149 to 0.0200
(+0.0051; Newey-West t 2.68; Holm-adjusted p 0.011), and a placebo that permutes the same columns across firms added nothing. The gain
was positive in six of eight folds but negative in the last two, about half of it survived a one-year shift of the columns, a gradient-boosting model gained nothing, and the frozen cost-aware portfolio did not improve.
Letting the variables moderate fundamentals signals did not help. A separately registered attribution check found that the gain is carried by the filing-process ranks, chiefly the count of amendments to periodic
reports in the previous two years, a rare event (about six names per date, from 60 firms). We read this as a lead, not a finding, and set out what would be needed to settle it.

## 1. Introduction

A fundamentals-based signal is computed from a filing. If the filing is old, was filed late, has since been amended, or belongs to a firm that files irregularly, the signal may describe the firm less well. The
idea that the strength of a signal depends on how uncertain or unreliable the underlying information is has a long record in finance and accounting (Zhang 2006; Francis et al. 2007; Chan et al. 2001; Richardson et al.
2005; Chen et al. 2020), and filing timeliness has been reported to predict returns (Bannouh et al. 2019; Brooks et al. 2023). Amendments and restatements are studied mostly as events (Palmrose et al. 2001; Hribar and
Jenkins 2004; Dechow et al. 2011). What this paper adds is modest and is stated as such: a vendor-free, strictly point-in-time construction of disclosure-process variables from the filing registry, and a preregistered test
of their incremental value inside a cost-aware machine-learning ranking, with placebos that destroy the link to the firm and a noise floor measured in a world with no signal.

The study is also a methodological exercise. Machine-learning return prediction (Gu et al. 2020; Kelly et al. 2023) reports results that move with research design choices (Lalwani et al. 2025); the replication
and multiple-testing literature asks for stricter standards (Harvey et al. 2014; Hou et al. 2018; Jensen et al. 2023); real-time data change what forecasts can achieve (Guo 2009); missing characteristics need explicit
treatment (Freyberger et al. 2024); and filing-derived signals can be under-used by investors (Cohen et al. 2018). We therefore fix the model class, folds and costs from earlier registered work, register the
contrasts and the decision rule before the run, and compare every real information set with a placebo.

## 2. Data and construction

**Universe and panel.** A frozen point-in-time panel of the 250 most liquid US non-ETF names per decision date (every fifth session; 139,292 name-dates, 762 securities, 2014-04-03 to 2025-05-09), 76 features (26
price, liquidity and macro features and 50 SEC-derived characteristics), and the label `fwd_rank_21`, the cross-sectional rank of the next 21 sessions' return. Prices come from a community source whose terms have not been
reviewed; this limits redistribution, not the analysis.

**Disclosure-process variables.** From the SEC Financial Statement Data Sets registry (371,229 filings), each filing becomes usable from the first session whose close-based decision may use it (a filing accepted before the
close is usable that day, otherwise the next session). Four variables result: the number of amendments to periodic reports usable in the trailing 730 days; whether the latest original periodic report has already been
amended; the number of original periodic reports in the trailing 400 days; and the lateness of the latest filing relative to the median of the firm's previous four of the same kind. Values are missing, never zero, before a
firm has any filing history; the registry column that records a *later* amendment is never read. Cross-sectional ranks of these, a count of missing fundamentals and a composite unreliability rank (the mean of five oriented
ranks, two of which are already in the 76 features) form the new block of six columns; 48 interaction terms multiply the fundamentals features by the composite.

**Validation of the construction.** Nine unit tests, including that filings usable after day d cannot change a value at day d; an independent recomputation of 4,000 sampled rows by a deliberately naive path (16,000
comparisons, no mismatch); two deliberate mutations that each broke the intended tests. Coverage is 91.8%. Three of the four raw variables are almost constant (an amendment in the trailing two years appears in 3.5%
of the non-missing rows, an amended latest report in 0.2%, and 98% of rows show four or five periodic reports), so the block is informative mainly through lateness and a small set of rows.

## 3. Design

Eight yearly expanding-window validation folds (validation windows from 2017-05 to 2025-05) with a purge; ridge with alpha 10 (no search); boosted settings frozen in an earlier experiment; the frozen 21-session
portfolio at a 10 basis point half-spread for economics. Fourteen arms and thirty fits: the baseline (A0) and rich (A1) sets that reproduce an earlier experiment, a rich set without its two existing reliability variables
(A2), the new block on the baseline (A4) and on the rich set (A5), the block with interactions (A6), and placebo arms in which the new block (and so the interactions built from it) or the two existing variables are
permuted across firms within each date (five draws) or shifted by 252 sessions within each firm. Three confirmatory contrasts, each of a paired difference of per-date Spearman Rank ICs: T1, A5 - A1; T2, A6 - A5; T3, A1 - A2,
tested one-sided with a Newey-West variance (4 lags) and adjusted by Holm's method; a contrast is SUPPORTED only if the adjusted p is below 0.05, at least six of eight folds are positive, and every mapped placebo is beaten.
The study is exploratory: the same folds were used by earlier experiments (1,029 cumulative trials), the holdout is sealed and was not used, and nothing is promoted. A follow-up attribution study (EXP-013; section 4.1) was registered and pushed separately before it was run. The design, the gates and the likely outcome of the main study were
committed and pushed before the run (registration commit `639eb65a1110`; GitHub is not an independent registry).

## 4. Results

The run reproduced the parent experiment's baseline and rich arms to 4e-17 (gate), all predictions were finite, and the pipeline returned NOT_SUPPORTED on every test in a rehearsal with the label shuffled within each date.

| Test | Contrast | Mean Rank IC difference | HAC t | 95% block-bootstrap interval | Positive folds |
|---|---|---|---|---|---|
| T1 | A5 - A1 | +0.00515 | 2.68 | [+0.0012, +0.0091] | 6/8 |
| T2 | A6 - A5 | -0.00361 | -1.50 | [-0.0086, +0.0012] | 1/8 |
| T3 | A1 - A2 | +0.00268 | 1.57 | [-0.0009, +0.0057] | 6/8 |

Holm-adjusted p: T1 0.011 (SUPPORTED), T2 0.933, T3 0.117 (NOT_SUPPORTED).

| Control | Contrast | Mean difference | HAC t | 95% interval | Positive folds |
|---|---|---|---|---|---|
| C1 | A5 - P0 | +0.00538 | 2.85 | [+0.0016, +0.0092] | 6/8 |
| C2 | A5 - P0s | +0.00242 | 1.28 | [-0.0011, +0.0064] | 6/8 |

| Fold (validation year) | A1 | A5 | A5 - A1 |
|---|---|---|---|
| 2017-18 | +0.0087 | +0.0131 | +0.0043 |
| 2018-19 | +0.0235 | +0.0322 | +0.0087 |
| 2019-20 | +0.0538 | +0.0640 | +0.0102 |
| 2020-21 | +0.0198 | +0.0229 | +0.0031 |
| 2021-22 | -0.0616 | -0.0465 | +0.0151 |
| 2022-23 | +0.0305 | +0.0429 | +0.0124 |
| 2023-24 | +0.0025 | -0.0096 | -0.0121 |
| 2024-25 | +0.0403 | +0.0396 | -0.0007 |

### 4.1 Attribution (EXP-013, separately registered; same folds, so another look)

Arms with each column and each group added to the rich set or removed from the full block (ridge, 34 fits, gates identical to the main study), against permuted and shifted placebos. The labels are descriptive rules fixed in advance.

| Group | Adds to the rich set | HAC t | Positive folds | Share of the T1 gain added / lost on removal | Label |
|---|---|---|---|---|---|
| the four filing-process ranks | +0.00309 | 2.07 | 7/8 | +0.60 / +0.78 | CARRIES |
| the missing-fundamentals count | +0.00140 | 1.68 | 6/8 | +0.27 / +0.27 | SHARES |
| the composite unreliability rank | -0.00019 | -1.25 | 2/8 | -0.04 / +0.13 | NOT_CARRYING |

The amendment count alone adds +0.00243 (t 2.50, 6/8 folds); lateness deterioration, the regularity count and the latest-report-amended flag add
nothing on their own, and the composite adds nothing. The Holm-adjusted p of the leading group is 0.058. The amendment variable is non-zero in 2.6% of the validation rows, from 60 of 754 symbols
(about six names per date).

Secondary contrasts (descriptive): the new block alone on the baseline adds +0.0168 (6/8 folds); the boosted learner's gain from the block is +0.0015
(t 0.77, 4/8). The unfitted 12-1 momentum rank, a pre-declared reference, has a Rank IC of 0.0158 (t 0.88) and a net Sharpe of
+0.39 in the frozen portfolio at 10 bp; the rich ridge set with the block (A5) has -0.49, and the boosted arms about
+0.54.

## 5. Discussion

The registered rule supports T1: six disclosure-process columns add measurable ordering information to a ridge model of fundamentals, and a version of the same columns scrambled across firms does not. Four features of
the evidence argue against reading more into it. The gain is absent in the two most recent validation years. A one-year shift of the columns, which preserves a firm's slow-moving profile but breaks its timing, keeps about
half of the gain (the margin over that placebo is +0.0024, t 1.28), so a persistent firm trait probably carries much of it. The boosted model, which is the
stronger learner here by a wide margin, gains nothing measurable, and the frozen portfolio does not improve. Finally, the realised standard errors were larger than the registered sensitivity analysis assumed (1.9 times for T1),
so the T1 effect sits near the smallest detectable one, where estimates tend to overstate. The failure of T2 and the non-significance of T3 are weak evidence against moderation and for the timeliness literature respectively:
the tests had little power.

The attribution check changes the reading. The registered expectation was that the composite and lateness deterioration would carry the gain and the amendment count almost none; the opposite held. The filing-process ranks
carry about 60% of the gain and their removal loses about 78%, chiefly through the amendment count, which is zero in 97% of rows. That puts the result close to
the literature on restatements and later returns (Palmrose et al. 2001; Hribar and Jenkins 2004), and it rests on a few dozen firm-episodes: the date-level standard errors used here do not account for clustering by firm, so
the evidence is thinner than the t-statistic suggests. A firm-level analysis is the necessary next step.

What the study does show is that the construction is sound and cheap, that a preregistered placebo-controlled test of this kind is feasible on public data, and that a small linear-model gain can coexist with no gain for the
model that matters. It does not show a mechanism: an amendment is not a restatement, and nothing here separates a correction effect from the characteristics of firms that amend.

## 6. Limitations

A single, narrow universe of liquid names, where amendments and late filing are rare, and an effect that rests on about sixty firms; folds reused by many earlier experiments; a registry that holds only filings with financial statements (late-filing notices and
non-reliance events are absent); price data of unreviewed licence; no full-text reading of the closest literature; economics reported as exploratory only; and a ridge-centred test of an incremental block, which cannot
find nonlinear moderation.

## 7. Conclusion

An exploratory, preregistered test finds a small, time-unstable, linear-model gain from point-in-time disclosure-process variables and no gain for gradient boosting or for the frozen portfolio. It does not justify a
claim of new alpha or a change to any production score. A separately registered attribution check traced the gain to the count of recent amendments, a rare event. It justifies one event-level, firm-clustered analysis and, if the owner chooses, one frozen look at data not used to design the study.

## Declarations (to be completed by the owner)

- **Preregistration.** `docs/EXP_012_PREREGISTRATION.md`, committed and pushed before the run (commit `639eb65a1110`); the attribution study is `docs/EXP_013_PREREGISTRATION.md` (commit `a39400f4463f`). Not an independent registry.
- **Data and code availability.** SEC filing data are public records; the reliability table can be rebuilt from them in seconds (`09_REPRODUCIBILITY_PLAN.md`). The price panel's community source has unreviewed terms and is not
  redistributed. Code, tests, manifests and results are in the repository's research branch.
- **Competing interests.** The author develops the OmniSignal platform to which the research is applied.
- **Funding.** None declared.
- **Use of automated tools in the research and in preparing this text.** [To be completed by the owner, truthfully and as the target journal's policy requires; see `10_JOURNAL_POSITIONING.md`. The repository's rule against
  naming tools as authors does not govern a journal declaration.]

## References

- Bryan Kelly, Semyon Malamud, Kangying Zhou (2023). The Virtue of Complexity in Return Prediction. The Journal of Finance. doi:10.1111/jofi.13298
- Campbell R. Harvey, Yan Liu, Heqing Zhu (2014). . . . and the Cross-Section of Expected Returns. NBER Working Paper. doi:10.3386/w20592 [working paper or preprint]
- Hui Guo (2009). Data Revisions And Out‐Of‐Sample Stock Return Predictability. Economic Inquiry. doi:10.1111/j.1465-7295.2008.00169.x
- Jennifer Francis, Ryan LaFond, Per Mikael Olsson, Katherine Schipper (2007). Information Uncertainty and Post‐Earnings‐Announcement‐Drift. Journal of Business Finance & Accounting. doi:10.1111/j.1468-5957.2007.02030.x
- Joachim Freyberger, Bjoern Hoeppner, Andreas Neuhierl, Michael Weber (2024). Missing Data in Asset Pricing Panels. The Review of Financial Studies. doi:10.1093/rfs/hhae003
- Karim Bannouh, Jie-Wei Geng, Bas Peeters (2019). Filing, Fast and Slow: Reporting Lag and Stock Returns. SSRN Electronic Journal. doi:10.2139/ssrn.3432446 [working paper or preprint]
- Kewei Hou, Chen Xue, Lu Zhang (2018). Replicating Anomalies. Review of Financial Studies. doi:10.1093/rfs/hhy131
- Konan Chan, Louis K. Chan, Narasimhan Jegadeesh, Josef Lakonishok (2001). Earnings Quality and Stock Returns. SSRN / NBER / publisher record. doi:10.3386/w8308 [working paper or preprint]
- Lauren Cohen, Christopher Malloy, Quoc Nguyen (2018). Lazy Prices. SSRN / NBER / publisher record. doi:10.3386/w25084 [working paper or preprint]
- Lisa Brooks, Yun Cheng, Linxiao Liu, Michael D. Yu (2023). The Timeliness of 10-K Filings, Financial Performance, and Stock Returns. SSRN Electronic Journal. doi:10.2139/ssrn.4536648 [working paper or preprint]
- Patricia M. Dechow, Weili Ge, Chad R. Larson, Richard G. Sloan (2011). Predicting Material Accounting Misstatements. Contemporary Accounting Research. doi:10.1111/j.1911-3846.2010.01041.x
- Paul Hribar, Nicole Thorne Jenkins (2004). The Effect of Accounting Restatements on Earnings Revisions and the Estimated Cost of Capital. SSRN / NBER / publisher record. doi:10.2139/ssrn.488003 [working paper or preprint]
- Scott A. Richardson, Richard G. Sloan, Mark T. Soliman, İrem Tuna (2005). Accrual reliability, earnings persistence and stock prices. Journal of Accounting and Economics. doi:10.1016/j.jacceco.2005.04.005
- Shihao Gu, Bryan Kelly, Dacheng Xiu (2020). Empirical Asset Pricing via Machine Learning. Review of Financial Studies. doi:10.1093/rfs/hhaa009
- Theis Ingerslev Jensen, Bryan Kelly, Lasse Heje Pedersen (2023). Is There a Replication Crisis in Finance?. The Journal of Finance. doi:10.1111/jofi.13249
- Vaibhav Lalwani, Vedprakash Meshram, Varun Jindal (2025). Empirical Asset Pricing via Machine Learning: The Role of Research Design Choices. European Financial Management. doi:10.1111/eufm.70033
- Wen Chen, Mozaffar Khan, Leonid Kogan, George Serafeim (2020). Cross‐firm return predictability and accounting quality. Journal of Business Finance & Accounting. doi:10.1111/jbfa.12452
- X. Frank Zhang (2006). Information Uncertainty and Stock Returns. The Journal of Finance. doi:10.1111/j.1540-6261.2006.00831.x
- Zoe-Vonna Palmrose, Vernon J. Richardson, Susan Scholz (2001). Determinants of Market Reactions to Restatement Announcements. SSRN / NBER / publisher record. doi:10.2139/ssrn.265009 [working paper or preprint]
