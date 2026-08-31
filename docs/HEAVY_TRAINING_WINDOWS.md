# Heavy training on the Windows CUDA machine

**Target hardware:** NVIDIA RTX PRO 4500, 24 GB VRAM, 64 GB system RAM.

This runs **EXP-007-WIN-GPU**, a separate registered experiment. It is not a
second copy of EXP-007 and its results are never merged into EXP-007's artifact.

---

## 1. What this machine is for, honestly

Most of this project's models cannot use a GPU. scikit-learn's
`GradientBoostingRegressor` is exact-split, has no CUDA path, and is pinned to
one thread by the determinism rule. "Running it on the GPU" is not a thing that
exists.

What genuinely accelerates on CUDA:

| Family | GPU path | Why it is in the search |
|---|---|---|
| `xgboost` | `tree_method="hist"`, `device="cuda"` | Histogram construction is the bulk of the work and is genuinely parallel. |
| `lightgbm` | `device_type="gpu"` | Leaf-wise growth — a different inductive bias from XGBoost, not a second copy of it. |
| `catboost` | `task_type="GPU"` | Oblivious (symmetric) trees. Genuinely different constraint. |
| `torch_mlp` | CUDA tensors | The only family here that uses the GPU for something other than histograms. |

Four families, chosen because each represents a *different* hypothesis. Three
near-identical boosters would spend trials without adding information.

## 2. The part that costs the Mac something

These trials share EXP-007's validation folds, so they share its
multiple-testing budget.

```
prior (EXP-001..EXP-006 + EXP-007 overnight)   1035
EXP-007-WIN-GPU                                 130
cumulative                                     1165
expected max |t| under the null   3.39  ->  3.42
```

Running this search **raises the bar EXP-007's own Mac winner has to clear.**
That is why the budget is 130 configurations and not 1,300. If you want to run a
much larger GPU search, that is a decision to make deliberately, knowing it
penalises the other machine's result.

## 3. Setup

### 3.1 Python

Python **3.12**. Match the Mac's minor version so `pandas`/`numpy` pickle
formats and default dtypes agree.

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3.2 Project dependencies

```bat
pip install -r requirements.txt
```

### 3.3 CUDA packages

Install these **after** the base requirements, and from the CUDA index — the
default PyPI `torch` wheel on Windows is CPU-only and will silently give you a
machine that reports `cuda_available: false`.

```bat
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install xgboost lightgbm catboost
```

`xgboost` ships CUDA support in the standard wheel from 2.0 onward. `lightgbm`
does **not** — the PyPI wheel is CPU-only, and GPU support needs a build with
`-DUSE_GPU=1`. If you do not want to build it, drop it:

```bat
python -m scripts.quant.win_gpu_worker --families xgboost,catboost,torch_mlp --confirm
```

Dropping a family is fine and is recorded in the artifact. Running it on CPU
while calling it GPU is not.

### 3.4 Verify the GPU is actually visible

