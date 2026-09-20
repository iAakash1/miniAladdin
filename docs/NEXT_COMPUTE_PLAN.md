# Compute plan for the next research sequence

Date: 2026-09-19. These are planning envelopes, not measured promises. Times
assume the 452,524-row training-side panel, no sealed-holdout rows, eight folds,
and materialized Parquet inputs. Every run records actual wall time, package
versions, peak RAM/VRAM, input hash, commit and seed.

| Stage | Model | Data / features | Folds × seeds | Device | Expected memory | Mac time | Kaggle T4 time | Parallel plan | Expected artifacts |
|---|---|---|---|---|---|---:|---:|---|---:|
| EXP-010A | sklearn GradientBoostingRegressor | 452k rows, 26 deduplicated base features | 8 × 10 | CPU | 8–16 GB RAM | **55–90 min** | no useful advantage | 1–2 seeds at a time; cap peak RAM | 0.5–1.5 GB predictions + <50 MB metrics/manifests |
| EXP-010B | no retraining; frozen predictions | ~100k OOS predictions; 5d and 21d portfolio grids | 8 × fixed predictions | CPU | 2–6 GB RAM | **5–20 min** | n/a | cadence arms serial; bootstrap workers limited | <100 MB |
| PIT security master | joins/rules, no ML | 998 historical universe members plus SEC filings | n/a | CPU / Parquet | 4–16 GB RAM using streaming | **1–3 engineering days**, individual runs 5–60 min | worse workflow | shard by filing year; deterministic merge | 0.2–2 GB |
| SEC XBRL ingest | parser/tag mapping, no ML | 2009+ quarterly bulk facts; selected tags plus provenance | n/a | CPU / Parquet | 8–18 GB RAM streaming | **2–5 engineering days**, full rebuild 1–6 h | no GPU value | process quarter shards; atomic manifests | 5–20 GB raw/cache, 1–5 GB curated |
| Characteristic panel | deterministic features | 452k+ rows, target 60–120 usable features | n/a | CPU | 8–18 GB RAM | **1–4 h** full materialization | n/a | feature families by shard, then keyed merge | 0.5–3 GB |
| EXP-011 linear | ridge/elastic net | base 26 vs rich 60–120 | 8 × deterministic or 10 resamples if registered | CPU | 4–12 GB RAM | **10–40 min** | 10–40 min | folds independent | 0.5–1.5 GB |
| EXP-011 existing GB | sklearn GB | base vs rich panel | 8 × 10 | CPU | 8–18 GB RAM | **1–3 h** | no guaranteed speedup | 1 seed at a time if rich panel peaks high | 1–3 GB |
| EXP-011 GPU boosting | LightGBM/XGBoost | base vs rich panel | 8 × 10 | CUDA | 8–18 GB host; 2–8 GB VRAM each | **2–6 h CPU** | **20–90 min** | GPU0 seeds 0,2,4,6,8; GPU1 1,3,5,7,9 | 1–3 GB |
| Conditional EXP-012 | small MLP, one frozen architecture | rich panel only | 8 × 10 | CUDA | 8–16 GB host; 2–6 GB VRAM | 1–4 h MPS/CPU | **30–120 min** | independent seeds, one process/GPU | 1–4 GB checkpoints/predictions |
| Conditional SEC text | frozen FinBERT/sentence encoder + shallow model | accepted-at documents, numeric controls | document shards + 8 × 10 shallow runs | CUDA | 12–24 GB host; 6–12 GB VRAM | 8–30 h first embedding pass | **2–8 h** | split documents, not a single DDP model | 5–30 GB embeddings depending corpus |
| Rejected exact quantile NN | two-stage 37-quantile NN | 194 features, global licensed panel | author workflow | RTX4090/128 GB reported | exceeds both | >4 days even minimum reported | session-incompatible | none | large, unspecified |
| Rejected exact JKMP | economic portfolio policy | JKP/WRDS + daily/monthly + optional Markit | dozens of jobs | Slurm CPU | authors used 25–75 GB/job | memory-bound | host-memory/session-bound | requires cluster job array | large, unspecified |

## Execution controls

1. EXP-010A is the only immediate training-like computation and must be
   preregistered under a new identifier. This document does not authorize it.
2. EXP-010B uses frozen predictions and starts only after the noise distribution
   is fixed. It is not a parameter sweep.
3. A 1% subset smoke test must precede each full data build; a single fold/seed
   is allowed only as an engineering validity check and cannot influence model
   selection.
4. Kaggle inputs are content-addressed exports. Each GPU gets an explicit seed
   list; results are reduced only after both workers finish. Never use implicit
   distributed defaults or assume pooled VRAM.
5. Artifact budgets exclude raw lawful SEC downloads. Raw and curated datasets
   remain gitignored; only schemas, manifests, hashes and aggregate coverage are
   committed.
6. Abort on holdout-date rows, PIT assertion failure, nondeterministic data hash,
   missing cost inputs, or memory above the registered ceiling.

## Status update — 2026-09-20 (measured)

Timing benchmark on the fold-0 *training* rows only (no prediction, no scoring): one gradient-boosting fit took **14.1 s with 26 features and 43.2 s with 76** (3.06x); EXP-010A's eight-fold fit averaged 267 s per seed, so a rich seed is about 13.6 minutes. On the 12-core Mac, EXP-011 is estimated at **30-45 minutes wall time with 6 workers** (about 136 minutes of CPU for ten boosted seeds; Ridge arms about a minute). The models are scikit-learn (CPU-only), so Kaggle GPUs give no benefit; the export/import pipeline (`scripts/quant/export_kaggle_experiment.py`, `kaggle_worker.py`, `import_kaggle_results.py`) exists for reproducibility with independent workers (never DDP), hash-verified imports, and a licence acknowledgement gate. Mac remains the recommended machine for data engineering, Ridge, scikit-learn boosting and backtests.

## Status update — EXP-011 actual runtime (2026-09-20)

EXP-011 ran on the 12-core Mac with 6 workers in **1,769 s (about 29.5 minutes)**, inside the 30-45 minute estimate above. The GPU-boosting row of the table is unused (no such arm was registered).
