# Do value-changing amendments to periodic reports predict next-month return ranks? A preregistered test on firms the discovery never saw

*Draft for the owner's review, generated from `experiments/EXP-014` (registered run, commit `fa1469ce840af6232c685dd3afd4030734d315f6`, registration commit `fa1469ce840af6232c685dd3afd4030734d315f6`, fingerprint `eefc4cc03454c3dcf0125f20cf45800fdc583e47f077fc5f18d5032960e3a435`). Not submission-ready: see Declarations.*

## Abstract

**Outcome: FRAGILE.** In an independent sample the association is statistically present but failed at least one registered robustness check; it is not established. Confirmatory sample: 150,884 firm-dates, 1,141 firms with a trusted identity, ranked 251 to 1,000 by liquidity, none of them in the discovery universe, 2014-04 to 2025-05.
Coefficient on a value-changing amendment in the trailing 730 days: -0.0537 centred-rank units (wild-cluster one-sided p 0.0104, two-sided 0.0202; Holm-adjusted 0.0208); with a fixed effect per firm -0.0551
(p 0.0566). Gates: R1_power passed, R2_influence FAILED, R3_years passed, R4_full_controls passed, R5_time_separate passed, R6_sector passed, R7_within_firm FAILED. The holdout was not opened. Registered interpretation: MARKER_OF_PERSISTENT_TROUBLE; the association is present in the look-ahead bin (amendments that become usable within a year) and in amendments one to two years old, not in the first year after them.

## 1. Introduction

Studies of restatement announcements agree on the immediate loss and disagree about what follows: negative abnormal returns over several years in some samples, no drift where the news is about cash flows, and, in a hand-collected sample of NYSE announcements 1993 to 2002, a
positive return 64 to 126 trading days later (Frieder and Shanthikumar 2008). For a related reliability disclosure, material weaknesses in internal control, a 2025 study finds negative drift (Ghosh et al.). Content-classified amendments to periodic reports, which change
the reported numbers or do not, have not been examined as a cross-sectional predictor in the studies found (`17_RECENT_LITERATURE_2022_2026.md`). A discovery on the 250 most liquid names suggested that firms with a recent value-changing amendment earn lower next-month return ranks; it rested on 18 treated firms.
This paper reports the single preregistered test of that finding on firms the discovery never saw.

## 2. Data and construction

Amendment forms (10-K/A, 10-Q/A and transition variants) come from the SEC Financial Statement Data Sets; each is classified by comparing its revenue, net income, assets, liabilities, equity and operating cash flow with the previous version (value-changing: any differs by more than 1%).
Availability is the first session whose close-based decision may use the filing (accepted before 16:00 New York time: that session). The acceptance times in the SEC's submissions JSON are wrong for 28.2% of 96,429 matched filings and were not used; the Data Sets' stamps obey the filing-date rule for 99.2%.
Prices come from a community dataset whose redistribution terms have not been reviewed (derived statistics only). The outcome is the centred cross-sectional rank (from -1 to 1) of the 21-session forward return.

## 3. Design, as registered

H1: the coefficient on a value-changing amendment in the trailing 730 days is negative (date x Fama-French 12 sector effects, 17 controls); H2: the same for any amendment; Holm across the two, wild-cluster bootstrap over firms with the null imposed (1141 firms, 9,999 draws).
Seven gates (power, influence, calendar years, full controls, time-separate sample, sectors, within-firm). Labels: SURVIVES, FRAGILE, REVERSED (positive coefficient, two-sided p < 0.05), NOT_REPLICATED, INCONCLUSIVE. Secondary: S1 to S12, with S11 (age of the amendment) and S12 (liquidity halves) descriptive.
A machine-learning increment and a cost-aware portfolio are reported separately and cannot rescue a failed H1.

## 4. Size of the procedure

On the real label structure with placebo amendments on length- and sector-matched untreated firms, the pooled regression rejected 0.155 of 200 draws at 5% and the regression with a firm fixed effect 0.065 of 200 (this run); the pre-registration quotes the earlier pre-run values (13.3% and 6.3%).

## 5. Results

### 5.1 Sample

150,884 labelled rows, 1,141 firms, 559 dates; 65 firms and 2,277 rows carry a value-changing amendment in the trailing 730 days.

### 5.2 Registered regressions and gates

