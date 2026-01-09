# MASFIN: A Multi-Agent System for Decomposed Financial Reasoning and Forecasting

**Authors:**  
Marc S. Montalvo — Rochester Institute of Technology  
Dr. Hamed Yaghoobian — Muhlenberg College  

Research presented in person at the NeurIPS 2025 Workshop on Generative AI in Finance, San Diego, CA  
Paper: https://arxiv.org/abs/2512.21878

---

### **Overview**
MASFIN (*Multi-Agent System for Financial Forecasting*) is a modular multi-agent framework that leverages AI (LLM - GPT-4.1 nano) to make investment portfolio decisions with structured financial metrics and unstructured news sentiment under explicit bias-mitigation protocols. The system was implemented using **CrewAI** and evaluated over an **eight-week live-market period**, generating weekly portfolios of 15–30 equities optimized for short-term returns.

In its evaluation, MASFIN achieved a **7.33 % cumulative return**, outperforming the **S&P 500**, **NASDAQ-100**, and **Dow Jones** in six of eight weeks, with favorable risk-adjusted performance despite higher volatility.

---

### **System Architecture**
MASFIN operates as a **five-stage sequential pipeline**, with 3–5 LLM-based agents per stage. Each stage passes structured outputs to the next, ensuring transparency, error control, and reproducibility.

1. **Postmortem Crew** – Analyzes delisted or at-risk firms to detect failure patterns and mitigate survivorship bias.  
2. **Screening Crew** – Filters the market to 50–100 candidate tickers using sentiment, trends, and rule-based criteria.  
3. **Analysis Crew** – Evaluates quantitative indicators (21-day and 5-day returns, volatility, Sharpe/Sortino ratios, drawdown, beta, alpha, z-scores, volume trends, among others). 
4. **Timing Crew** – Assesses short-term entry timing using Sortino ratio, return z-score, regression slope, among others.  
5. **Portfolio Crew** – Allocates weights across 15–30 equities, balancing return and risk while ensuring diversification and bias control.

Each crew includes a **Summary Agent** to consolidate outputs and enable **human-in-the-loop (HITL)** validation, reducing hallucinations and reinforcing interpretability.

---

### **Methodology**
- **Data Sources:** Yahoo Finance (market data) and Finnhub API (news sentiment).  
- **Evaluation Period:** June – August 2025.
- **Performance Metrics** See Calculations.md   
- **Benchmark Comparison:** S&P 500 (SPY), NASDAQ-100 (QQQ), and Dow Jones (DIA).  
- **Evaluation Cycle:** weekly rebalancing and performance review.

---

### **Results**
| Metric | MASFIN | NASDAQ-100 | S&P 500 | Dow Jones |
|:--|:--:|:--:|:--:|:--:|
| **Cumulative Return** | 7.33 % | 5.36 % | 4.92 % | 4.11 % |
| **Standard Deviation (Volatility)** | 2.61% | 2.18% | 1.78% | 2.03% |
| **Correlation to MASFIN** | 1.0 | 0.95 | 0.97 | 0.88 |

---

### **How to Use**
- **Install dependencies** listed in `requirements.txt`  
- **Open** `MASFIN_System_Template.ipynb` in Jupyter Notebook
- **Connect** Finnhub API + LLM
- **Run each crew** in order:  
  - Postmortem  
  - Screening  
  - Analysis  
  - Timing  
  - Portfolio  
- **Use human-in-the-loop (HITL)** review between crews by passing each summary output to the next stage  
- **Review final outputs:** Buy, Sell, or Hold recommendations from the Portfolio Crew  
- **Compare performance:** open `Calculations.ipynb` to calculate metrics and place into Analysis Crew, Timing Crew, and Portfolio Crew for next week (week beginning, end, among others) & can evaluate results against market indices
- **Repeat weekly** with updated data to track performance over time

---

### **Reproducibility**
- **Language & Platform:** Python 3.13 on Windows 11  
- **Framework:** CrewAI (v0.30.2)  
- **Notebook Environment:** Jupyter Notebook  
- **Dependencies:** listed in `requirements.txt`  
- **Evaluation Notebooks:** `MASFIN_System_Template.ipynb` and supporting analysis notebooks  
- **Data Sources:** Yahoo Finance and Finnhub APIs (June – August 2025)

All scripts and notebooks are fully reproducible and publicly available.

---

### **Limitations and Future Work**
While MASFIN achieves strong short-term predictive performance, it does not yet include a learning mechanism or statistical inference tools such as confidence intervals or hypothesis testing. Extending evaluation periods and comparing MASFIN to other AI-based financial systems will further contextualize its performance. Future versions aim to integrate adaptive learning modules and automated calibration of agent parameters.

---

### **Citation**
If you use or reference MASFIN, please cite:

> Montalvo, M. S., & Yaghoobian, H. (2025). *MASFIN: A Multi-Agent System for Decomposed Financial Reasoning and Forecasting.*  
> Proceedings of the NeurIPS 2025 Workshop on Generative AI in Finance.  
> [https://github.com/mmontalvo9/MASFIN](https://github.com/mmontalvo9/MASFIN)
