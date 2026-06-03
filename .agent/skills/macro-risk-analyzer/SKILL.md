---
name: macro-risk-analyzer
description: Fetches real-time macro data (Treasury yields, CPI) from FRED to assess systemic risk.
---

## Instructions

1. Use the `scripts/fetch_macro.py` script to pull 10-year Treasury yields and Inflation rates from the Federal Reserve (FRED) API.
2. Calculate a **Systemic Risk Multiplier (SRM)** based on current interest rate trends and inflation data.
3. Feed this SRM into the main stock prediction model to adjust "bullishness" levels.

## Risk Multiplier Logic

| Condition | Adjustment |
|---|---|
| Yield Curve Inverted (T10Y2Y < 0) | +0.3 to multiplier |
| Inflation > 4% (YoY CPI) | +0.2 to multiplier |
| Fed Funds Rate > 5% | +0.1 to multiplier |
| All conditions normal | Multiplier stays at 1.0 |

**Output Range:** 0.5 (extremely low risk) to 1.6 (extreme systemic risk)

## Usage

```bash
# Run the macro fetch script
python scripts/fetch_macro.py

# Output: JSON with risk_multiplier, yield_spread, inflation_rate, status
```

## Dependencies

- `fredapi` — Python wrapper for the FRED API
- `FRED_API_KEY` environment variable must be set in `.env`
