# MASFIN Calculations: Full Reference

This document provides a detailed explanation of the financial and statistical calculations used by the **MASFIN** (Multi-Agent System for Financial Forecasting) project.  
While the paper version (Table 2) presents a condensed overview, this page serves as the **complete reference** for calculation details and standardization

---

## 1. Return-Based Metrics

**21-Day Return**  
Measures medium-term performance over roughly one trading month:  
Return_21 = (Close_t / Close_{t-21}) - 1
- Close_t = stock closing price on day *t*  
- Close_{t-21} = stock closing price 21 trading days earlier  

**5-Day Return**  
Captures short-term performance over one trading week:  
Return_5 = (Close_t / Close_{t-5}) - 1
- Close_t = stock closing price on day *t*  
- Close_{t-5} = stock closing price 5 trading days earlier  

**Percentage Change**  
Generic formula for start-to-end comparison:  
Percent Change = (End Price - Start Price) / Start Price * 100
- End Price = final observed price over the period  
- Start Price = initial observed price  

**Momentum**  
Absolute price movement over 21 days:  
Momentum_21 = Close_t - Close_{t-21}
- Close_t = current closing price  
- Close_{t-21} = closing price 21 trading days earlier  

**Global Mean Benchmarking (Cross-Sectional)**  
Used to compare each ticker against the average of all tickers in the sample:  
Global Mean_m = (1/N) * Σ Metric_{i,m}
- N = number of tickers in the sample  
- Metric_{i,m} = value of metric *m* (e.g., Sharpe, volatility) for ticker *i*

---

## 2. Risk and Risk-Adjusted Metrics

**Volatility (Annualized)**  
Standard deviation of daily returns, scaled to trading year:  
σ = StdDev(daily returns) * sqrt(252)
- σ = annualized volatility  
- StdDev(daily returns) = standard deviation of daily returns  
- 252 = typical number of trading days in a year

**Max Drawdown**  
Largest observed loss from a peak to a trough:  
MaxDD = min( Close_t / max(Close_{≤t}) - 1 )
- Close_t = stock closing price at time *t*  
- max(Close_{≤t}) = maximum closing price observed up to time *t*

**Mean Return (Daily)**  
μ = (1/N) * Σ R_t
- μ = mean daily return  
- R_t = return on day *t*  
- N = total number of trading days  

**Sharpe Ratio**  
Risk-adjusted return assuming risk-free rate = 0:  
Sharpe = (μ * 252) / (σ * sqrt(252))
- μ = mean daily return  
- σ = standard deviation of daily returns

**Downside Deviation**  
Focuses only on harmful volatility (negative returns):  
σ_d = sqrt( (1/N) * Σ min(R_t, 0)^2 )
- σ_d = downside deviation  
- R_t = return on day *t*  
- N = number of trading days

**Sortino Ratio**  
Rewards upside while penalizing only downside risk:  
Sortino = μ / σ_d
- μ = mean daily return  
- σ_d = downside deviation

**Beta (OLS Slope)**  
Sensitivity of stock returns to market returns:  
Stock Return_t = β * Market Return_t + ε_t
- β = stock’s sensitivity to market movements  
- ε_t = error term (unexplained variance)

**Alpha (OLS Intercept)**  
Excess return unexplained by market exposure:  
Alpha = Intercept from regression of Stock Return on Market Return
- Alpha = regression intercept, represents return not explained by the market 

---

## 3. Technical Indicators

**RSI-14 (Relative Strength Index)**  
Momentum oscillator based on average gains vs losses over 14 days:  
RSI_14 = 100 - (100 / (1 + RS)), where RS = Avg Gain_14 / Avg Loss_14
- Avg Gain_14 = average daily gain over past 14 days  
- Avg Loss_14 = average daily loss over past 14 days

**Recent Z-Score (Return)**  
Standardized deviation of latest return vs past 5-day average:  
Z = (Return_t - μ_{t-5:t}) / σ_{t-5:t}
- Return_t = return at time *t*  
- μ_{t-5:t} = mean return over past 5 days  
- σ_{t-5:t} = standard deviation of past 5 days’ returns

**5-Day Volume Trend**  
Direction of trading activity across the last week:  
Trend_vol = (1/5) * Σ (Volume_{t-i} - Volume_{t-i-1})
- Volume_{t-i} = trading volume on day *t-i*  
- Trend_vol = average daily change in volume across 5 days

**Residual Volume**  
Difference between current volume and recent 5-day average:  
Residual Volume = Volume_t - MA_{5,volume}(t)
- Volume_t = trading volume on day *t*  
- MA_{5,volume}(t) = 5-day moving average of trading volume

**Price Relative to 5-Day Moving Average**  
Captures short-term deviation from trend:  
Relative MA = (Close_t - MA_5(t)) / MA_5(t)
- Close_t = closing price on day *t*  
- MA_5(t) = 5-day moving average of closing price

---

## Why These Metrics Matter
- **Consistency**: All metrics are computed exactly as defined here, ensuring reproducibility.  
- **Bias Reduction**: Using standard definitions avoids introducing custom rules that could bias results.  
- **Multi-Agent Use**: These metrics are referenced by multiple MASFIN crews (Analysis, Timing, Portfolio) for screening, forecasting, and portfolio construction.  
- **Transparency**: Public formulas with references ensure clarity for peer review, replication, and future extensions.  

---

## References

[Return Definition – Investopedia](https://www.investopedia.com/terms/r/return.asp)  
[Percentage Change – Investopedia](https://www.investopedia.com/terms/p/percentage-change.asp)  
[Cross-Sectional Analysis – Investopedia](https://www.investopedia.com/terms/c/cross_sectional_analysis.asp)  
[Volatility – Investopedia](https://www.investopedia.com/terms/v/volatility.asp)  
[Maximum Drawdown – Investopedia](https://www.investopedia.com/terms/m/maximum-drawdown-mdd.asp)  
[Sharpe Ratio – Sharpe (1966), JSTOR](https://www.jstor.org/stable/2351741)  
[Sortino Ratio, Downside Deviation – Investopedia](https://www.investopedia.com/terms/s/sortinoratio.asp)  
[Beta – Investopedia](https://www.investopedia.com/terms/b/beta.asp)  
[Alpha – Investopedia](https://www.investopedia.com/terms/a/alpha.asp)  
[RSI – Investopedia](https://www.investopedia.com/terms/r/rsi.asp)  
[Standard Score (Recent Z-score) – Wikipedia](https://en.wikipedia.org/wiki/Standard_score)  
[Volume – Investopedia](https://www.investopedia.com/terms/v/volume.asp)  
[Moving Average – Investopedia](https://www.investopedia.com/terms/m/movingaverage.asp)  