| Test | Coef | t (firm) | WCR p (neg.) | WCR p (2-sided) | Treated firms | Treated rows |
|---|---|---|---|---|---|---|
| H1 value-changing, 730 days | -0.0537 | -2.43 | 0.0104 | 0.0202 | 65 | 2,277 |
| H2 any amendment, 730 days | 0.0021 | 0.17 | 0.5743 | 0.8671 | 180 | 7,456 |
| R4 all 76 features | -0.0502 | -2.31 | 0.0140 | 0.0266 | 65 | 2,277 |
| R2 without the 5 most influential firms | -0.0267 | -1.30 | 0.1016 | 0.2146 | 60 | 2,051 |
| R7 firm fixed effect | -0.0551 | -1.62 | 0.0566 | 0.1192 | 65 | 2,277 |
| R5 time-separate, core | -0.1363 | -1.34 | 0.1946 | 0.3998 | 9 | 161 |

Gates: R1_power passed, R2_influence FAILED, R3_years passed, R4_full_controls passed, R5_time_separate passed, R6_sector passed, R7_within_firm FAILED. Failed: R2_influence, R7_within_firm.

### 5.3 Other secondary analyses

| Test | Coef | t (firm) | WCR p (neg.) | WCR p (2-sided) | Treated firms | Treated rows |
|---|---|---|---|---|---|---|
| S10_amendments_without_financials | -0.0108 | -0.99 | 0.1632 | 0.3304 | 287 | 13,075 |
| S1_core_365 | -0.0042 | -0.16 | 0.4370 | 0.8748 | 51 | 1,205 |
| S2_core_1095 | -0.0442 | -2.69 | 0.0030 | 0.0062 | 76 | 3,245 |
| S3_unchanged | 0.0287 | 1.96 | 0.9692 | 0.0588 | 104 | 4,616 |
| S4_unclass | 0.0016 | 0.05 | 0.5236 | 0.9614 | 36 | 1,075 |
| S5_k_core | -0.0121 | -0.36 | 0.3698 | 0.7176 | 51 | 1,907 |
| S6_q_core | -0.0505 | -1.25 | 0.1132 | 0.2340 | 39 | 1,478 |
| S8_item_4_02 | -0.0832 | -3.79 | 0.0004 | 0.0006 | 74 | 2,368 |
| S9_core_with_4_02_and_nt | 0.0587 | 2.00 | 0.9704 | 0.0542 | 65 | 2,277 |

### 5.4 Event time

Anticipation ratio coef(next 365 days) / coef(previous 365 days): 58.388 (below 0.5: time-specific; otherwise a marker of persistent trouble). Interpretation label: MARKER_OF_PERSISTENT_TROUBLE. The coefficient for amendments usable in the previous 365 days is -0.0013 (one-sided p 0.4748), so the ratio is ill-conditioned; the plain reading is that there is no association in the first year after the amendment, and a negative one in the look-ahead bin (-0.0747, one-sided p 0.0120).

### 5.5 Age of the amendment (S11) and liquidity halves (S12), descriptive

| Test | Coef | t (firm) | WCR p (neg.) | WCR p (2-sided) | Treated firms | Treated rows |
|---|---|---|---|---|---|---|
| core amendment first usable 0-89 days earlier (S11) | -0.0118 | -0.18 | 0.4454 | 0.8620 | 32 | 275 |
| core amendment first usable 90-179 days earlier (S11) | 0.0531 | 0.95 | 0.8180 | 0.3584 | 34 | 299 |
| core amendment first usable 180-364 days earlier (S11) | -0.0150 | -0.36 | 0.3678 | 0.7350 | 41 | 655 |
| core amendment first usable 365-729 days earlier (S11) | -0.1121 | -3.20 | 0.0028 | 0.0038 | 44 | 1,104 |
| S12_illiquid_half | -0.0544 | -2.07 | 0.0216 | 0.0420 | 63 | 1,409 |
| S12_liquid_half | -0.0468 | -1.63 | 0.0544 | 0.1100 | 43 | 868 |

### 5.6 Machine-learning increment and economics (separate from the decision)

Labels: T_boosted NOT_SUPPORTED, T_ridge NOT_SUPPORTED.