```bat
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Expect `True NVIDIA RTX PRO 4500`. If it prints `False`, stop and fix that
first — the worker will refuse to run rather than quietly use the CPU.

## 4. Repository

```bat
git clone https://github.com/iAakash1/miniAladdin
cd miniAladdin
git checkout <EXPERIMENT_COMMIT>
```

The commit matters. Pin it to whatever `git_commit` the Mac's
`experiments/EXP-007/search.json` records, so both machines run the same feature
code. Running a different commit produces a different panel hash and the worker
will say so.

## 5. Data

**Datasets are not in Git**, by policy, and no credentials are either. The panel
is rebuilt locally from the raw partitions:

```bat
python -m scripts.quant.local_backfill --stage all
python -m scripts.quant.backfill --stage universe --universe-size 250
```

This needs whatever data access the Mac uses, configured through environment
variables on your own machine. Nothing is committed.

**Check the panel matches.** The worker prints its `content_hash` and it must
equal the `dataset.content_hash` in the Mac's `experiments/EXP-007/search.json`.
If the hashes differ, the two machines are not looking at the same data and
comparing their results is meaningless. Stop and reconcile before running.

## 6. Run it

Dry run first — prints the plan, the detected GPU, the configuration count and
the trial cost, and fits nothing:

```bat
python -m scripts.quant.win_gpu_worker
```

Then:

```bat
python -m scripts.quant.win_gpu_worker --confirm
```

After any interruption:

```bat
python -m scripts.quant.win_gpu_worker --confirm --resume
```

### Workers

`--workers` defaults to **2**. Keep it small. Each process holds its own CUDA
context and its own copy of the panel; four boosters contending for one device
is slower than two, and 24 GB of VRAM disappears faster than you expect. With
64 GB of system RAM the constraint is the GPU, not the host.

## 7. Where things land

| | |
|---|---|
| checkpoint | `experiments/EXP-007-WIN-GPU/checkpoints/configs.jsonl` |
| artifact | `experiments/EXP-007-WIN-GPU/search.json` |

The checkpoint is append-only JSONL, written after every configuration. Closing
the terminal, a driver reset, or a power cut costs at most the configuration in
flight.

## 8. Sending results back

Send the whole `experiments/EXP-007-WIN-GPU/` directory — as a branch, a PR, or
a zip. It is small (hundreds of KB).

**Do not copy anything into `experiments/EXP-007/`.** That is the Mac's
namespace and overwriting it destroys the record the deployed artifact
references.

## 9. What the artifact records about your machine

Provenance is captured so a result can be attributed afterwards:

- OS, CPU architecture, Python version
- GPU name, VRAM, CUDA driver version, and *how it was detected*
- exact versions of numpy, pandas, scikit-learn, scipy, xgboost, lightgbm,
  catboost, torch, joblib
- git commit and whether the working tree was dirty
- dataset content hash
- seed, fold boundaries, execution lag, cost assumptions
- every configuration, including the ones that failed

`cuda_available: null` means torch was not installed and the GPU state is
genuinely **UNKNOWN**. It is recorded as unknown rather than guessed.

## 10. What will not reproduce, and why that is fine

CUDA histogram construction reduces in nondeterministic order. Two runs on the
same GPU with the same seed can differ in the last bits, and a Mac CPU run will
never reproduce a Windows GPU run bit-for-bit.

Held identical across machines, by construction:

- dataset content hash
- feature list and ordering
- target definition
- fold boundaries, embargo, purge
- execution lag
- cost assumptions
- seed

Not held identical: floating-point association. Which is exactly why this is a
separate experiment with machine provenance attached, rather than extra rows in
EXP-007's table.

## 11. How results are combined

They are **not** automatically combined.

The Mac produces `experiments/EXP-007/search.json`. The Windows machine produces
`experiments/EXP-007-WIN-GPU/search.json`. Both become rows in
`docs/RESEARCH_LEDGER.md`, each with its own machine, its own trial count, and
its own verdict.

Taking the better number off two machines and reporting it as one result is
selection, not aggregation — and it is exactly the failure mode the
multiple-testing accounting in this project exists to prevent. If a GPU family
does produce a candidate, it goes through the same gates in
`scripts/quant/select_candidate.py`, against the *shared* cumulative trial
count.

## 12. The holdout

Sealed. This worker cannot open it.

`build_plan` reserves the final 252 sessions before the first fold is cut, and
`HoldoutFirewall.assert_clear` runs on the training frame and the validation
frame of every fold before every fit. There is no flag, and no environment
variable, that turns it off — setting `QUANT_DISABLE_HOLDOUT_FIREWALL` makes the
firewall raise rather than relax.

If you find yourself wanting holdout numbers, the answer is no. That decision is
made once, deliberately, under `docs/HOLDOUT_CONTRACT.md`, on the Mac.
