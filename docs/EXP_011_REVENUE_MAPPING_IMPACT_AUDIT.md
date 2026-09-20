# EXP-011 Revenue-Mapping Impact Audit

Status: **COMPLETE_OUTCOME_BLIND**  
Classification: **UNRESOLVED_MAPPING_IMPACT**

## Scope and firewall

This is a parallel corrected-data integrity audit of the frozen EXP-011 population. It does not edit `sec_v3`, `ds-richpit-ff3d3f556488b7da`, or any EXP-011 output. It loaded no target or return columns, fit zero models, computed no IC/Sharpe/portfolio statistic, and did not access the sealed holdout.

The conservative rule uses consolidated, undimensioned USD facts already admitted by SEC v3 plus `pre.txt` income-statement presentation. A differing candidate is selected only when it is the unique explicitly labelled total/net revenue line or the unique candidate presented on the income statement. Equal candidates preserve the frozen value. Multiple plausible totals, duplicate-tag conflicts, or absent presentation evidence are `REVENUE_AMBIGUOUS`; the shadow view leaves revenue missing.

## Measured filing scope

- Frozen rows: 139,292; CIKs: 743; dates: 2014-04-03 through 2025-05-09.
- Multi-candidate annual filings: 393 (1,142 filing-period contexts, including comparative periods).
- Unambiguously corrected disagreements: 171 filings (480 contexts).
- Ambiguous filings: 100 (290 contexts).
- Affected CIKs (corrected or ambiguous): 58.
- Corrected/frozen revenue ratio: median 1.0851983275838373, p05 0.8270217530141281, p95 157.6445611731232, min 0.4504194579087069, max 744.1147859922179.

Reason codes:

- `CANDIDATES_VALUE_EQUIVALENT`: 51
- `MULTIPLE_PLAUSIBLE_TOTALS`: 290
- `UNIQUE_EXPLICIT_TOTAL_IS_LABEL`: 801

## Attached-snapshot impact

4,256 of 139,292 EXP-011 name-dates (3.0555%) receive a different revenue-dependent snapshot in the shadow view. This count excludes cross-sectional rank propagation to otherwise unchanged names.

### By validation period

| Period | Rows | Affected | Share |
|---|---:|---:|---:|
| fold_0 | 12,726 | 154 | 1.2101% |
| fold_1 | 12,322 | 231 | 1.8747% |
| fold_2 | 12,376 | 648 | 5.2359% |
| fold_3 | 12,483 | 512 | 4.1016% |
| fold_4 | 12,460 | 584 | 4.6870% |
| fold_5 | 12,737 | 687 | 5.3937% |
| fold_6 | 12,492 | 494 | 3.9545% |
| fold_7 | 12,745 | 393 | 3.0836% |
| train_only | 38,951 | 553 | 1.4197% |

### By year

| Year | Rows | Affected | Share |
|---|---:|---:|---:|
| 2014 | 9,702 | 122 | 1.2575% |
| 2015 | 12,499 | 195 | 1.5601% |
| 2016 | 12,500 | 180 | 1.4400% |
| 2017 | 12,744 | 159 | 1.2476% |
| 2018 | 12,389 | 124 | 1.0009% |
| 2019 | 12,280 | 598 | 4.8697% |
| 2020 | 12,507 | 554 | 4.4295% |
| 2021 | 12,451 | 548 | 4.4013% |
| 2022 | 12,733 | 683 | 5.3640% |
| 2023 | 12,492 | 549 | 4.3948% |
| 2024 | 12,500 | 415 | 3.3200% |
| 2025 | 4,495 | 129 | 2.8699% |

### By filer regime

| Regime | Rows | Affected | Share |
|---|---:|---:|---:|
| DOMESTIC_10K | 129,327 | 4,252 | 3.2878% |
| MIXED | 998 | 4 | 0.4008% |
| UNRESOLVED | 8,967 | 0 | 0.0000% |

## Actual revenue dependency trace

The list below is derived from `src/quant/features/pit_fundamentals.py` and `src/quant/pit/rich_panel.py`, not from the prompt:

