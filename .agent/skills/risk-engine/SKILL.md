---
name: risk-engine
description: Calculates 'Systemic Risk Multiplier' using FRED Macro data.
---

## Instructions

1. Fetch current **10-year Treasury yields** (T10Y2Y) and **CPI** (CPIAUCNS) from the Federal Reserve Economic Data (FRED) API.
2. Compare them against 1-year moving averages to detect trend shifts.
3. Generate a **Macro Dampener** score between **0.5** and **1.5**.
4. If Inflation > 4% or Rates > 5%, reduce "Bullish" predictions by 20%.

## Core Logic

The risk engine uses `src/risk_analysis.py` → `OmniSignalRiskEngine` class.

### Systemic Risk Multiplier (SRM)

```
Base SRM = 1.0

IF yield_curve_inverted (10Y - 2Y < 0):
    SRM += 0.3   # Recession warning

IF inflation_yoy > 4.0%:
    SRM += 0.2   # Inflationary pressure

IF fed_funds_rate > 5.0%:
    SRM += 0.1   # Tight monetary policy

SRM = clamp(SRM, 0.5, 1.6)
```

### Dampening Effect on Predictions

When SRM is applied to a prediction agent:

| SRM Range | Effect |
|---|---|
| 0.5 – 0.9 | Boost bullish signals by up to 10% |
| 1.0 | No adjustment (neutral macro) |
| 1.1 – 1.3 | Dampen bullish predictions by 10-20% |
| 1.3+ | Downgrade "Strong Buy" → "Hold", flag recession risk |

## Integration

```python
from src.risk_analysis import OmniSignalRiskEngine

engine = OmniSignalRiskEngine()
multiplier, stats = engine.get_systemic_risk_multiplier()
# Use multiplier to adjust prediction confidence
```
