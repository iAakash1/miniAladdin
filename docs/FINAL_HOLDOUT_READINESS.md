# Final holdout readiness — NOT READY

Date: 2026-09-20  
Holdout: 2025-08-26 through 2026-08-28  
State: **SEALED / UNTOUCHED**

No holdout row has been read, no contract has been armed, and no model is promoted. This document records readiness only; it grants no authority to open the holdout.

## Completed prerequisites

- Foreign reporting-currency curation is filing-global, deterministic, real-data chunk invariant, and validates with zero multi-currency filings.
- Repaired Rich PIT v2 is immutable as `ds-richpit2-6368cccdb94c62d0`; its frozen 76-feature block has zero changed cells.
- The 18-column foreign block passes its frozen admission gate.
- Size/industry controls remain withheld under the unchanged market-cap gate.
- ALFRED remains `BLOCKED_EXTERNAL_FRED_KEY`; nothing was substituted.
- Manual audit and all used v4 integrity checks pass. Identity remains transparently PARTIAL for retrospective grade stability.

## Blocking scientific question

The EXP-011 revenue-definition issue is not yet resolved. The outcome-blind shadow audit found:

- 393 multi-candidate annual filings;
- 171 filings with an unambiguously different total-revenue candidate;
- 100 filings that remain `REVENUE_AMBIGUOUS`;
- 4,256 EXP-011 name-dates with a different attached revenue-dependent snapshot;
- 981,502 changed cross-sectional feature cells after same-date rank propagation;
- all 14 revenue-dependent frozen features affected;
- zero changed cells when reproducing the uncorrected frozen pipeline.

Classification: `UNRESOLVED_MAPPING_IMPACT`.

EXP-011 remains an immutable result of its declared v3 pipeline. However, it cannot support final-candidate selection without an explicit decision about a newly registered corrected-data replication. No post-hoc materiality threshold is introduced here.

## Decision

**Do not prepare or run EXP-012. Do not arm or open the final holdout.**

The next authorized research action is a governance decision: preregister a corrected-data EXP-011 replication under a new experiment ID, or provide a documented scientific rationale for another path. Any replication must freeze its reconciliation rule, dataset, feature hash, arms, folds, seeds, interpretation, and trial-history treatment before any fit.

Confirmed: zero EXP-012 fits, zero EXP-011 reruns, zero holdout access, zero feature or hyperparameter search.

