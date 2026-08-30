# Model Training

> Training is local. Inference would be Render. Nothing is deployed, because
> nothing has cleared the promotion gate — and the pipeline is built so that
> promotion is a registry state change rather than a rewrite.

---

## 1. The pipeline, as it actually runs

Every stage below executes today. EXP-005 ran all of it in **1h 42m** on an
Apple M4 Pro with 6 workers; EXP-006 re-ran the frozen `C_base` specification
through the same path.

```mermaid
flowchart TD
    subgraph V["Versioned inputs — all hashed into the fingerprint"]
        D["Dolt clones<br/>14 GB, gitignored"]
        C["DatasetCatalog<br/>PIT class per source"]
    end

    D --> C --> B["DatasetBuilder<br/>content_hash"]
    B --> F["FeatureEngine<br/>103 registered"]
    F --> L["LabelEngine<br/>forward rank / return"]
    L --> S["WalkForwardEngine<br/>expanding + purge + embargo"]
    S --> FW{"HoldoutFirewall<br/>assert_clear per fold"}
    FW -->|holdout rows| X["HoldoutBreach — nothing computed"]
    FW -->|clear| T["Fit per fold<br/>FoldImputer fitted INSIDE the fold"]
    T --> P["Predictions artifact<br/>parquet"]
    P --> E["Evaluation<br/>Newey-West IC, fold dispersion"]
    E --> R["Robustness<br/>regimes · cost sweep · PBO · ablation"]
    R --> BT["Costed backtest<br/>lag · commission · spread · impact"]
    BT --> M["Multiple testing<br/>deflated Sharpe vs CUMULATIVE trials"]
    M --> REG["ModelRegistry<br/>evidence bundle"]
    REG --> G{"Promotion gate"}
    G -->|evidence missing OR numbers fail| REJ["REJECTED — recorded with reasons"]
    G -->|both pass| PROD["production"]
    PROD -.->|not reached| DEP["Render inference"]

    style DEP stroke-dasharray: 5 5
    style REJ stroke:#c0392b
```

**The only stage never exercised is the last one.** That is the honest state.

---

## 2. What is versioned

An experiment is a frozen declaration, hashed by `ExperimentDefinition.fingerprint()`.
Change any field and the hash changes, so a report cannot be silently
re-attributed to a different setup.

| Recorded | Where |
|---|---|
| git SHA + dirty flag | `metrics.json → git_commit`, `git_dirty` |
| dataset content hash | `dataset.content_hash` |
| dataset version id | `dataset.dataset_version` |
| source manifests (rows, dates, PIT class) | `dataset.source_datasets` |
| feature set actually used | `features_used` |
| feature families, when frozen | `experiment.feature_families` |
| target definition | `experiment.targets`, `primary_target` |
| random seed | `experiment.seed` |
| hyperparameters per model | `experiment.models[].params` |
| training + validation windows | `labels.<target>.fold_rows` |
| execution lag | `experiment.execution_lag_periods` |
| transaction costs | `backtests.<model>.config.costs` |
| benchmark | `factor_attribution` (FF5 + MOM) |
| trial count | `declared_evaluations`, `prior_evaluations`, `cumulative_evaluations` |
| dependency versions | `dependency_versions` |
| machine | `machine` |

Reproduce any study from these alone:

```bash
git checkout <git_commit>
export QUANT_DATA_ROOT=/path/to/datasets
python -m scripts.quant.local_backfill --stage all
python -m src.quant.study.run --experiment <id> --workers 6
# dataset content_hash must match the recorded one, or the panel moved
```

---

## 3. Compute

Measured on this machine, not assumed.

| | |
|---|---|
| CPU | Apple M4 Pro, 12 cores |
| RAM | 24 GB |
| Disk free | ~72 GB |
| Workers | **6** (`MAX_WORKERS`) |
| Peak RSS observed | ~7.3 GB |
| EXP-005 wall clock | 6,131 s |

### Why 6 and not 12

A previous run with 12 workers **OOM-ed the machine**. `recommended_workers()`
now sizes the pool from measured frame bytes:

