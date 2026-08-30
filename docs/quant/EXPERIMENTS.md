# Experiment Lifecycle

> Every experiment is a **declaration** before it is a result. The models, the
> targets, the folds, the costs, the seed and the trial count are frozen in
> `src/quant/study/experiment.py` and hashed, so a report cannot be silently
> re-attributed to a different setup.

---

## 1. The rule that makes the rest work

**Pre-registration.** `ExperimentDefinition` is a frozen dataclass with a
`fingerprint()` over its full serialisation. Change a field, change the hash.
`primary_target` is validated in `__post_init__` to be among the targets, so it
cannot be chosen after seeing which one worked.

`declared_evaluations` is computed from the definition — `len(models) ×
len(targets)`, plus `len(arms) × len(arm_models) × len(targets)` — rather than
counted afterwards. Arm evaluations count fully: a contrast between arms is
still a comparison a human looks at and can select on.

---

## 2. The register

| Study | Configurations | Targets | Evaluations | Status |
|---|---|---|---|---|
| EXP-001 | 12 | 1 | 12 | complete |
| EXP-002 | 17 | 2 | 34 | **VOID** — as-of join defect |
| EXP-003 | 0 | 0 | 0 | audit only |
| EXP-004 | 17 | 2 | 34 | complete — NO EVIDENCE OF EDGE |
| EXP-005 | 17 + 7×6 | 1 | 59 | this study |
| **Cumulative** | | | **139** | |

**A void study stays in the count.** Deleting EXP-002 would erase the exposure
it created, and every later significance claim is discounted against the total.

---

## 3. EXP-005: the ablation

EXP-004 established that the corrected pipeline finds nothing in the feature set
it had. Two readings survive that: the signal is not there, or the feature set
never contained it. EXP-005 separates them by asking, one source at a time,
whether adding a family beats a price-and-volatility base.

| Arm | Families | Question |
|---|---|---|
| `A_price` | price | The floor: what momentum and reversal already capture. |
| `B_price_vol` | + volatility | Does volatility add over price alone? |
| `C_base` | + volume, macro | **The base.** Everything derivable from the price panel plus the curve. |
| `D_base_options` | + options | Does the 8 GB options dataset earn its cost? |
| `E_base_estimates` | + estimates | Do analyst revisions add? **Never tested before.** |
| `F_base_fundamentals` | + earnings, fundamentals | Do gated statement fundamentals add? Isolated for restatement risk. |
| `G_all` | everything | If G does not beat C, the negative covers all sources jointly. |

It is a **ladder**, not a power set: each arm adds one family to a fixed base, so
each contrast is attributable to one source. Testing all 2⁷ subsets would answer
more questions and cost 128× the trials to answer any of them convincingly.

**Reduced ladder per arm.** Six learned models (`ridge`, `elastic_net`,
`random_forest`, `gradient_boosting`, `hist_gradient_boosting`, `extra_trees`),
not seventeen. Asking 17 models the same question 7 times costs 238 trials to
answer it no better than 42 do. Baselines are single-feature passthroughs that
do not depend on the arm, so they run once.

**One target.** EXP-004 showed `fwd_ret_21` is won by a baseline with every
learned model at or below +0.0028. Carrying it here would double the trial count
to re-answer a settled question.

---

## 4. How a contrast is read

`models_improved / models_compared` is the headline, not the best-of. One model
improving out of six is noise; a maximum over six draws is biased upward by
construction. `mean_delta` and `median_delta` are reported beside it.

A family "adds information" only if its arm beats `C_base` **on the same folds,
with the same models and the same seed**. Nothing else counts.

---

## 5. Stopping rules

Declared before the run:

* If a **blocking negative control** fires, the study aborts before any model is
  fitted. This has happened.
* If **truncation invariance** fails, the study aborts. Results from a run with a
  failed integrity check are not admissible.
* If a **methodological flaw** is found mid-study, the study stops, the flaw is
  fixed, affected results are invalidated, and the invalidation is recorded
  permanently. This has happened — EXP-002.
* No arm may be added after results are seen. No threshold may be moved to make
  a model pass.
