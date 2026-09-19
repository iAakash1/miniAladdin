# Model compute feasibility: M4 Pro versus Kaggle T4 x2

Date: 2026-09-19. This document separates **reported compute** from
**OmniSignal planning estimates**. Ranges are not benchmark claims. The local
machine inspected for this study is a 12-core (8 performance + 4 efficiency)
M4 Pro with 24 GB unified memory. Kaggle's documented accelerator is two
separate T4 devices with 16 GB VRAM each, four CPU cores and about 29 GB host
RAM. The GPUs do not form one 32 GB pool.

## Decision in one sentence

Use the **MacBook** for the immediate EXP-010 noise-floor and cadence studies,
and for all PIT data engineering. Use **Kaggle as two independent workers** only
after the richer PIT panel exists and a GPU-native MLP/embedding study is
preregistered. Neither environment can exactly reproduce the JKMP frontier or
Barunik–Hronec–Tobek workflow.

## Calibration from this repository

The current training panel has 452,524 rows, 103 stored features and a 113 MB
Parquet frame; the frozen model uses 27 features across eight temporal folds.
Measured on this Mac:

| Existing operation | Measured wall time | Meaning for estimates |
|---|---:|---|
| EXP-009A portfolio-only, 10,000 bootstrap draws | 121.6 s | Cadence/portfolio evaluation is cheap compared with refitting |
| EXP-009B, four model cells across eight folds | 628.2 s | Current tree/ranker family is CPU-feasible |
| EXP-009C, two sequential sklearn fits | 666.1 s | About 5.5 min per eight-fold current-model fit |
| EXP-009D, three sklearn fits | 857.6 s | Ten seeds should take roughly 55–90 min serial, before diagnostics |

The last range includes orchestration and conservative headroom. A measured
job always supersedes the planning range.

## Paper-reported compute

| Study | Hardware and runtime stated by authors | Exact replication here? |
|---|---|---|
| Jensen–Kelly–Malamud–Pedersen implementable frontier | Slurm/HPC. Twelve model jobs: 32 CPUs, 100 GB request, about 75 GB used and ≤5 h **each**. Base portfolio: 48 CPUs, about 40 GB, ≤6 h. All-stock portfolio: 32 CPUs, about 70 GB, 2 d 16 h. Frontier: 20 jobs, 16 CPUs/about 40 GB, ≤7 h each. | **Neither.** Both local RAM (24 GB) and Kaggle host RAM (~29 GB) are below individual-job use; Kaggle sessions are also too short for the all-stock job. |
| Barunik–Hronec–Tobek quantile networks | Ubuntu, 16-core CPU, RTX 4090 24 GB, 128 GB RAM. Authors report >2 months total: ~2 weeks data, ~3 weeks tuning, ~2 weeks all NNs, ~1 week GARCH, days for trees, ~2 weeks simulations; minimum example ~4 days. | **Neither exact.** Kaggle T4 is slower and has less VRAM/host RAM; its session limit prevents the reported jobs. |
| Qian et al. MDGNN | Nvidia V100, PyTorch, hidden size 128, 2 layers, window 10, 500 epochs, six-month rolling retrains; runtime and RAM not reported. | Small adaptation could fit Kaggle, but the 18.9–62.5 million-edge China graphs and relation data are absent. |
| Chen–Pelger–Zhu deep SDF | Nine-model ensembles of FFN/LSTM/adversarial networks over all CRSP stocks, 46 firm features and 178 macro series; hardware/runtime not reported. | Data/objective mismatch and unlicensed code/data make exact replication inappropriate regardless of device. |
| Zhang–Wu–Chen ListFold | Four-layer MLP, 21 rolling train/test pairs, 300-week training windows, 16-week tests; hardware/runtime not reported. | Compute is feasible on either device; the 80-stock survivor-filtered China dataset and unlicensed code make the evidence weak. |
| Qlib Alpha158 benchmark | Official table reports means over 20 seeds but not hardware/runtime. | Models fit both; US PIT data is the binding constraint. |

`NR` compute disclosures must not be backfilled with invented author hardware.

## OmniSignal model-family estimates

Assumptions: 452k rows; 26–120 numeric features; eight walk-forward folds; one
configuration unless stated; float32 where supported; no full-grid search;
features already materialized. “Kaggle” uses one T4 per independent seed or
fold group. Data upload/setup time (typically 5–30 min) is excluded.

