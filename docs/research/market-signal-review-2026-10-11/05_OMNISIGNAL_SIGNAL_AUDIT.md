# OmniSignal signal audit

Machine-readable registry: `signals.csv` (162 rows, built by `code/make_signals_csv.py`; the live rows import their weights from `src/scoring/engine.py`, so they cannot drift from the code).
Verified by reading code and tests on 2026-10-12. No product code was changed.

## What is in the registry

| Scope | Layer | Rows | Source |
|---|---|---|---|
| research only | transformed feature (57 registry definitions and 57 rich-panel characteristics, plus the 6 new reliability ranks) | 120 | `src/quant` feature registry and `docs/PIT_FEATURE_CATALOG.md`; exported by `code/export_signal_registry.py` |
| research only | raw variable (the 4 reliability variables) | 4 | `src/quant/pit/reliability.py` |
| research only | interaction (48 fundamentals x unreliability, one row for the family) | 1 | `src/quant/study/exp012.py` |
| live product | factor (6 momentum, 1 reversal, 4 fundamental, 3 quality, 1 news) | 15 | `src/scoring/engine.py` |
| live product | sleeve (momentum, fundamental, quality, news, reversal) | 5 | same |
| live product | macro gate | 1 | same |
| live product | risk component | 9 | same |
| live product | confidence deduction | 7 | same |

Each row records definition, hypothesis, inputs, source dataset, frequency, timestamp semantics, expected lag, missing-value semantics, normalisation, known failure modes, related literature, empirical status,
the experiments that used it, code references, redundancy notes, a verification note and a confidence label.

## Finding 1: the research stack is built to be point in time; the live scorer is a separate system

Every research row carries timestamp semantics and passes through the repository's availability rule, backed by leakage tests under `tests/quant`. The live scoring engine (`src/scoring/engine.py`,
812 lines) shares none of this: `src/quant` and `scripts` do not import it (checked by search; only a memory-profiling script mentions the module name). Consequences:

1. **No committed experiment evaluates the live composite.** Its weights (momentum 0.40, news 0.20, fundamental 0.20, quality 0.15, reversal 0.05, with a regime switch) are literature-anchored constants, never
   fitted (the module says so). `docs/FACTOR-AUDIT.md` audits it on three synthetic worlds and states that "cross-sectional panel validation on real data remains the final arbiter". That panel validation has
   not been done for the composite as built.
2. **Most of the live inputs cannot be replayed.** The fundamental, analyst, quality and news factors take provider snapshots at request time (P/E, forward P/E, analyst target and count, earnings surprise,
   gross profitability, issuance, asset growth, news sentiment). No history of those snapshots is kept, so no honest backtest of those sleeves is possible. Only the price-derived parts (momentum, reversal,
   the risk components) could be replayed from daily bars.
3. The research panel's baseline and rich features are different objects from the live factors (a ranked 26-feature baseline and 50 SEC-derived characteristics, versus t-statistic and prior-centred scores). Evidence
   about one does not transfer to the other without a bridging experiment.

## Finding 2: what the frozen research did establish (read, not recomputed; `docs/EXP_011_RESULTS.md`)

On the eight validation folds (404 dates, 100,246 predictions per arm):

| Arm | Mean Rank IC | HAC t | Positive folds |
|---|---|---|---|
| Ridge, 26 baseline features (E0) | 0.0053 | 0.36 | 6 of 8 |
| Ridge, 76 features with the SEC characteristics (E1) | 0.0149 | 1.35 | 7 of 8 |
| Boosted, baseline, 10 seeds (E2) | 0.0322 (seed SD 0.0016) | 2.92 | 6.1 |
| Boosted, 76 features, 10 seeds (E3) | 0.0317 (seed SD 0.0018) | 2.83 | 6.7 |

The SEC characteristics raise the linear model's ordering (+0.0096, positive in 6 of 8 folds) but do not help the boosted model; the boosted baseline is the strongest arm. Economics at 10 bp are in
`docs/EXP_010B_RESULTS.md`. Promotion is not assessed; the holdout is sealed. This is the evidence base for EXP-012, whose arms A0 and A1 reproduce E0 and E1 exactly as a gate.

## Finding 3: redundancy and weakness inside the live engine

From the synthetic audit (not real data): the trend factors form one cluster (12-1 and 52-week proximity correlate 0.86; 63-day and 21-day 0.82), so equal weighting inside the sleeve guards against counting one
component several times; MACD was removed from scoring for adding nothing; the reversal sleeve is destructive in trends and so is gated by volatility. These are reasonable design statements and
are not evidence about real returns.

## Finding 4: operational facts that bear on the signals (verified 2026-10-12)

| Item | Finding | How verified |
|---|---|---|
| Clerk sign-in | still a **development** instance (`caring-snipe-24.clerk.accounts.dev`, key kind test) | the production CSP header and sign-in HTML |
| News factor | the provider key is bound as a secret; the owner document records `apiKeyInvalid` as of 2026-10-09 | not re-tested: doing so needs the credential, which was not used |
| SEC contact | `SEC_USER_AGENT` is **not set** on the service, so the live SEC vendor sends its built-in generic agent, which is a placeholder contact | read-only listing of the service's variable names (values not read) |
| Build identity | GitHub `main`, Vercel production and Cloud Run revision `omnisignal-api-poc-release-1b3e6c7` (100% of traffic) all show `1b3e6c7` | `/api/build`, Cloud Run description |

## Recommendations (proposals, none enacted; the brief forbids production changes)

1. **A bridging experiment.** Register a separate experiment that replays the live engine's price-derived factors on the point-in-time panel and compares their rank IC and cost-aware performance with the frozen
   baselines. It would give the product a measured statement about its own score for the part that can be replayed, and make plain what cannot. It must be preregistered like EXP-012 and must not touch the holdout.
2. **Start an append-only archive of provider snapshots** (timestamp, provider, field, value, hash). It costs little, makes the fundamental and news sleeves replayable from the day it starts, and is the only way to
   create the history that the vendor-disagreement question needs (`07_RESEARCH_CANDIDATES.md`, section A). Design before building: privacy, licence terms of each provider, retention.
3. **Say what is not validated.** Wherever the interface shows the composite or its confidence, the validation state should read "mechanics tested; not validated on a point-in-time panel" until recommendation 1 is done.
4. **Owner actions already documented** (`docs/OWNER_ACTIONS.md`): move Clerk to a production instance, provide or disable the news key, set `SEC_USER_AGENT` to a real contact. Setting the SEC contact is also the right
   place to resolve a point this review raises: the account email should not be placed in scholarly-API headers, and the SEC asks for a contact, so the owner should choose which address to publish.
