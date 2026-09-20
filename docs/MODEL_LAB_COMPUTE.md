# Model Lab compute routing

## Mac M4 Pro

Ridge, Lasso, ElasticNet, Huber, SGD-Huber, PCA+Ridge, PLS, Random Forest,
ExtraTrees and sklearn histogram boosting run locally. Fits remain
single-threaded for prediction reproducibility; parallelism belongs across
independent families or folds. The campaign benchmarks 2/4/6 workers before a
large parallel run and refuses a setting that drives swap.

## Kaggle GPU

XGBoost, LightGBM, CatBoost, the MLP and FT-Transformer are routed to a
hash-pinned Kaggle bundle. The local environment currently lacks those optional
dependencies, so Quant Lab reports them BLOCKED rather than silently using a
CPU or sklearn substitute.

Every trial records wall, fit and prediction time, peak resident memory, CPU,
platform, Python/dependency versions, device, and GPU/VRAM when measurable.
An unavailable measurement remains null.
