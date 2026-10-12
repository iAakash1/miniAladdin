# EXP-014 results - the restating-amendment signal in firms the discovery never saw

Registration: `docs/EXP_014_PREREGISTRATION.md`, fingerprint `eefc4cc03454c3dcf0125f20cf45800fdc583e47f077fc5f18d5032960e3a435`. Run: commit `fa1469ce840af6232c685dd3afd4030734d315f6`, dirty tree: False. Completion: **COMPLETE**. Wall time 1370 s.
Holdout sealed (untouched). Promotion not assessed.

## 1. Outcome

**FRAGILE.** In an independent sample the association is statistically present but failed at least one registered robustness check; it is not established.
Interpretation: **MARKER_OF_PERSISTENT_TROUBLE**.

| Gate | Result |
|---|---|
| R1_power | passed |
| R2_influence | **failed** |
| R3_years | passed |
| R4_full_controls | passed |
| R5_time_separate | passed |
| R6_sector | passed |
| R7_within_firm | **failed** |

### Distance to the registered thresholds (mechanical)

| Gate | Quantity | Observed | Threshold |
|---|---|---|---|
| R1 | distinct treated firms / treated rows (core, 730 days) | 65 / 2,277 | at least 40 / 150 |
| R2 | share of the H1 estimate kept after removing the 5 most influential treated firms | 0.497 (coefficient -0.0267) | at least 0.5, same sign |
| R3 | leave-one-year-out fits with a negative coefficient | 12 of 12 | at least 9 |
| R4 | full-control H1: coefficient / one-sided p | -0.0502 / 0.0140 | negative / below 0.05 |
| R5 | time-separate: core coefficient; any-amendment coefficient / one-sided p | -0.1363; -0.0391 / 0.0980 | negative; negative / below 0.10 |
| R6 | leave-one-sector-out fits with a negative coefficient | 13 of 13 | at least 8 |
| R7 | within-firm H1: coefficient / one-sided p | -0.0551 / 0.0566 | negative / below 0.05 |

The margins are shown so that nobody has to take the gate list on trust; they do not change the label. Thresholds were fixed in the registration and apply mechanically.

Samples: confirmatory 150,884 rows, 1,141 firms, 559 dates (discovery-universe companies excluded: 891; 185,809 panel rows dropped on that ground);
time-separate 35,654 rows, 458 firms.

## 2. Registered regressions

Coefficient on the 21-session forward return rank (centred ranks run from -1 to 1), date x sector fixed effects, 17 controls, wild-cluster bootstrap p (one-sided, negative, firm clusters, null imposed).
Two-way and firm-clustered t statistics are shown for comparison only.

| Test | Coef | t (two-way) | t (firm) | WCR p (one-sided, negative) | WCR p (two-sided) | Treated firms | Treated rows | Rows |
|---|---|---|---|---|---|---|---|---|
| H1 core, 730 days | -0.0537 | -2.43 | -2.43 | 0.0104 | 0.0202 | 65 | 2,277 | 148,343 |
| H2 any amendment, 730 days | 0.0021 | 0.17 | 0.17 | 0.5743 | 0.8671 | 180 | 7,456 | 148,343 |
| R4 H1 with all 76 features as controls | -0.0502 | -2.29 | -2.31 | 0.0140 | 0.0266 | 65 | 2,277 | 148,343 |
| R2 H1 without the 5 most influential treated firms | -0.0267 | -1.31 | -1.30 | 0.1016 | 0.2146 | 60 | 2,051 | 147,162 |
| R5 H1, time-separate sample | -0.1363 | -1.35 | -1.34 | 0.1946 | 0.3998 | 9 | 161 | 34,338 |
| R5 H2, time-separate sample | -0.0391 | -1.36 | -1.35 | 0.0980 | 0.1944 | 58 | 1,798 | 34,338 |
| R7 H1 with a fixed effect per firm (within-firm timing) | -0.0551 | -1.60 | -1.62 | 0.0566 | 0.1192 | 65 | 2,277 | 148,343 |

Holm-adjusted p: H1 0.0208, H2 0.5743. Share of the full H1 estimate kept after removing the five most influential treated firms:
0.497 (removed: sec-5e7757640642ed8a8f92, sec-212bcc6364422e7f06e0, sec-be990a98bf9ad07c0ddf, sec-a5713f4cc272d333f16a, sec-e55b09cc05bf3a914713).

Leave-one-year-out coefficients: 2014: -0.037, 2015: -0.068, 2016: -0.053, 2017: -0.058, 2018: -0.062, 2019: -0.056, 2020: -0.053, 2021: -0.046, 2022: -0.057, 2023: -0.050, 2024: -0.047, 2025: -0.056.
Leave-one-sector-out coefficients: BusEq: -0.034, Chems: -0.064, Durbl: -0.046, Enrgy: -0.055, Hlth: -0.045, Manuf: -0.056, Money: -0.057, NoDur: -0.048, None: -0.054, Other: -0.069, Shops: -0.059, Telcm: -0.054, Utils: -0.057.

