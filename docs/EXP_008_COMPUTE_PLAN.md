# EXP-008 compute plan

Plan date: 2026-09-19. **Planning only; no training was run.**

## Host and capacity

| Resource | Observed |
|---|---|
| Host | MacBook Pro, Apple M4 Pro |
| CPU | 12 cores (8 performance, 4 efficiency) |
| Memory | 24 GB |
| Free workspace volume | about 17 GiB at planning time |
| Prior benchmark | EXP-007: 873 configs, 5 single-thread workers, 9.87 h wall, 45.6 worker-hours |

Disk headroom is the immediate operational constraint. EXP-008 must reuse the
raw data and write only a versioned label column, predictions, metrics and
logs. Preflight must refuse to start below 10 GiB free or if the worktree is
dirty without recording a patch hash. No dataset copy is permitted.

## Implementation work (no fit)

1. Add `fwd_rank_5` and its leakage/truncation tests.
2. Add the allocator interface to the backtest and bit-for-bit equal-weight
   reproduction test.
3. Register EXP-008 with `search_budget=None` and exactly five declared cells.
4. Extend the artifact schema for allocator, target, dataset hash, source
   commit/patch hash, dependency lock hash, worker policy and trial ledger.
5. Run unit tests and a dry plan that builds no model.

Estimated engineering time: one to three focused days. This is a planning
estimate, not measured effort.

## Execution policy after approval

- Prefer 2 single-thread workers initially to leave memory for panel joins and
  macOS. Increase only after a dry memory profile; worker count may not change
  numerical ordering or results.
- Pin BLAS/OpenMP threads to 1 per worker.
- Run H1 once; generate all H2 allocator outputs from the one already-frozen
  prediction stream where the design permits, rather than refitting four
  predictive models.
- Checkpoint each completed declared cell atomically. Resume skips completed
  fingerprints and cannot generate replacement cells.
- Keep the machine on power; record thermal interruption, crash, or retry.

Using the EXP-007 average of roughly 188 worker-seconds per configuration as a
lower-bound reference, five cells are not an overnight model search. Dataset
build, covariance construction, backtest, diagnostics, and conservative I/O
allowance dominate. Budget **1--3 wall-clock hours** and less than 5 GiB new
working space. This is deliberately a range; the allocator path is not yet
implemented and no benchmark is fabricated for it.

## Dry-run and run gates

Before any confirmed run, the dry plan must print:

- experiment fingerprint and exactly five cells;
- dataset/source/lock/commit hashes;
- holdout dates and firewall status;
- fold geometry, label horizon, purge, embargo, execution lag and costs;
- projected workers, memory and disk;
- cumulative trial count 1,034 and null max-|t| 3.39.

Abort on a sixth cell, hash mismatch, unavailable equal-weight reproduction,
holdout intersection, fewer than 10 GiB free, unrecorded dirty source, or a
dependency-lock mismatch.

After an authorized run, verify cell count and fingerprints, reproduce summary
metrics from raw predictions, run the complete test suite twice, and commit
results separately from implementation. Do not automatically arm the holdout
or promote anything.