| Contrast | Arms | Mean Rank-IC difference | HAC t | Holm p | Positive folds |
|---|---|---|---|---|---|
| C_permute | M1 vs P1 | 0.00048 | 0.57 | n/a | 5 of 8 |
| C_shift | M1 vs P1s | -0.00068 | -0.68 | n/a | 2 of 8 |
| T_boosted | G1 vs G0 | 0.00038 | 1.42 | 0.1547 | 7 of 8 |
| T_ridge | M1 vs M0 | 0.00040 | 0.48 | 0.3152 | 5 of 8 |

| Arm:seed | Mean Rank IC | Net Sharpe 10 bp | Gross Sharpe | Cost share of gross |
|---|---|---|---|---|
| G0:0 | 0.03588 | 0.577 | 0.696 | 0.170 |
| G0:1 | 0.03299 | 0.316 | 0.439 | 0.281 |
| G0:2 | 0.03647 | 0.477 | 0.588 | 0.188 |
| G1:0 | 0.03624 | 0.603 | 0.721 | 0.163 |
| G1:1 | 0.03300 | 0.319 | 0.443 | 0.280 |
| G1:2 | 0.03726 | 0.461 | 0.571 | 0.192 |
| M0:0 | 0.02984 | 0.322 | 0.444 | 0.275 |
| M1:0 | 0.03024 | 0.343 | 0.465 | 0.263 |

## 6. Discussion

The association is statistically present in the registered direction (coefficient -0.0537, Holm-adjusted p 0.0208) but it failed R2_influence, R7_within_firm and is therefore not established. Without the five most influential treated firms 0.497 of the estimate remains (the gate needs 0.5), and with a fixed effect per firm the coefficient is -0.0551 with one-sided p 0.0566 (the gate needs below 0.05): the within-firm estimate is as large as the pooled one but less precise, so the data do not separate a within-firm effect from none. The registered interpretation label is MARKER_OF_PERSISTENT_TROUBLE: the coefficient for amendments that become usable in the NEXT 365 days is -0.0747 (one-sided p 0.0120) while that for the previous 365 days is -0.0013, and the age bins (S11) put the negative coefficient in amendments one to two years old (-0.1121), not in the first year. The following are descriptive, registered but uncorrected for multiplicity, and not part of the decision: an Item 4.02 non-reliance 8-K in the trailing 730 days carries a coefficient of -0.0832, and when it and late-filing notices enter the same regression the core-amendment coefficient is 0.0587 (two-sided p 0.0542). Read together, and as a description rather than a test, the amendment looks like a marker of firms in persistent trouble; in the secondary analyses the Item 4.02 announcement, not the amendment, carries the negative association. The rebound that Frieder and Shanthikumar report would have shown as positive coefficients in the 90-179 and 180-364 day bins of S11: they are 0.0531 and -0.0150, neither distinguishable from zero, so these data neither show nor exclude it. The size is about a fifth of the discovery estimate, consistent with the shrinkage of a selected discovery estimate. The machine-learning increment is 0.00040 (ridge) and 0.00038 (boosted) Rank IC, not supported.

## 7. Limitations

* An amendment is a detection and disclosure event: only detected misstatements are observable, so the coefficient is the price relevance of detection and disclosure. An amendment can follow earlier public news (an Item 4.02 8-K, an earnings release).
* Firm type: disclosure failures repeat, and a pooled association can reflect which firms receive amendments; the within-firm gate is the answer and has lower power than the pooled test.
* 65 treated firms and 21-session overlapping labels limit precision; the preregistration states the power.
* The sample shares calendar months with the discovery sample; the time-separate sample has 9 treated firms.
* Names delisting inside the 21-session window have no label, and rows shortly before a firm leaves the sample carry systematically low ranks (-0.083 in the final quarter in a label-only descriptive made before registration); amendments cluster in troubled firms, so exit is a confound that firm effects remove only in part. Delisting returns are not modelled and the price source's licence is unreviewed.
* Sixteen secondary analyses were registered and are not corrected for multiplicity; the Item 4.02 and S9 results are descriptive.
* Evidence on the literature rests on abstracts except where `17_RECENT_LITERATURE_2022_2026.md` says full text.

## Declarations (to be completed by the owner)

Funding, competing interests, data and code availability (SEC data are public; prices are not redistributable; code and registrations are in the repository), and the journal-specific statement on the use of AI tools in preparing the analysis and text, which is a separate duty from the repository's attribution rule and must not be left out.