### Secondary regressions (not gated)

| Test | Coef | t (two-way) | t (firm) | WCR p (one-sided, negative) | WCR p (two-sided) | Treated firms | Treated rows | Rows |
|---|---|---|---|---|---|---|---|---|
| S10_amendments_without_financials | -0.0108 | -1.01 | -0.99 | 0.1632 | 0.3304 | 287 | 13,075 | 148,343 |
| S11_age_0_90 | -0.0118 | -0.18 | -0.18 | 0.4454 | 0.8620 | 32 | 275 | 148,343 |
| S11_age_180_365 | -0.0150 | -0.35 | -0.36 | 0.3678 | 0.7350 | 41 | 655 | 148,343 |
| S11_age_365_730 | -0.1121 | -3.17 | -3.20 | 0.0028 | 0.0038 | 44 | 1,104 | 148,343 |
| S11_age_90_180 | 0.0531 | 0.94 | 0.95 | 0.8180 | 0.3584 | 34 | 299 | 148,343 |
| S12_illiquid_half | -0.0544 | -2.03 | -2.07 | 0.0216 | 0.0420 | 63 | 1,409 | 74,403 |
| S12_liquid_half | -0.0468 | -1.59 | -1.63 | 0.0544 | 0.1100 | 43 | 868 | 73,940 |
| S1_core_365 | -0.0042 | -0.15 | -0.16 | 0.4370 | 0.8748 | 51 | 1,205 | 148,343 |
| S2_core_1095 | -0.0442 | -2.65 | -2.69 | 0.0030 | 0.0062 | 76 | 3,245 | 148,343 |
| S3_unchanged | 0.0287 | 2.01 | 1.96 | 0.9692 | 0.0588 | 104 | 4,616 | 148,343 |
| S4_unclass | 0.0016 | 0.05 | 0.05 | 0.5236 | 0.9614 | 36 | 1,075 | 148,343 |
| S5_k_core | -0.0121 | -0.36 | -0.36 | 0.3698 | 0.7176 | 51 | 1,907 | 148,343 |
| S6_q_core | -0.0505 | -1.22 | -1.25 | 0.1132 | 0.2340 | 39 | 1,478 | 148,343 |
| S8_item_4_02 | -0.0832 | -3.74 | -3.79 | 0.0004 | 0.0006 | 74 | 2,368 | 148,343 |
| S9_core_with_4_02_and_nt | 0.0587 | 2.02 | 2.00 | 0.9704 | 0.0542 | 65 | 2,277 | 148,343 |

S11 (age of a core amendment) and S12 (liquidity halves) are descriptive and were registered as such: the age bins show where in time after an amendment any association sits (the competing prediction of
Frieder and Shanthikumar is a positive coefficient in the first two bins), the halves show whether it lives in the less liquid stocks.

## 3. Event-time bins (interpretation diagnostic)

| Bin | Coef | WCR p | Treated firms |
|---|---|---|---|
| D_core_next365 | -0.0747 | 0.0120 | 43 |
| D_core_prev365 | -0.0013 | 0.4748 | 51 |

Anticipation ratio coef(next 365 days) / coef(previous 365 days): 58.388 (below 0.5: TIME_SPECIFIC). The ratio is ill-conditioned because its denominator, the coefficient for amendments usable in the previous 365 days (-0.0013, one-sided p 0.4748), is indistinguishable from zero, while the coefficient for amendments that will become usable in the NEXT 365 days is -0.0747 (one-sided p 0.0120). The registered rule labels the pattern MARKER_OF_PERSISTENT_TROUBLE; read plainly, the association is not a drift in the first year after the amendment: it is present before the amendment (the look-ahead bin) and in the second year after it (S11).

## 4. Size of the procedure on the real label structure

200 draws, each giving 65 random firms one placebo amendment: rejection rate at 5% (one-sided) 0.155, at 1% 0.030
(pooled regression; mean placebo coefficient -0.0164, sd 0.0255). With a fixed effect per firm: 0.065 at 5%, 0.015 at 1%
(mean 0.0016, sd 0.0366). These are the numbers of THIS run on the real labels with placebo events; the pre-registration quotes the earlier pre-run values.

## 4b. Descriptive notes on the secondary analyses (not part of the decision)

