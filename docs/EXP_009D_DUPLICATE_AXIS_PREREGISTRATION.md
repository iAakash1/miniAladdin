# EXP-009D preregistration — is the exact duplicate feature axis harmless to remove?

**Status: FROZEN. Registered before either changed arm has been scored.**
EXPERIMENTAL — HYGIENE — PROMOTION NOT ASSESSED. Baseline commit `42b1e29`.

Committed and pushed to `origin/main` **before** execution; `src/quant/study/exp009d.py` refuses to run
unless this file embeds the definition fingerprint below, is committed unchanged, and its commit is an ancestor
of `origin/main` (`src/quant/study/prereg.py`). The fingerprint covers the definition and the bytes of every
method file.

## 1. Why this exists

`dist_52w_high_xs` and `max_drawdown_252_xs` are the same axis with the sign reversed (correlation −1.000 to
three decimals in the audited panel; **−0.999996** on universe rows in the rebuilt frame — rank ties and a constant
offset of 2/N separate it from exactly −1). The 27-feature `C_base` set therefore carries 26 independent axes.
The audit asked that *only* this exact duplicate be removed, and only in a **new** experiment (EXP-006, EXP-009A/B/C
keep the 27 features), because dropping a column changes the trees' random tie-breaking even when the information is
identical — and that has to be measured, not assumed. Any other pruning would be a separate, counted trial and is
not attempted here.

## 2. Arms (frozen split, sklearn `GradientBoostingRegressor`, repository defaults)

| Arm | Features | Seed | Role |
|---|---|---:|---|
| `FULL` | the 27 frozen features | 0 | reproduces EXP-006's frozen predictions (validity gate, 1e-9) |
| `DEDUP` | the same, minus `max_drawdown_252_xs` (its twin `dist_52w_high_xs` is kept) | 0 | the test |
| `NOISE` | the 27 frozen features | 1 | **descriptive noise reference only; enters no criterion** |

Dataset `ds-491d761b9f2a6fc4` (returns-panel sha256 `d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e`),
the eight recorded EXP-006 folds, target `fwd_rank_21`, both portfolio constructions at 1/3/5/10/20 bp.

## 3. Criterion: equivalence, not superiority

| ID | Criterion |
|---|---|
| **Gate** | dataset id and panel hash match; `FULL` reproduces the frozen predictions to 1e-9; \|corr(`max_drawdown_252_xs`, `dist_52w_high_xs`)\| ≥ 0.99999 on universe rows |
| **E_ordering** | paired per-date Rank-IC difference (DEDUP − FULL): \|mean\| ≤ **0.005** and \|mean\| + 1.96 × HAC SE (Bartlett, 4 lags) ≤ **0.010** |
| **E_economics** | under top-k dropout at 10 bp: \|Δ net Sharpe\| ≤ **0.20** and the annualised turnover ratio within [0.9, 1.1] |

**Classification:** `EQUIVALENT` = E_ordering ∧ E_economics; `DIFFERENT` otherwise. **Consequence:** if
`EQUIVALENT`, later experiments may use the 26-feature set without further justification; if `DIFFERENT`,
nothing changes.

**Why these margins.** They are set from the **noise floor EXP-009B measured** for a change that alters no
information — a different bagging implementation moved mean Rank IC by **0.0031** and net Sharpe under top-k dropout
by **0.067** — and **not** from any EXP-009D outcome. A tolerance tighter than that would classify a reseed as a real
difference. The `NOISE` arm shows how far a plain reseed moves the same quantities in this very run, so the reader
can see whether `DEDUP` moved more than that.

## 4. Inference, trials, governance

HAC / block statistics only. **Trials:** 164 + 2 (the DEDUP fit and the seed reference) = **166**. CPU only, three
single-process sklearn fits (≈ 15 minutes). Holdout untouched (firewall engaged, window 2025-08-26 → 2026-08-28,
dataset ends 2025-05-09). No production change; nothing is promoted.

## 5. Recorded predictions

1. The gate passes.
2. `DEDUP` will move mean Rank IC by less than 0.005 and will be classified `EQUIVALENT`, with the difference
   comparable to the `NOISE` arm's (my probability ≈ 65%); the economics margin is the more likely one to fail
   (fold 5 dominates net Sharpe and reseeding moved it by 0.067 in EXP-009B).
3. No single-feature removal of one perfect twin will make the model better in any way I could defend.

## 6. Amendments

None.

Definition fingerprint: `434554c39aa382a7caeab80bfa3e8141883a188b343417569e52fa25d4104ef4`
