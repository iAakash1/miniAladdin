# PIT feature catalog (rich panel)

Dataset `ds-richpit-ff3d3f556488b7da` (`rich-pit-panel-v1`), 76 features = 26 unchanged baseline + 50 new. Generated from `src/quant/pit/rich_panel_catalog.py` and measured coverage.

## Rules that apply to every new feature

* **Timestamp rule:** usable from the availability session of the filing that reports it: accepted (US Eastern) before 16:00 on a session -> that session; at or after 16:00 or on a non-session day -> the next session.
* **Minimum lag:** 0 sessions after availability; an after-close acceptance is therefore lagged by at least one session. Median filing lag from period end is reported per feature family in the audit.
* **Cross-sectional transform / winsorisation:** winsorise at the 1st/99th percentile within the date's point-in-time universe, then percentile rank scaled to [-1, 1] (`_xs`); fewer than 10 names with a value -> missing.
* **Missing-value policy:** missing stays missing (NaN) into the model; it is never zero, never forward-filled beyond the staleness limit (550 days for a report, 400 days for shares); training-fold-local median imputation happens only inside the walk-forward fold.
* **Source:** SEC Financial Statement Data Sets (`sec-core-facts-v3`) unless a column says otherwise; market cap uses the unadjusted close of the same date.

## Baseline features (unchanged, identical values to `ds-491d761b9f2a6fc4`)

`acceleration_xs`, `dist_52w_high_xs`, `ma_gap_xs`, `mom_21_xs`, `mom_252_21_xs`, `mom_63_xs`, `reversal_5_xs`, `trend_strength_63_xs`, `downside_vol_63_xs`, `vol_21_xs`, `vol_63_xs`, `vol_ratio_xs`, `amihud_21_xs`, `log_dollar_volume_21_xs`, `volume_shock_xs`, `market_drawdown`, `market_mom_21`, `market_mom_252`, `market_vol_21`, `market_vol_63`, `market_vol_percentile`, `rates_change_63`, `rates_curvature`, `rates_level`, `rates_short`, `rates_slope`

Price, liquidity, volatility, trend and market-regime features are PIT by construction (trailing windows only); the five rates features use the Treasury curve with a one-session lag (ALFRED vintages are `BLOCKED_EXTERNAL_FRED_KEY`).

## Profitability

PIT assurance: HIGH: as-reported SEC vintages, acceptance-time gated.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `gross_profitability` | TTM gross profit / total assets (Novy-Marx 2013); gross profit = GrossProfit, else revenue - cost of revenue | gross_profit or revenue, cost_of_revenue; assets | 2014-04-03 | 53.1% | gross profit is a small-coverage tag; the fallback needs both revenue and cost |
| `roa` | TTM net income / total assets | net_income; assets | 2014-04-03 | 87.2% | end-of-period, not average, assets |
| `roe` | TTM net income / stockholders' equity, equity > 0 | net_income; equity | 2014-04-03 | 82.5% | undefined for non-positive equity |
| `operating_profitability` | TTM operating income / total assets | operating_income; assets | 2014-04-03 | 67.0% | OperatingIncomeLoss is absent for some banks/insurers |
| `cash_profitability` | TTM operating cash flow / total assets | operating_cash_flow; assets | 2014-04-03 | 89.1% | - |
| `gross_margin` | TTM gross profit / TTM revenue | gross_profit or revenue, cost_of_revenue | 2014-04-03 | 51.2% | financials have no gross profit |
| `operating_margin` | TTM operating income / TTM revenue | operating_income; revenue | 2014-04-03 | 62.8% | - |
| `net_margin` | TTM net income / TTM revenue | net_income; revenue | 2014-04-03 | 78.2% | - |
| `cash_flow_margin` | TTM operating cash flow / TTM revenue | operating_cash_flow; revenue | 2014-04-03 | 79.9% | - |
| `ebitda_margin` | (TTM operating income + TTM depreciation & amortisation) / TTM revenue | operating_income, depreciation_amortization; revenue | 2014-04-03 | 43.1% | D&A from the cash-flow statement |
| `asset_turnover` | TTM revenue / total assets | revenue; assets | 2014-04-03 | 80.1% | - |

## Value

