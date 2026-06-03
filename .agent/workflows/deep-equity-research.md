---
description: Deep equity research workflow combining macro risk, technical analysis, and live sentiment
---

# Aladdin Deep Equity Research

**Command:** `/research [TICKER]`

Performs a comprehensive, multi-factor research analysis on a given equity ticker by orchestrating macro-economic risk assessment, technical analysis, and live sentiment scraping into a unified OmniSignal report.

---

## Workflow Steps

### Step 1: Macro Risk Assessment
Run the `macro-risk-analyzer` skill to get the current economic environment.

```bash
// turbo
python scripts/fetch_macro.py
```

Parse the JSON output to extract:
- Systemic Risk Multiplier (SRM)
- Yield curve status (normal / inverted)
- Current inflation rate
- Macro environment flag (STABLE / ELEVATED / CRITICAL)

### Step 2: Technical Analysis
Execute MASFIN agents to perform technical analysis on `[TICKER]`.

```python
from src.prediction_agent import RiskAwarePredictionAgent

agent = RiskAwarePredictionAgent(ticker="[TICKER]")
prediction = agent.predict(risk_multiplier=srm_from_step_1)
```

This returns risk-adjusted price targets, Sharpe/Sortino ratios, and a dampened recommendation signal.

### Step 3: Live Sentiment Analysis
Use the Browser Agent to scrape the last 3-5 news headlines for sentiment.

1. Navigate to `https://finance.yahoo.com/quote/[TICKER]/`
2. Extract the top 3 headlines from the news section
3. Score each headline as Bullish / Bearish / Neutral
4. Calculate an aggregate sentiment score

Alternatively, run the programmatic sentiment analyzer:

```python
from src.sentiment_edge import SentimentAnalyzer

analyzer = SentimentAnalyzer()
sentiment = analyzer.analyze_ticker("[TICKER]")
```

### Step 4: OmniSignal Report Generation
Synthesize Macro + Technical + Sentiment into an OmniSignal report.

```python
from src.report_generator import OmniSignalReportGenerator

generator = OmniSignalReportGenerator()
report = generator.generate(
    ticker="[TICKER]",
    macro_data=macro_from_step_1,
    prediction=prediction_from_step_2,
    sentiment=sentiment_from_step_3
)
```

The report is saved to `research_vault/[TICKER]_omnisignal_[DATE].md`.

---

## Output

A Markdown report in `research_vault/` containing:
- **Header**: Ticker, date, analyst (OmniSignal v1)
- **Macro Environment**: SRM, yield curve, inflation, overall economy status
- **Technical Analysis**: Price targets, key ratios, momentum indicators
- **Sentiment Edge**: Headlines, sentiment scores, regulatory risk flags
- **OmniSignal Verdict**: Final composite recommendation with confidence level