```
per_worker  = frame_bytes / 1 GiB + WORKER_OVERHEAD_GB   (2.6)
affordable  = (total_gb - reserve_gb) / per_worker        (reserve 6 GB)
workers     = min(ceiling, cores, affordable, MAX_WORKERS)
```

with a hard `MAX_WORKERS = 6` ceiling on top, because the memory estimate is an
estimate and the failure mode of getting it wrong is not a slow run but a killed
one. During the EXP-005 controls the arithmetic chose **2** workers on its own —
the ceiling is a bound, not a target.

**GPU/MPS is not used and should not be.** Everything in the ladder is
scikit-learn on tabular data: tree ensembles do not benefit from Metal, and the
linear models are trivial. There is no neural model to accelerate, and adding one
to justify the hardware would be exactly backwards.

---

## 4. Model families, in order

Baselines first, always. They are the thing to beat, and they keep winning.

| Family | Members | Rationale |
|---|---|---|
| Naive | zero, historical mean | Floor. Detects a broken pipeline |
| Factor passthrough | momentum, reversal, low-volatility, earnings surprise, IV premium | Free, published, no fitting. A learned model that loses to these has rediscovered them expensively |
| Linear | OLS, ridge, ridge-strong, lasso, elastic net | Interpretable; a large gap to trees signals nonlinearity or overfitting |
| Trees | random forest, extra trees, gradient boosting, hist gradient boosting | Capture interactions without feature engineering |
| Overfit control | gradient_boosting_deep | **Deliberately over-parameterised.** Exists to prove the train/validation gap diagnostic fires — and it does, at +0.718 |

Anything beyond this — sequence models, transformers, representation learning —
is **not justified by the evidence**. Complexity is not a hypothesis. The
ablation showed that adding *data* to a 27-feature set makes results worse; there
is no reading of that under which adding model capacity is the missing piece.

---

## 5. Anti-overfitting, enforced not documented

| Control | Where |
|---|---|
| Expanding walk-forward, never random | `build_plan`; no code path produces a random split |
| Purge by label horizon | 21 sessions |
| Embargo | 5 further sessions |
| Execution lag ≥ 1 | refused in `ExperimentDefinition.__post_init__` |
| Holdout firewall | `assert_clear` per fold, before every fit; no env override |
| Imputer fitted inside the fold | hoisting it out is the leak |
| Cross-sectional ranks fitted per date | cannot leak across dates |
| No hyperparameter search | fixed defaults in the frozen definition |
| Baseline comparison | baselines in the same table, same folds |
| Costs | commission + assumed half-spread + sqrt impact |
| Multiple testing | deflated Sharpe vs **cumulative** trials |
| PBO | CSCV, degenerate configs excluded and named |
| Newey-West | Bartlett kernel, lags = ceil(horizon/step) − 1 |
| Regime floor | 200 validation dates or INSUFFICIENT EVIDENCE |
| Train/validation gap | reported per model; > 0.15 renders OVERFIT |

---

## 6. Promotion

```mermaid
stateDiagram-v2
    [*] --> experimental
    experimental --> validated: walk-forward + methodology + baseline comparison
    validated --> production_candidate: costs + attribution AND CANDIDATE_THRESHOLDS clear
    production_candidate --> production: holdout + regimes AND PRODUCTION_THRESHOLDS clear
    experimental --> retired: any time, with a reason
    validated --> retired
    production_candidate --> retired
    production --> retired
```

Two independent refusals, both required:

* `PROMOTION_GATES` — does the required evidence **exist**?
* `CANDIDATE_THRESHOLDS` / `PRODUCTION_THRESHOLDS` — what does it **say**?

`CANDIDATE_THRESHOLDS` at candidacy: `|IC t| ≥ 2`, net Sharpe > 0, **gross
Sharpe > 0**, beats best baseline. An unrecorded value counts as unmet.

Current registry: **88 entries, 0 production, 0 candidates, 34 retired VOID.**
Every EXP-005 entry is eligible for `validated` and nothing beyond it.

---

## 7. Deployment, when there is something to deploy

