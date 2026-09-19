# Replication candidate: regularized PIT characteristic panel

| Item | Assessment |
|---|---|
| Original evidence | GKX; Han–He–Rapach–Zhou regularized Fama–MacBeth; Avramov–Cheng–Metzker economic restrictions; broad characteristic literature |
| Original data | CRSP/Compustat-style US panels with dozens to hundreds of lagged firm characteristics and macro states |
| Original target | Next-month raw/excess cross-sectional return; some designs standardize or rank targets |
| Original model | Ridge/elastic net or regularized Fama–MacBeth, with boosted-tree and MLP comparisons |
| Original validation | Long temporal OOS splits, portfolio sorts, and characteristic importance; cost treatment varies and is often incomplete |
| Original result | Regularization stabilizes broad panels; nonlinear trees help on interactions, but deep models do not dominate universally |
| Original compute | Generally unreported; materially below deep distribution/GNN studies for an Omni-sized panel |
| What we have | PIT price/volume/macro, 452k rows, 26 clean frozen base features, eight folds, top-k dropout and cost sweep |
| What we lack | As-reported statement vintages, PIT shares/market cap, stable CIK identity and dated industry |
| Feasible substitute | SEC XBRL first-reported facts + CIK/SIC/size master; 60–120 documented features; ridge/elastic net and one boosted tree |
| MacBook plan | Entire data build and linear baseline; estimated 10–40 min linear and 1–3 h 10-seed sklearn GB after materialization |
| Kaggle plan | Optional GPU boosting only; independent seeds, estimated 20–90 min |
| Data preparation time | 3–8 engineering days for first audited numeric release, then 1–4 h per full rebuild |
| Implementation complexity | MEDIUM; data semantics dominate model code |
| Leakage risk | Restatements, form amendments, fiscal-period contexts, ticker reuse, after-close filing acceptance and cross-sectional preprocessing |
| Licensing risk | SEC/FRED inputs open subject to terms; exact CRSP comparison unavailable; formulas/summaries are original implementation |
| Recommendation | **REPLICATE/ADAPT FIRST** after EXP-010A/B |

This is the preferred serious research cycle because it changes the information
set while retaining cheap, auditable models and the already validated turnover
control.
