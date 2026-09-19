# EXP-010B — horizon / rebalance-cadence study (results summary)

Status: **COMPLETE, immutable.** Validation-period evidence only. **No promotion.** Holdout (2025-08-26 → 2026-08-28):
**untouched** (`"touched": false`, firewall state `SEALED`).
Preregistration: [EXP_010B_PREREGISTRATION.md](EXP_010B_PREREGISTRATION.md) (commit `1797327`, fingerprint
`ff9eb7df02abe08f5f8bb3c2e162d872b8de58d9545ac1290fe498fcaded2133`). Outputs: `experiments/EXP-010B/`. Wall time 57.6 s.

## Disclosure that must travel with this result

**EXP-010B is not perfectly blind confirmatory evidence.** Before the interpretation thresholds were registered, one
exploratory prototype of the 21-session arm (B1) on **seed 0** was run on real data and its output was seen (net Sharpe
at 10 bp about 0.75, turnover about 2.34). The schedule, alignment and eligibility rules were fixed by the requirement
that B0 reproduce EXP-010A exactly, not by that output, and the thresholds are expressed in units of EXP-010A's noise
floor and sign counts. They were nonetheless written *after* that glimpse and cannot be called blind. The preregistration
records this in §2. The disclosure is permanent and applies to every reading of this result.

## Design

Two arms on the ten frozen EXP-010A prediction files, no retraining, no new label: **B0** rebuilds the book every 5
sessions (403 rebalances), **B1** every 21 sessions on the global trading calendar (96 rebalances). Everything else —
universe, top-k dropout (10%), long/short quintiles, commission, impact, half-spread grid — is identical. The signal at a
rebalance is the latest frozen prediction at least 5 sessions old. B0 reproduced EXP-010A's per-seed economics with a
maximum absolute gap of 0.0.

## Result (B1 − B0, paired by seed, all ten seeds)

| Metric (10 bp) | B0 mean | B1 mean | Median diff | Sample SD | Min | Max | Seeds better |
|---|---:|---:|---:|---:|---:|---:|---:|
| Net Sharpe | 0.352 | 0.641 | **+0.296** | 0.130 | +0.093 | +0.534 | **10 / 10** |
| Annualised one-way turnover | 6.876 | 2.332 | **−4.545** | 0.013 | −4.567 | −4.523 | 10 / 10 lower |
| Gross Sharpe | 0.511 | 0.699 | +0.202 | 0.124 | −0.013 | +0.425 | 9 / 10 |
| Net max drawdown | −0.167 | −0.117 | +0.046 (shallower) | 0.030 | −0.012 | +0.099 | 9 / 10 |
| Cost share of gross | 0.318 | 0.088 | −0.246 | 0.054 | −0.314 | −0.124 | 10 / 10 lower |
| Net CAGR | 4.1% | 7.5% | +3.0 pt | 2.0 pt | +0.7 pt | +6.6 pt | 10 / 10 |

Net Sharpe by seed (B0 → B1): 0.406→0.731, 0.377→0.743, 0.313→0.847, 0.329→0.707, 0.496→0.611, 0.200→0.412,
0.326→0.644, 0.439→0.712, 0.323→0.595, 0.314→0.407.

**Against the EXP-010A noise floor (descriptive only):** the median net-Sharpe gain is about 3.6 seed SDs (0.0817) and
1.35 p95 − p05 spans (0.2194); the turnover change is about 237 seed SDs. Even the smallest single-seed gain (+0.093)
is above one seed SD but below the p95 − p05 span, and every seed is positive.

**Preregistered label: `ECONOMICALLY_IMPROVED`** — turnover materially reduced (−66% median, lower in all ten seeds),
net-Sharpe status IMPROVED (median ≥ 0.0817, 10/10 positive), fold-robust (the worst leave-one-fold-out median gain is
+0.076, all above zero). The label describes this cadence comparison on this data; promotion is **NOT ASSESSED**.

## Fold heterogeneity exists

The improvement is not uniform. Median seed-level change in net Sharpe (B1 − B0) by fold:

| Fold | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Δ net Sharpe | +0.49 | −0.11 | +1.51 | +0.16 | +0.69 | +0.81 | **−0.43** | **−0.62** |
| Seeds positive | 10 | 3 | 10 | 6 | 8 | 10 | 0 | 0 |
| EXP-010A mean fold IC | −0.015 | +0.040 | +0.055 | +0.032 | −0.007 | +0.032 | +0.040 | +0.081 |

* B1 is worse in folds 1, 6 and 7 (the last two in **zero** of ten seeds), including the fold with the strongest ranking
  signal. Removing fold 5 leaves the gain positive but smallest (+0.076, 7/10 seeds positive).
* Fold-level Sharpes for B1 come from about 12 periods each and are noisy; they are context, not tests.

## What this does and does not support

Supports: at this signal quality, rebuilding every 21 sessions cuts turnover by about two-thirds and lowers cost drag
enough to raise validation-period net Sharpe in every seed, with a modestly higher gross Sharpe as well.

Does **not** support: any claim of guaranteed or expected profitability; any claim about the sealed holdout; promotion of
any model or portfolio; a claim that 21 sessions is *optimal* (no other cadence or start phase was tested, and none will
be in this research cycle); or a statistical-significance claim (date-sampling uncertainty is untested, B1 has 96
observations against 403, and its drawdown cannot see intra-period paths). Net Sharpe of about 0.64 on 96 monthly
periods is a validation-period number (out-of-sample predictions, but the portfolio design was developed with this period visible) on a survivorship-caveated universe (`docs/PIT_SECURITY_MASTER_PLAN.md`).

## The cadence question is closed for this research cycle

No 10/15/20/22/42-session cadence, alternative start phase or different dropout percentage will be tested. The frozen
21-session implementation is the downstream portfolio for EXP-011.

## Immutable artifact hashes (SHA-256)

| File | SHA-256 |
|---|---|
| `definition.json` | `3f75be834bed7e7486482cb0534ef28e3e00b134b2da6e422fe5dcee980d8e1c` |
| `config.json` | `0f63cde81f431fc76c64a75a74b611bb5e90daf03b1a447bf87a5446764b88d6` |
| `manifest.json` | `8a35fed732671f072eceb1c745074cd1cf7db890c05c26dcf1a13b5bb2e7e7d9` |
| `metrics.json` | `cb4b4d27313962c805390e5417b882604e491b5d968d3087a77962e113509f96` |
| `per_seed_cadence.csv` | `88a010efbd630111e1e8f318a48d6c9366ae0a27df76391af14ccad55ee8181c` |
| `fold_cadence.csv` | `9a9af00fe4616a36806b8f92862012c94abda7d73b1e4c51b368ac09011e6971` |
| `paired_differences.csv` | `ec23c32d2e47351a1cae90db774fcb407e25d9ee7559e2291ea113bf6c21351f` |
