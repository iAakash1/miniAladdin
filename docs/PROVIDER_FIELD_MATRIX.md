# Provider field matrix

**Generated** by `scripts/generate_provider_matrix.py` from
`src/providers/statements.py`. Do not edit by hand — regenerate it.

Every row is a vendor-native key that this product has established a
meaning for. A key absent from this table is a key the adapter does
not surface, and that is deliberate: a number whose unit, basis and
period nobody has established is a numeral, not a fact.

`Scale` is the multiplier applied to reach `Unit`. Finnhub reports
company-level totals in millions and every other figure here is in
units; the factor is measured against yfinance across four securities,
not assumed.

`Period` of *not stated* means the vendor supplied none. Those facts
are never grouped with a dated one — silence is not a wildcard.

| Field | Provider | Vendor key | Raw | Normalized | API | UI | Unit | Basis | Period | Scale |
|---|---|---|---|---|---|---|---|---|---|---|
| Book value | finnhub | `bookValuePerShareAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Book value | finnhub | `bookValuePerShareQuarterly` | yes | yes | yes | yes | currency/share | per share | MRQ | ×1 |
| Dividend paid | finnhub | `dividendPerShareAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Dividend paid | finnhub | `dividendPerShareTTM` | yes | yes | yes | yes | currency/share | per share | TTM | ×1 |
| EBITDA | finnhub | `ebitdPerShareAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| EBITDA | finnhub | `ebitdPerShareTTM` | yes | yes | yes | yes | currency/share | per share | TTM | ×1 |
| Earnings per share | finnhub | `epsAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Earnings per share | finnhub | `epsTTM` | yes | yes | yes | yes | currency/share | per share | TTM | ×1 |
| Earnings per share, excluding extraordinary items | finnhub | `epsExclExtraItemsAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Earnings per share, excluding extraordinary items | finnhub | `epsExclExtraItemsTTM` | yes | yes | yes | yes | currency/share | per share | TTM | ×1 |
| Earnings per share, normalised | finnhub | `epsNormalizedAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Enterprise value | finnhub | `enterpriseValue` | yes | yes | yes | yes | currency | total | not stated | ×1,000,000 |
| Market capitalisation | finnhub | `marketCapitalization` | yes | yes | yes | yes | currency | total | not stated | ×1,000,000 |
| Operating cash flow | finnhub | `cashFlowPerShareAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Operating cash flow | finnhub | `cashFlowPerShareQuarterly` | yes | yes | yes | yes | currency/share | per share | MRQ | ×1 |
| Operating cash flow | finnhub | `cashFlowPerShareTTM` | yes | yes | yes | yes | currency/share | per share | TTM | ×1 |
| Revenue | finnhub | `revenuePerShareAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Revenue | finnhub | `revenuePerShareTTM` | yes | yes | yes | yes | currency/share | per share | TTM | ×1 |
| Tangible book value | finnhub | `tangibleBookValuePerShareAnnual` | yes | yes | yes | yes | currency/share | per share | FY | ×1 |
| Tangible book value | finnhub | `tangibleBookValuePerShareQuarterly` | yes | yes | yes | yes | currency/share | per share | MRQ | ×1 |
| Book value | yfinance | `book_value` | yes | yes | yes | yes | currency/share | per share | not stated | ×1 |
| Cash and equivalents | yfinance | `total_cash` | yes | yes | yes | yes | currency | total | not stated | ×1 |
| EBITDA | yfinance | `ebitda` | yes | yes | yes | yes | currency | total | not stated | ×1 |
| Enterprise value | yfinance | `enterprise_value` | yes | yes | yes | yes | currency | total | not stated | ×1 |
| Free cash flow | yfinance | `free_cash_flow` | yes | yes | yes | yes | currency | total | not stated | ×1 |
| Operating cash flow | yfinance | `operating_cash_flow` | yes | yes | yes | yes | currency | total | not stated | ×1 |
| Revenue | yfinance | `total_revenue` | yes | yes | yes | yes | currency | total | not stated | ×1 |
| Total debt | yfinance | `total_debt` | yes | yes | yes | yes | currency | total | not stated | ×1 |

**Coverage.** 20 Finnhub keys and 8 yfinance keys are mapped. Finnhub returns 131 keys per request; the unmapped remainder is predominantly ratios and price-return statistics, which belong on the ratio surface rather than beside statement figures.
