# EXP-009 candidate: fundamental characteristics

Status: blocked on historical-as-reported provenance for official selection;
existing research-only features are implemented; not run.

## Literature-supported candidates

| Feature | Formula | Local support | Risk |
|---|---|---|---|
| Gross margin/profitability | gross profit / sales | Yes | Later restatement may overwrite history |
| ROA / ROE | net income / assets or equity | Yes | Negative/small denominators; restatement |
| Accruals | (net income - operating cash flow) / assets | Yes | Statement alignment/restatement |
| Asset growth | YoY change in assets / prior assets | Yes | Four-quarter continuity |
| Sales growth | YoY change in sales / prior sales | Yes | Same |
| Net issuance | YoY change in shares outstanding | Yes | Split/share-definition consistency |
| Leverage/current ratio | liabilities/equity; current assets/current liabilities | Yes | Financial-sector comparability |
| Book-to-market | book equity / PIT market cap | Partial | PIT shares/security master missing |
| Earnings/FCF yield | earnings or FCF / PIT enterprise/equity value | Partial | FCF definition and market-cap timing |
| Investment/quality composites | preregistered component combination | Partial | Weight selection/multiple testing |

`src/quant/features/fundamentals.py` already implements ten of these behind an
announcement-date gate. Coverage is about 53% of panel rows after the calendar
starts in 2020. The gate prevents period-end look-ahead but cannot recover the
originally filed version; restatement risk is unquantified.

## Candidate path

First build a SEC accession/acceptance-time fact store with filing versions.
Then reproduce a small canonical set (gross profitability, accruals, asset
growth, net issuance, book-to-market) using formulas frozen before evaluation.
Compare base versus base + that entire canonical set. Do not select the
best-looking ratio after fold results.

The EXP-005 earnings/fundamental arm materially reduced IC (0.0124 versus
0.0290). Until data vintaging changes the information set, rerunning the same
features is not a new hypothesis.