| Model family | CPU / RAM | GPU / VRAM | Mac estimate | Kaggle T4 estimate | Inference | Parallelization | Difficulty / risk | Environment |
|---|---|---|---:|---:|---:|---|---|---|
| Ridge / elastic net / regularized Fama–MacBeth | 4–12 GB | none | 3–20 min | 5–25 min CPU | seconds | folds or seeds | Low; strongest audit baseline | **MACBOOK** |
| Current sklearn gradient boosting | 8–16 GB | none | measured 5–9 min / seed; 55–90 min / 10 seeds | CPU gives little benefit | seconds | processes capped to avoid memory pressure | Low; canonical noise control | **MACBOOK** |
| LightGBM/XGBoost regression on 26–120 features | 8–18 GB | optional 2–8 GB | 20–90 min / 10 seeds | 10–40 min / 10 seeds using two independent GPUs | seconds | seed 0/2/4… on GPU0, 1/3/5… on GPU1 | Medium; OpenMP/CUDA environment pinning | **EITHER**, Kaggle only for multi-seed speed |
| LightGBM LambdaMART / pairwise trees | 8–18 GB | optional 2–8 GB | 30–120 min / 10 seeds | 15–60 min / 10 seeds | seconds | same independent-seed split | Medium; query grouping and objective already failed once | **NOT NEXT** |
| Random forest / extra trees | 12–22 GB at large tree counts | optional ecosystem-dependent | 1–4 h | 30–120 min | seconds–minutes | trees/seeds | High RAM; little reason over boosting | **DEFER** |
| Small MLP (2–4 layers) | 6–14 GB | 2–6 GB | 1–4 h / 10 seeds on MPS or CPU | 30–120 min / 10 seeds | seconds | independent seeds per GPU | Medium; seed variance and preprocessing | **KAGGLE_T4** after data build |
| FT-Transformer / TabTransformer | 8–18 GB | 6–12 GB | 6–20 h / 10 seeds | 2–8 h / 10 seeds | seconds–minutes | independent seeds; no DDP needed | High; Qlib gives no strong finance prior | **DEFER** |
| LSTM/TCN/Patch-style temporal model | 10–20 GB | 6–14 GB | 8–30 h / 10 seeds | 3–12 h / 10 seeds | minutes | independent seed/fold jobs | High; sequence construction and weak baseline evidence | **DEFER** |
| Quantile MLP, reduced 9 quantiles | 10–20 GB | 8–14 GB | 10–30 h / seed | 3–10 h / seed | minutes | one seed per GPU | High calibration/storage burden; no cost result in source | **DEFER** |
| Frozen FinBERT/sentence embeddings for SEC event text | 8–20 GB | 6–12 GB | 8–30 h per first corpus | 2–8 h per first corpus | cached embeddings make later inference cheap | shard documents across GPUs | Medium–high; text timing and document identity dominate | **KAGGLE_T4** if text enters shortlist |
| FinBERT fine-tuning / LoRA | 12–24 GB | 10–16 GB | possible but fragile/slow | 1–6 h per run | minutes | one run per T4; do not pool memory | High overfit/license risk | **KAGGLE_T4**, later only |
| GNN / temporal heterogeneous graph | 16 GB to >70 GB depending edge count | 10–16+ GB | impractical for MDGNN scale | reduced graph only; 4–12 h / run | minutes | independent folds; graph partitioning otherwise | Very high; relation data absent | **NOT PRACTICAL NOW** |
| Deep SDF/GAN | 16–64+ GB | 12–24+ GB | reduced toy only | reduced study possible, exact no | minutes | independent ensembles | Very high objective/data mismatch | **REJECT** |
| JKMP economic portfolio objective | 25–75 GB measured by authors | CPU/HPC workflow | memory bound | memory/session bound | NR | large Slurm job arrays | Very high; licensed inputs, no license | **NEITHER exact** |

## Workload-specific decision

| Workload | MacBook | Kaggle T4 x2 | Choice |
|---|---|---|---|
| SEC bulk/XBRL parsing, identifier joins, PIT tests | Native filesystem, 24 GB adequate with streaming/Parquet | Session/storage friction; no GPU value | **Mac** |
| Security-master construction and hand validation | Best debugging/audit surface | No benefit | **Mac** |
| EXP-010A ten-seed current-model noise floor | 55–90 min estimated from measured runs | Porting/setup larger than likely speedup | **Mac** |
| EXP-010B frozen predictions, 5d vs 21d cadence | 5–20 min | No benefit | **Mac** |
| Rich PIT tabular boosting, ten seeds | 1–4 h depending features | 20–90 min if CUDA implementation is pinned | Start **Mac**; move to **Kaggle** only if measured runtime exceeds 2 h |
| Small neural tabular ablation | MPS support must be tested; 24 GB shared | CUDA is mature; two independent workers | **Kaggle** |
| SEC embedding generation | Possible but slow | Best match; shard documents | **Kaggle** |
| Full quantile-network or frontier-paper replication | Insufficient RAM/time | Insufficient RAM/session | **Neither** |

## Operational rules

1. Never describe T4 x2 as 32 GB pooled VRAM. Prefer two single-GPU workers.
2. Make Parquet shards and manifests on the Mac, upload only frozen inputs, and
   copy hashes/results back. Kaggle must not become an undocumented data source.
3. Cap concurrent CPU folds so their peak resident sets do not exceed 18 GB on
   the 24 GB machine. Preserve headroom for the OS and filesystem cache.
4. Report actual wall time, peak host RAM, peak VRAM, package lock, device name,
   seed and input hash in every future manifest.
5. Stop a model family when a cheaper baseline matches it within the registered
   noise margin. GPU availability is not evidence.