* **Where the association sits in time (S11 and the event-time bins).** Amendments first usable 0-89 days earlier: -0.0118 (two-sided p 0.8620); 90-179: 0.0531 (0.3584); 180-364: -0.0150 (0.7350); 365-729: -0.1121 (0.0038). The registered reading rule said a rebound of the Frieder and Shanthikumar kind would show as positive coefficients in the 90-179 and 180-364 day bins: the 90-179 coefficient is positive and not distinguishable from zero, the 180-364 coefficient is negative and not distinguishable from zero, so these data neither show nor exclude that rebound. The negative association is concentrated in amendments that are one to two years old and, in the look-ahead bin, in firms that will file a value-changing amendment within the next year; it is not visible in the first year after the amendment.
* **Item 4.02 and late-filing notices (S8, S9).** An Item 4.02 (non-reliance) 8-K in the trailing 730 days: coefficient -0.0832 (two-sided p 0.0006, 74 firms), stronger than H1. With Item 4.02 and late-filing notices entered beside it, the core-amendment coefficient is 0.0587 (two-sided p 0.0542) and the Item 4.02 coefficient -0.1246: the amendment adds nothing in the registered direction once the announcement is in the model. These are registered secondary analyses, sixteen in all, not corrected for multiplicity and not gated.
* **Any amendment, unchanged-number amendments, other forms.** H2 (any amendment): 0.0021 (adjusted p 0.5743); S3 (numbers unchanged): 0.0287 (two-sided p 0.0588); S10 (no financial statements): -0.0108; S5 and S6 (10-K/A and 10-Q/A): -0.0121 and -0.0505.
* **Liquidity (S12).** More liquid half -0.0468 (one-sided p 0.0544, 43 firms), less liquid half -0.0544 (0.0216, 63 firms): the point estimates are close, so the pooled association is not confined to the less liquid stocks, but neither half has much power alone.
* **Size against the discovery sample.** The discovery coefficient was -0.245 (18 treated firms; -0.154 with a firm effect); here -0.0537 pooled and -0.0551 within firm, about a fifth to a third of the discovery size, consistent with the shrinkage expected of a selected discovery estimate.
* **Machine learning and economics.** The amendment block adds 0.00040 (ridge) and 0.00038 (boosted) Rank IC, labels {'T_boosted': 'NOT_SUPPORTED', 'T_ridge': 'NOT_SUPPORTED'}; with the out-of-sample ridge score held fixed the H1 coefficient is -0.0535. The frozen portfolio's net Sharpe at 10 bp is similar with and without the block (see the table). The economics describe the independent universe in general and are not a promotion argument.

## 5. Machine-learning increment and economics (reported separately)

Labels (separate verdicts, not part of the decision): {'T_boosted': 'NOT_SUPPORTED', 'T_ridge': 'NOT_SUPPORTED'}.

| Contrast | Arms | Mean Rank-IC difference | HAC t | one-sided p | Holm p | Positive folds | Block-bootstrap 95% |
|---|---|---|---|---|---|---|---|
| C_permute | M1 vs P1 | 0.00048 | 0.57 | 0.2856 | n/a | 5 of 8 | [-0.00143, 0.00193] |
| C_shift | M1 vs P1s | -0.00068 | -0.68 | 0.7528 | n/a | 2 of 8 | [-0.00276, 0.00111] |
| T_boosted | G1 vs G0 | 0.00038 | 1.42 | 0.0774 | 0.1547 | 7 of 8 | [-0.00017, 0.00093] |
| T_ridge | M1 vs M0 | 0.00040 | 0.48 | 0.3152 | 0.3152 | 5 of 8 | [-0.00145, 0.00184] |

Secondary S7, H1 with the out-of-sample ridge score held fixed: coefficient -0.0535, wild-cluster one-sided p 0.0472, 49 treated firms, 103,971 rows.

Saved artifact: `experiments/EXP-014/model/M1.joblib` (git-ignored; SHA-256 `ef9866ed2864b3dd46982101b2bcc78994f3074af17453e16b36fcd11855c148`); fresh-process reload check: {'features': 81, 'max_abs_difference': 0.0, 'ok': True, 'rows': 2000}.

### Economics (the frozen 21-session portfolio, 10 bp)

| Arm:seed | Mean Rank IC | Net Sharpe 10 bp | Gross Sharpe | Annualised turnover | Cost share of gross |
|---|---|---|---|---|---|
| G0:0 | 0.03588 | 0.577 | 0.696 | 2.71 | 0.170 |
| G0:1 | 0.03299 | 0.316 | 0.439 | 2.76 | 0.281 |
| G0:2 | 0.03647 | 0.477 | 0.588 | 2.70 | 0.188 |
| G1:0 | 0.03624 | 0.603 | 0.721 | 2.72 | 0.163 |
| G1:1 | 0.03300 | 0.319 | 0.443 | 2.76 | 0.280 |
| G1:2 | 0.03726 | 0.461 | 0.571 | 2.69 | 0.192 |
| M0:0 | 0.02984 | 0.322 | 0.444 | 2.74 | 0.275 |
| M1:0 | 0.03024 | 0.343 | 0.465 | 2.73 | 0.263 |


## 6. Reproduction

`python -m scripts.quant.exp014 run --workers 6` (gate first); outputs under `experiments/EXP-014/` with a manifest of SHA-256 hashes; saved model scored again in a fresh process by `python -m scripts.quant.exp014 infer`.
