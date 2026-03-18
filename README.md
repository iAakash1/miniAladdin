# OmniSignal: Agentic Multi-Factor Risk & Prediction Engine 📊

**OmniSignal** is a systemic-risk-aware prediction engine that integrates **macro-economic risk signals** from the Federal Reserve, **live news sentiment**, and **technical analysis** into a unified research workflow. Instead of analyzing stocks in isolation, OmniSignal provides a holistic view of market conditions and individual equity performance.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│                  OmniSignal Pipeline                 │
├──────────────┬──────────────┬────────────────────────┤
│  FRED API    │  yfinance    │  Yahoo Finance RSS     │
│  (Macro)     │  (Technicals)│  (Sentiment)           │
├──────────────┴──────────────┴────────────────────────┤
│            AsyncDataPipeline (concurrent)            │
├──────────────┬──────────────┬────────────────────────┤
│ Risk Engine  │  Prediction  │  Sentiment             │
│ (SRM calc)   │  Agent       │  Analyzer              │
├──────────────┴──────────────┴────────────────────────┤
│              OmniSignal Report Generator             │
│              → research_vault/TICKER_report.md       │
└──────────────────────────────────────────────────────┘
```

### Systemic Risk Multiplier (SRM)

| Condition | Adjustment | Effect |
|---|---|---|
| Yield Curve Inverted (10Y < 2Y) | +0.3 | Recession warning |
| Inflation > 4% YoY | +0.2 | Dampened bullish signals |
| Fed Funds Rate > 5% | +0.1 | Tighter conditions |
| SRM > 1.3 | — | Strong Buy → Hold |

---

## 📂 Project Structure

```
├── .agent/
│   ├── skills/
│   │   ├── macro-risk-analyzer/   # FRED macro data skill
│   │   └── risk-engine/           # SRM calculation skill
│   └── workflows/
│       └── deep-equity-research.md  # /research workflow
├── src/
│   ├── models.py              # Pydantic data models
│   ├── risk_analysis.py       # FRED-based Risk Engine
│   ├── prediction_agent.py    # Risk-aware technical analysis
│   ├── sentiment_edge.py      # Headline sentiment scoring
│   ├── data_pipeline.py       # Async concurrent pipeline
│   └── report_generator.py    # Markdown report output
├── scripts/
│   └── fetch_macro.py         # CLI macro data fetcher
├── tests/                     # Pytest suite (80%+ coverage)
├── research_vault/            # Generated OmniSignal reports
├── MASFIN_System_Template.ipynb  # Original MASFIN notebook
└── Calculations.md            # Financial metric formulas
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Keys

```bash
cp .env.example .env
# Edit .env and add your FRED API key
# Get one free at: https://fred.stlouisfed.org/docs/api/api_key.html
```

### 3. Check Macro Environment

```bash
python scripts/fetch_macro.py
```

### 4. Run Tests

```bash
python -m pytest tests/ -v --tb=short --cov=src
```

### 5. Use the Research Workflow

In the Antigravity agent, run:
```
/research NVDA
```

---

## 🧠 Key Components

### Risk Engine (`src/risk_analysis.py`)
Connects to the Federal Reserve FRED API to pull Treasury yield spreads, CPI inflation data, and the Federal Funds Rate. Computes a Systemic Risk Multiplier (0.5–1.6) that adjusts prediction confidence.

### Prediction Agent (`src/prediction_agent.py`)
Computes RSI-14, Sharpe/Sortino ratios, volatility, momentum, and drawdown. Applies the SRM dampening: multiplier > 1.3 shifts "Strong Buy" down to "Hold".

### Sentiment Edge (`src/sentiment_edge.py`)
Fetches Yahoo Finance RSS headlines and scores them with a keyword-based sentiment engine. Aggregates into Bullish/Bearish/Neutral with a -1 to +1 composite score.

### Async Pipeline (`src/data_pipeline.py`)
Orchestrates concurrent data fetching from all three sources and synthesizes the final OmniSignal verdict with confidence scoring.

---

## 🚀 Deployment (Vercel)

### Local Development

**1. Start the API server:**
```bash
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
```

**2. Start the dashboard:**
```bash
cd dashboard && npm install && npm run dev
```

**3. Open** `http://localhost:3000` — the dashboard proxies `/api/*` to `localhost:8000`.

### Deploy to Vercel

**1. Push to GitHub:**
```bash
git add .
git commit -m "feat: Aladdin-style risk engine with Vercel support"
git push origin main
```

**2. Connect to Vercel:**
- Import your GitHub repo at [vercel.com/new](https://vercel.com/new)
- Vercel auto-detects the `vercel.json` configuration

**3. Add Environment Variables** in Vercel Dashboard → Settings → Environment Variables:

| Variable | Value |
|---|---|
| `FRED_API_KEY` | `6e050ad2ed98fb11706fb33f7ae2b279` |

### API Endpoints

| Endpoint | Method | Description | Speed |
|---|---|---|---|
| `/api/health` | GET | Health check | <1s |
| `/api/macro` | GET | SRM + macro indicators | ~2s |
| `/api/research/{ticker}` | GET | Full OmniSignal pipeline | ~5s |
| `/api/research/{ticker}?fast=true` | GET | Fast mode (no sentiment) | ~3s |

---

---

## 🔬 Technology Stack

- **Backend:** FastAPI + Python 3.10+
- **Frontend:** Next.js 16 + React 19 + Tailwind CSS
- **Data Sources:** FRED API, Yahoo Finance, yfinance
- **Deployment:** Vercel (serverless)
- **Testing:** Pytest with 80%+ coverage

---

## 📜 License

MIT License - See LICENSE file for details

---

*OmniSignal is for research and educational purposes only. Not financial advice.*