```mermaid
flowchart LR
    subgraph L["Local — training only"]
        DS["Dolt clones 14 GB"] --> TR["ExperimentRunner"]
        TR --> AR["experiments/EXP-*/"]
        TR --> RG["registry.json"]
    end
    subgraph R["Render — inference only"]
        API["FastAPI /api/quant/*"]
        MA["Frozen artifact<br/>joblib + feature schema"]
    end
    subgraph W["Vercel"]
        Q["/quant"]
    end
    AR -.->|read-only| API
    RG -->|status gate| API
    MA -.->|absent today| API
    API --> Q
    style MA stroke-dasharray: 5 5
```

Training never runs on Render. The 14 GB of clones are a development dependency,
not a deployment one: inference needs the artifact and the feature schema.

The deployable unit, when one exists: `joblib` estimator + feature specification
+ metadata (version, dataset hash, git SHA, seed, training window, validation
report). If it cannot be reproduced from that, it is not production-ready — which
is why `PROMOTION_GATES` requires those fields rather than encouraging them.

**A model that fails promotion never reaches Render.** `/api/quant/status`
returns `NO_MODEL` from the registry, and `/api/quant/symbol/{ticker}` returns an
explicit refusal instead of a number.

---

## 7b. Model Deployment (EXP-006)

> The model is deployed as an **inference service**. It is **not** promoted.
> Registry production count remains 0.

### What is deployed

| | |
|---|---|
| Model | `gradient_boosting@4.0:fwd_rank_21` |
| Experiment | **EXP-006**, fingerprint `6f8703469aec28e5` |
| Target | `fwd_rank_21` — cross-sectional rank, 21-session horizon |
| Features | 27 (`price`, `volatility`, `volume`, `macro`) |
| Artifact | `artifacts/gradient_boosting@EXP-006.joblib` — **89 KB**, committed |
| Metadata | `artifacts/gradient_boosting@EXP-006.metadata.json` |
| Feature snapshot | `artifacts/feature_snapshot.parquet` — 250 symbols, as of **2025-08-27** |
| Research status | **EXPERIMENTAL** |
| Promotion | **BLOCKED** — net Sharpe −0.102 at the declared 10 bp half-spread |

### The distinction that must travel with it

EXP-006 never persisted a fitted estimator, and neither did any earlier study:
`run_walk_forward` builds a fresh model per fold and discards it. That is correct
for research, because the object of study is the **specification**.

So `scripts/quant/build_artifact.py` materialises one. The consequence:

* **EXP-006's metrics** — IC +0.0290, t +2.66, gross Sharpe +0.384, net Sharpe
  −0.102 — were estimated from **eight separate walk-forward fits** and describe
  the specification.
* **The deployed artifact** is **one** fit of that specification over the whole
  pre-holdout window (142,941 rows, 2014-04-03 → 2025-08-27, 876 symbols).

They are not the same object. `/model` serves the metrics under
`specification_metrics` with that caveat attached rather than as properties of
the file. Reporting them as the artifact's own would be a category error.

The builder refuses to run if the rebuilt dataset's `content_hash` differs from
the one EXP-006 recorded, and arms the holdout firewall over the fit window.

### Architecture

```mermaid
flowchart LR
    subgraph L["Local — training only"]
        D["Dolt clones · 14 GB · gitignored"] --> R["ExperimentRunner"]
        R --> A["experiments/EXP-006/"]
        R --> B["build_artifact.py"] --> AR["artifacts/*.joblib · 89 KB"]
    end
    subgraph V["Vercel"]
        Q["/quant"]
    end
    subgraph API["Render — miniAladdin backend"]
        C["inference_client.py"]
    end
    subgraph INF["Render — inference service"]
        S["services/inference/app.py"] --> M["gradient_boosting@4.0"]
    end
    AR -.->|committed| S
    Q --> C --> S
    A -.->|read-only| C
```

Training is **off** the request path. The inference image installs
`services/inference/requirements.txt` only — no yfinance, no supabase, no
provider fabric, no Dolt.

### Endpoints

**Inference service** (`render.yaml` → `minialaddin-quant-inference`):

| Endpoint | Purpose |
|---|---|
| `GET /health` | `ok` is false when the artifact failed to load — a service reporting healthy while unable to predict stops the caller's fallback engaging |
| `GET /model` | Full provenance: registry key, experiment, fingerprint, features, dataset hash, git SHA, seed, fit scope, specification metrics, blocked gate |
| `POST /predict` | Scores pre-computed feature vectors. Every response repeats model identity and status |