PIT assurance: MEDIUM-HIGH: SEC vintages plus PIT shares x unadjusted close; share basis and split restatement add error.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `book_to_market` | stockholders' equity / market capitalisation | equity; PIT shares x close | 2014-04-03 | 86.8% | negative equity gives a negative ratio (kept) |
| `earnings_yield` | TTM net income / market capitalisation | net_income; market cap | 2014-04-03 | 82.5% | - |
| `sales_yield` | TTM revenue / market capitalisation | revenue; market cap | 2014-04-03 | 75.6% | - |
| `fcf_yield` | (TTM operating cash flow - TTM capital expenditure) / market capitalisation | operating_cash_flow, capital_expenditure; market cap | 2014-04-03 | 72.5% | capex tag covers PP&E payments only |
| `ocf_yield` | TTM operating cash flow / market capitalisation | operating_cash_flow; market cap | 2014-04-03 | 84.5% | - |
| `operating_income_to_ev` | TTM operating income / enterprise value; EV = market cap + (long-term + short-term debt) - cash | operating_income, long_term_debt, short_term_debt, cash; market cap | 2014-04-03 | 23.0% | needs both debt legs reported (an absent tag is not read as zero debt) |
| `gross_profit_to_ev` | TTM gross profit / enterprise value | as above | 2014-04-03 | 20.3% | as above |
| `sales_to_ev` | TTM revenue / enterprise value | as above | 2014-04-03 | 28.0% | as above |

## Investment

PIT assurance: HIGH: as-reported SEC vintages; year-ago balances from the vintages known then.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `asset_growth` | total assets / total assets one year earlier - 1 (base > 0) | assets, assets_1y | 2014-04-03 | 90.1% | year-ago balance needs the year-ago comparative or filing |
| `capex_to_assets` | TTM capital expenditure / total assets | capital_expenditure; assets | 2014-04-03 | 77.0% | - |
| `capex_to_revenue` | TTM capital expenditure / TTM revenue | capital_expenditure; revenue | 2014-04-03 | 70.7% | - |
| `capex_growth` | TTM capital expenditure / year-ago TTM - 1 (base > 0) | capital_expenditure | 2014-04-03 | 73.9% | - |
| `inventory_growth` | inventory / inventory one year earlier - 1 (base > 0) | inventory | 2014-04-03 | 52.4% | absent for non-inventory businesses |
| `inventory_to_assets_change` | (inventory - year-ago inventory) / year-ago total assets | inventory, assets_1y | 2014-04-03 | 52.4% | - |
| `working_capital_growth` | change in non-cash working capital [(current assets - cash) - current liabilities] / year-ago assets | current_assets, cash, current_liabilities, assets_1y | 2014-04-03 | 77.1% | unclassified balance sheets have no current items |
| `receivables_growth` | net receivables / year-ago - 1 (base > 0) | accounts_receivable | 2014-04-03 | 55.2% | - |

## Quality

PIT assurance: HIGH: as-reported SEC vintages.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `accruals` | (TTM net income - TTM operating cash flow) / total assets (Sloan 1996) | net_income, operating_cash_flow; assets | 2014-04-03 | 87.0% | balance-sheet accruals variants not built |
| `cash_flow_quality` | TTM operating cash flow / TTM net income, net income > 0 | operating_cash_flow, net_income | 2014-04-03 | 76.6% | undefined for losses |
| `gross_margin_stability` | - standard deviation of TTM gross margin over the last (up to) 8 filings, >= 5 observations | gross_margin history | 2014-04-03 | 26.0% | history is per filing, including amendments |
| `roa_stability` | - standard deviation of TTM ROA over the last (up to) 8 filings, >= 5 observations | roa history | 2014-04-03 | 85.1% | - |
| `cash_conversion` | (TTM operating cash flow - TTM capital expenditure) / TTM net income, net income > 0 | operating_cash_flow, capital_expenditure, net_income | 2014-04-03 | 65.7% | - |

## Leverage

PIT assurance: HIGH: as-reported SEC vintages (both debt legs required).

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `debt_to_assets` | (long-term + short-term debt) / total assets | long_term_debt, short_term_debt; assets | 2014-04-03 | 34.9% | both debt legs must be reported |
| `debt_to_equity` | (long-term + short-term debt) / equity, equity > 0 | as above; equity | 2014-04-03 | 33.1% | - |
| `net_debt_to_assets` | (debt - cash) / total assets | debt legs, cash; assets | 2014-04-03 | 33.8% | - |
| `liabilities_to_assets` | total liabilities / total assets; liabilities = Liabilities, else assets - equity | liabilities or (assets, equity) | 2014-04-03 | 91.6% | the fallback includes non-controlling interest in equity |
| `current_ratio` | current assets / current liabilities | current_assets, current_liabilities | 2014-04-03 | 80.2% | unclassified balance sheets |
| `cash_to_assets` | cash and equivalents / total assets | cash; assets | 2014-04-03 | 88.1% | - |

