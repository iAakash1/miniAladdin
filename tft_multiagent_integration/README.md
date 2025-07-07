# TFT Multi-Agent Integration

This directory contains a **fully-contained Python implementation** of the crews that appear in your `Research_Week_3_Simulation.ipynb`, but re-organised into standard `.py` files and linked to the new **Temporal Fusion Transformer (TFT)** forecaster.

Your student can run everything **without touching notebooks** and **without knowing the underlying RNN/NN details**—all ML logic is wrapped behind easy-to-use CrewAI tools.

---
## 1. Directory Contents

```
tft_multiagent_integration/
├── __init__.py            # Makes the directory a package
├── agents.py              # All CrewAI agent definitions (post-mortem + analysis)
├── tasks.py               # Lightweight task definitions
├── crews.py               # Convenience builders that glue agents & tasks together
├── run_full_pipeline.py   # 🚀 Entry-point script – runs both crews sequentially
└── README.md              # (this file) step-by-step guide
```

## 2. Quick-Start (10 min)

1. **Create & activate a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # on Windows use .venv\Scripts\activate
   ```

2. **Install all requirements** (same list used in the notebook):

   ```bash
   pip install -r ../../requirements.txt  # one level up from this folder
   ```

   If you only want the minimum needed:

   ```bash
   pip install crewai yfinance ta darts[torch] pytorch-forecasting pandas numpy matplotlib
   ```

3. **(Optional) Train the TFT model** – this is **only one line** thanks to the helper tool:

   ```python
   >>> from crewai_tft_integration import train_tft_model
   >>> train_tft_model("2024-01-01")  # uses 2+ yrs of history prior to evaluation start
   ```

   • Training may take ~5-8 min on CPU for the demo ticker set.
   • Skip the step if you just want to see the pipeline – a fallback technical-analysis model will load automatically.

4. **Run the pipeline**:

   ```bash
   python -m tft_multiagent_integration.run_full_pipeline
   ```

   You should see console logs as each crew and task execute. Results are printed to stdout; adapt as needed.

---
## 3. How It Works (at a glance)

1. **agents.py** – defines two helper functions:
   • `get_postmortem_agents()` – five qualitative agents copied from the notebook.
   • `get_analysis_agents()` – quantitative agents **plus** the TFT-powered forecasting analyst built via `create_enhanced_forecasting_analyst()`.

2. **tasks.py** – lightweight `Task` objects that reference those agents.  They are intentionally slim; expand their descriptions any time.

3. **crews.py** – wraps agents & tasks into `Crew` objects using `Process.sequential` (same order as the notebook).

4. **run_full_pipeline.py** – orchestrates crews sequentially:
   • Runs the Post-Mortem crew on your (placeholder) headlines.
   • Runs the Analysis crew which internally calls the TFT tools for price-direction prediction.

   All heavy lifting (feature engineering, model training, inference) lives in **`tft_forecaster.py`** and **`crewai_tft_integration.py`** at repo-root level—already imported by the enhanced forecasting agent.

---
## 4. Customising & Testing

• **Replace `headlines_placeholder`** in `run_full_pipeline.py` with actual news text or pass it programmatically.

• **Ticker universe** – the TFT global model is trained across a curated S&P-500 subset.  Update tickers via:

```python
from crewai_tft_integration import train_tft_model
train_tft_model(evaluation_start_date="2024-01-01", training_tickers="AAPL,MSFT,NVDA,TSLA")
```

• **Inspect model status** at any time:

```python
from crewai_tft_integration import tft_model_status
print(tft_model_status())
```

• **Quick predictions** for a single ticker:

```python
from crewai_tft_integration import tft_price_direction
print(tft_price_direction("AAPL"))
```

---
## 5. Troubleshooting Checklist

1. **Missing package** error → run `pip install <package>`.
2. **No module named 'ta'** → ensure `ta` was installed (`pip install ta`).
3. **CUDA warnings** → ignore; model defaults to CPU unless GPU present.
4. **Internet fetch issues** (yfinance / Finnhub) → check firewall or proxy.

---
## 6. Next Steps for Your Student

1. Read the **first ~50 lines of `tft_forecaster.py`** to see all engineered features (there's no deep ML required).
2. Treat the TFT forecaster **like any other CrewAI tool** – just call `tft_price_direction()` inside your agent reasoning.
3. Experiment with adding **PatchTST** and **Informer** models next, following the same pattern.

Happy researching! 🚀 