**miniAladdin backend** (degrades, never raises):

| Endpoint | Purpose |
|---|---|
| `GET /api/quant/inference/status` | Service health + model card |
| `GET /api/quant/inference/predict/{symbol}` | Prediction with provenance, or a structured `unavailable` |

### Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `MODEL_ARTIFACT_DIR` | inference | Artifact directory (default `artifacts`) |
| `MODEL_ARTIFACT` | inference | Artifact stem (default `gradient_boosting@EXP-006`) |
| `ALLOWED_ORIGINS` | inference | CORS allow-list. **Empty by default** — the backend proxies server-side, so no browser needs direct access |
| `QUANT_INFERENCE_URL` | backend | Inference service base URL. Unset ⇒ reported unavailable, never guessed |
| `QUANT_INFERENCE_TIMEOUT` | backend | Seconds, default 8 |

No secrets. The service reads two files and exposes no path, no dataset and no
credential.

### Deploying

```bash
python -m scripts.quant.build_artifact --experiment EXP-006 --model gradient_boosting
python -m scripts.quant.export_feature_snapshot --experiment EXP-006
git add artifacts/ && git commit && git push        # 89 KB + 39 KB
# Render: create from render.yaml, then set QUANT_INFERENCE_URL on the backend
curl https://<service>.onrender.com/health
```

### Why it is not promoted

`CANDIDATE_THRESHOLDS` on validation:

| Bar | Required | Observed | |
|---|---|---|---|
| \|IC t\| | ≥ 2.0 | +2.66 | PASS |
| gross Sharpe | > 0 | +0.384 | PASS |
| beats best baseline | true | +0.0290 vs +0.0209 | PASS |
| **net Sharpe** | **> 0** | **−0.102** | **FAIL** |

Three of four. Deploying it as an inference service does not change that, and no
part of the serving path can: `promote()` lives in the research repository and
the artifact carries `promotion_status: BLOCKED` as data.

Net Sharpe is positive at 1, 3 and 5 bp and crosses zero between 5 and 10 — the
half-spread is assumed, not observed. That is a reason for caution, not a reason
to lower the bar.

---

## 8. Experiment lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor R as Researcher
    participant D as ExperimentDefinition
    participant L as RESEARCH_LEDGER.md
    participant X as ExperimentRunner
    participant G as Guards
    participant A as Artifact
    participant M as ModelRegistry

    R->>D: declare models, targets, folds, costs, seed, trial count
    D->>D: fingerprint() over the whole declaration
    R->>L: pre-register — arms and thresholds BEFORE the run
    R->>X: run
    X->>G: truncation invariance
    alt integrity fails
        G-->>X: abort — no result admissible
    end
    X->>G: negative controls
    alt a blocking control finds signal
        G-->>X: abort BEFORE any model is fitted
    end
    X->>X: fit, backtest, attribute, correct for trials
    X->>A: metrics.json + predictions + folds + portfolio
    R->>M: register — evidence bundle per model
    M->>M: promote() evaluates gates
    alt evidence missing or numbers fail
        M-->>R: PromotionRefused, with the unmet items
    end
    R->>L: record the result, including a void one
```

Rule that makes the rest work: **a void study stays in the ledger.** Deleting
EXP-002 would erase the multiple-testing exposure it created, and every later
significance claim is discounted against the cumulative total.

---

## 9. Adding a training job later

The architecture is ready for background jobs; nothing about it needs rewriting.

1. Add an `ExperimentDefinition` to `EXPERIMENTS` in `study/experiment.py`.
2. Pre-register it in `docs/RESEARCH_LEDGER.md` — arms, metrics, trial count.
3. Run `python -m src.quant.study.run --experiment <id>`.
4. `python -m scripts.quant.register_experiment --experiment <id>`.
5. The UI picks it up: `/api/quant/experiments` lists it, `/quant` renders it.

To make it a queued job rather than a CLI invocation, the runner is already a
pure function of its definition plus the dataset — the only shared state is the
artifact directory. A job runner would supply the definition id and collect the
artifact; no scientific code changes.

**What must not change:** the definition is frozen before the run, the trial
count accumulates across studies, and the holdout stays locked.