## References

* Frieder, L. & Shanthikumar, D. M. (2008). After a Restatement: Long-Run Market and Investor Response. SSRN working paper 1106855 (draft of 7 July 2008) [first online 2008-07-07 (date of the draft); issue or print NR; doi 10.2139/ssrn.1106855]. Evidence level in this project: FULL_TEXT.
* Ghosh, A., Ikaheimo, S., Myllymaki, E.-R. & Sihvonen, J. Long-Run Stock Returns Following Internal Control Disclosures. Journal of Business Finance & Accounting [first online 2025-09-16; issue or print 2026-02; doi 10.1111/jbfa.70012]. Evidence level in this project: FULL_TEXT_PARTIAL.
* Ecker, F., Francis, J., Olsson, P. M. & Schipper, K. Payoffs to Aggressiveness. The Accounting Review [first online 2023-10-23; issue or print 2023-11-01; doi 10.2308/tar-2018-0385]. Evidence level in this project: ABSTRACT.
* Cahan, S., Chen, C. & Chen, L. In Financial Statements We Trust: Institutional Investors' Stockholdings after Restatements. The Accounting Review [first online 2024-02-05; issue or print 2024-03-01; doi 10.2308/tar-2019-0654]. Evidence level in this project: ABSTRACT.
* Bangert, J. & Myers, L. The Differential Effects of Non-Reliance Restatements on Retail and Institutional Investor Trading. SSRN working paper 4571695 (2023) [first online 2023-10-09; issue or print 2023; doi 10.2139/ssrn.4571695]. Evidence level in this project: ABSTRACT.
* Barton, F. J., Burnett, B. M., Gunny, K. A. & Miller, B. P. The Importance of Separating the Probability of Committing and Detecting Misstatements in the Restatement Setting. Management Science [first online 2022-12-19; issue or print 2024-01; doi 10.1287/mnsc.2022.4627]. Evidence level in this project: ABSTRACT.
* Zhu, L. Filing Discipline: Regulatory Disclosure Behavior and the Cross-Section of Stock Returns. SSRN working paper 7536681 (2026) [first online 2026-09-30; issue or print 2026; doi 10.2139/ssrn.7536681]. Evidence level in this project: ABSTRACT.
* Ahn, H. Reading the Late-Filing Notification: Form NT Body Narratives Predict Subsequent SEC Restatement Disclosures. SSRN working paper 6932478 (2026) [first online 2026-07-09; issue or print 2026; doi 10.2139/ssrn.6932478]. Evidence level in this project: ABSTRACT.
* Lalwani, V., Meshram, V. & Jindal, V. Empirical Asset Pricing via Machine Learning: The Role of Research Design Choices. European Financial Management [first online 2025-11-07; issue or print 2026-06; doi 10.1111/eufm.70033]. Evidence level in this project: ABSTRACT.
* Avramov, D., Cheng, S. & Metzker, L. Machine Learning vs. Economic Restrictions: Evidence from Stock Return Predictability. Management Science [first online 2022-06-29; issue or print 2023-05; doi 10.1287/mnsc.2022.4449]. Evidence level in this project: ABSTRACT.
* Menkveld, A. J. et al. Nonstandard Errors. The Journal of Finance [first online 2024-04-17; issue or print 2024-06; doi 10.1111/jofi.13337]. Evidence level in this project: ABSTRACT.
* Soebhag, A., Van Vliet, B. & Verwijmeren, P. Non-standard errors in asset pricing: Mind your sorts. Journal of Empirical Finance [first online 2024-06-05; issue or print 2024-09; doi 10.1016/j.jempfin.2024.101517]. Evidence level in this project: ABSTRACT.
* Perignon, C. et al. Computational Reproducibility in Finance: Evidence from 1,000 Tests. Review of Financial Studies [first online 2024-06-21; issue or print 2024-11-01; doi 10.1093/rfs/hhae029]. Evidence level in this project: ABSTRACT.
* Yang, L. & Zhu, M. Misstatement Detection Lag and Prediction Evaluation. The Accounting Review [first online 2026-02-09; issue or print 2026-03-01; doi 10.2308/tar-2023-0073]. Evidence level in this project: ABSTRACT.