## Growth

PIT assurance: HIGH: as-reported TTM now against the TTM computed at the year-ago filing.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `revenue_growth` | TTM revenue / year-ago TTM revenue - 1 (base > 0) | revenue TTM now and at the year-ago filing | 2014-04-03 | 76.6% | - |
| `gross_profit_growth` | (TTM gross profit - year-ago TTM) / year-ago total assets | gross_profit; assets_1y | 2014-04-03 | 28.1% | scaled by assets to avoid sign problems |
| `earnings_growth` | (TTM net income - year-ago TTM) / year-ago total assets | net_income; assets_1y | 2014-04-03 | 84.1% | - |
| `operating_income_growth` | (TTM operating income - year-ago TTM) / year-ago total assets | operating_income; assets_1y | 2014-04-03 | 64.5% | - |
| `ocf_growth` | (TTM operating cash flow - year-ago TTM) / year-ago total assets | operating_cash_flow; assets_1y | 2014-04-03 | 86.4% | - |
| `fcf_growth` | (TTM free cash flow - year-ago TTM) / year-ago total assets | operating_cash_flow, capital_expenditure; assets_1y | 2014-04-03 | 73.9% | - |

## Capital Structure

PIT assurance: MEDIUM-HIGH: shares depend on the cover-page/balance-sheet basis and split table (2014+).

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `debt_growth` | (debt - year-ago debt) / year-ago total assets | debt legs now and a year ago; assets_1y | 2014-04-03 | 31.7% | - |
| `equity_issuance_proxy` | ((equity - year-ago equity) - TTM net income) / year-ago assets: equity change not explained by earnings | equity, net_income; assets_1y | 2014-04-03 | 86.5% | also picks up dividends, buybacks, OCI |
| `shares_growth` | split-adjusted shares outstanding / shares one year (365 days) earlier - 1 | PIT shares vintage (cover page, else balance sheet); splits | 2014-04-03 | 84.8% | share basis can differ between the two dates |

## Event

PIT assurance: HIGH: filing acceptance times.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `seasonal_ni_surprise` | (discrete-quarter net income - same quarter a year earlier) / std of the previous 8 such differences (>= 4) | net_income YTD algebra | 2014-04-03 | 85.4% | not analyst-based; a seasonal-difference SUE |
| `filing_lag_days` | days from the latest report's period end to its acceptance | accepted_at, report period | 2014-04-03 | 91.8% | a reporting-behaviour signal |
| `days_since_report` | calendar days since the latest report became usable | available session | 2014-04-03 | 91.8% | - |

## Control

PIT assurance: GATED: withheld unless the security-master PIT gate passes.

| Feature | Formula | Inputs | First valid | Coverage | Known limitation |
|---|---|---|---|---:|---|
| `log_market_cap` | log(PIT shares outstanding x unadjusted close) | PIT shares; close | withheld | withheld | CONTROL - present only if the security-master gate allows size features |
| `industry_rel_roa` | ROA minus the (date, Fama-French 12) mean; groups < 5 names stay missing | roa; ff12 | withheld | withheld | CONTROL - gated; SIC-based industries, not GICS |
| `industry_rel_gross_profitability` | gross profitability minus its (date, FF12) mean | gross_profitability; ff12 | withheld | withheld | CONTROL - gated |
| `industry_rel_book_to_market` | book-to-market minus its (date, FF12) mean | book_to_market; ff12 | withheld | withheld | CONTROL - gated |
| `industry_rel_operating_margin` | operating margin minus its (date, FF12) mean | operating_margin; ff12 | withheld | withheld | CONTROL - gated |
| `industry_rel_asset_growth` | asset growth minus its (date, FF12) mean | asset_growth; ff12 | withheld | withheld | CONTROL - gated |
| `industry_rel_earnings_yield` | earnings yield minus its (date, FF12) mean | earnings_yield; ff12 | withheld | withheld | CONTROL - gated |
