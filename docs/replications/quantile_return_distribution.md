# Replication candidate: return-distribution quantile neural network

| Item | Assessment |
|---|---|
| Original paper | [Barunik, Hronec & Tobek, *Forecasting Stock Return Distributions Around the Globe*](https://arxiv.org/abs/2408.07497), revised 2025 preprint |
| Original data | CRSP/Compustat/IBES for the US plus LSEG DataStream/Worldscope internationally; 176 stock characteristics and 18 market/volatility inputs, 194 total |
| Original target | 37 conditional quantiles of next 22-day raw return, via standardized-return and market-volatility subnetworks |
| Original model | Two-stage quantile MLP with pinball loss and quantile-to-density/moment reconstruction; annual expanding retraining |
| Original validation | 1973–1994 initial train/validation; annual OOS forecasts 1995–2018 for US/international samples |
| Original portfolio/result | Monthly equal-weight decile long-short portfolios; central quantiles/derived mean are strongest. The paper contains no transaction-cost or turnover analysis |
| Original compute | Official MIT repo: 16-core CPU, RTX 4090 24 GB, 128 GB RAM; >2 months full workflow, ~4 days minimum example |
| What we have | 21-session target, price/volume/macro, PIT aggregate analyst data, cost engine and 452k-row panel |
| What we lack | Broad PIT fundamentals, international panel, licensed source histories and 194 matched features |
| Feasible substitute | Nine quantiles on the eventual US PIT panel, one fixed small MLP, compared with direct mean/rank baselines |
| MacBook plan | Possible reduced run, estimated 10–30 h per seed; not recommended |
| Kaggle plan | One seed per T4, estimated 3–10 h per seed; session risk and ten-seed cost remain high |
| Data preparation time | Same SEC/security-master build as EXP-011 plus distribution calibration work; at least 1–2 additional weeks |
| Implementation complexity | HIGH |
| Leakage risk | Cross-sectional normalization, expanding-window tuning, quantile crossing and overlapping 22-day labels |
| Licensing risk | Code MIT; full WRDS/LSEG inputs omitted and licensed |
| Recommendation | **DEFER** until a rich numeric panel first proves stable mean/rank signal net of costs |

Distributional prediction is scientifically interesting, but it does not solve
OmniSignal's current information deficit, and the source paper does not show
that the added compute survives implementation costs.
