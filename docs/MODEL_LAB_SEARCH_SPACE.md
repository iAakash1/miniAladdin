# MODEL-LAB-001 declared search space

The executable registry is `src/quant/model_lab/search_space.py`; this document
explains it. Exact grids are code, versioned before screening results.

| Family | Models | Route | Current state |
|---|---|---|---|
| Regularised linear | Ridge, Lasso, ElasticNet | Mac CPU | executable |
| Robust linear | Huber, SGD-Huber | Mac CPU | executable |
| Dimension reduced | PCA+Ridge, PLS | Mac CPU | executable; transform fit per split |
| Bagging | Random Forest, ExtraTrees | Mac CPU | executable |
| Histogram boosting | sklearn HistGradientBoosting | Mac CPU | executable |
| GPU boosting | XGBoost, LightGBM, CatBoost | Kaggle GPU | dependency/export required |
| Neural | modest MLP | Kaggle GPU | PyTorch dependency required; seeds 0–9 |
| Tabular attention | one FT-Transformer | Kaggle GPU | blocked until implementation/licence review after classical families |
| Additive | Explainable Boosting Machine | Mac CPU | optional dependency absent |
| Robust/quantile | Huber is the primary robust family | Mac CPU | executable; quantile variant deferred |
| Ranking | date-query LambdaMART v2 | Kaggle GPU | blocked until a materially new specification is frozen |
| Ensembles | equal family-rank average | post-outer | OOF only |
| Stacking | Ridge meta-model | post-outer | base OOF predictions only |

## Budgets

- Smoke: outer fold 0, first two configurations, seed 0.
- Screening: every declared configuration, every outer fold, seed 0.
- Robustness: only configurations that satisfy the predeclared eligibility
  inputs; stochastic models use all seeds 0–9.
- Ensembles: after individual OOF prediction sets exist; no outer-fold weight
  optimisation.

No portfolio, target, cadence, dropout or transaction-cost search is part of
this campaign.