- `gross_profitability_xs` — conditional: gross profit falls back to revenue minus cost of revenue
- `gross_margin_xs` — revenue denominator; conditional gross-profit fallback
- `operating_margin_xs` — revenue denominator
- `net_margin_xs` — revenue denominator
- `cash_flow_margin_xs` — revenue denominator
- `ebitda_margin_xs` — revenue denominator
- `asset_turnover_xs` — revenue numerator
- `capex_to_revenue_xs` — revenue denominator
- `gross_margin_stability_xs` — rolling history of gross margin
- `revenue_growth_xs` — current and year-ago revenue
- `gross_profit_growth_xs` — conditional current gross-profit fallback uses revenue
- `sales_yield_xs` — revenue divided by market capitalisation
- `gross_profit_to_ev_xs` — conditional gross-profit fallback uses revenue
- `sales_to_ev_xs` — revenue divided by enterprise value

## Shadow feature-cell impact

- Common rows: 139,292.
- Frozen features examined: 76.
- Changed feature cells: 981,502.
- Name-dates with any changed rank, including same-date propagation: 114,213.
- Features with at least one changed cell: 14.
- Frozen pipeline reproduction changed cells before correction: 0.

All feature changes below are changes in the stored cross-sectional rank scale. “Same-date ranks changed” equals the changed-cell count for that ranked feature and is recorded in the machine manifest.

| Feature | Changed cells | Row share | Median | p95 | Max | Dependency |
|---|---:|---:|---:|---:|---:|---|
| `gross_profitability_xs` | 73,369 | 52.6728% | 0.008758 | 0.024929 | 1.136700 | conditional: gross profit falls back to revenue minus cost of revenue |
| `gross_margin_xs` | 70,864 | 50.8744% | 0.015805 | 0.039044 | 1.883104 | revenue denominator; conditional gross-profit fallback |
| `operating_margin_xs` | 87,146 | 62.5635% | 0.006734 | 0.022724 | 0.566038 | revenue denominator |
| `net_margin_xs` | 108,447 | 77.8559% | 0.005739 | 0.019679 | 1.336868 | revenue denominator |
| `cash_flow_margin_xs` | 110,880 | 79.6026% | 0.006018 | 0.019233 | 1.539970 | revenue denominator |
| `ebitda_margin_xs` | 39,636 | 28.4553% | 0.009237 | 0.027300 | 0.270172 | revenue denominator |
| `asset_turnover_xs` | 110,964 | 79.6629% | 0.007671 | 0.020756 | 0.880776 | revenue numerator |
| `capex_to_revenue_xs` | 97,952 | 70.3213% | 0.004445 | 0.018077 | 1.958058 | revenue denominator |
| `gross_margin_stability_xs` | 4,732 | 3.3972% | 0.009790 | 0.034278 | 0.464286 | rolling history of gross margin |
| `revenue_growth_xs` | 106,112 | 76.1795% | 0.007615 | 0.034149 | 1.981221 | current and year-ago revenue |
| `gross_profit_growth_xs` | 537 | 0.3855% | 0.012645 | 0.024735 | 0.031250 | conditional current gross-profit fallback uses revenue |
| `sales_yield_xs` | 104,705 | 75.1694% | 0.007362 | 0.021094 | 0.832764 | revenue divided by market capitalisation |
| `gross_profit_to_ev_xs` | 27,743 | 19.9172% | 0.018118 | 0.039394 | 1.846880 | conditional gross-profit fallback uses revenue |
| `sales_to_ev_xs` | 38,415 | 27.5788% | 0.016133 | 0.040753 | 0.880435 | revenue divided by enterprise value |

Changed cells by validation period: `{"fold_0": 85245, "fold_1": 83656, "fold_2": 94031, "fold_3": 89828, "fold_4": 89019, "fold_5": 98831, "fold_6": 96779, "fold_7": 95538, "train_only": 248575}`  
Changed cells by year: `{"2014": 59785, "2015": 79798, "2016": 80528, "2017": 84805, "2018": 83200, "2019": 90178, "2020": 93018, "2021": 87590, "2022": 96803, "2023": 98320, "2024": 93981, "2025": 33496}`

## Scientific interpretation

EXP-011 remains the immutable result of its frozen v3 pipeline. The audit does not label it automatically invalid or harmless. The measured scope contains unresolved filing-level ambiguity, so the descriptive classification is **UNRESOLVED_MAPPING_IMPACT**. A formal corrected-data replication decision is required before the frozen result can support final-candidate selection. No post-hoc materiality percentage was invented.

Machine-readable evidence: `data/manifests/exp011_revenue_mapping_impact.json`.
