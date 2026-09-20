# Next research decision (2026-09-20)

This note records where the research stands after EXP-011 and the two legitimate ways forward. **It does not choose between them.** That decision belongs to the owner.
No experiment is started, registered or run by this note; EXP-012 is not started.

## Where the evidence stands

| Study | Finding | Status |
|---|---|---|
| EXP-010A | Boosting reseed noise quantified: Rank IC seed SD 0.00158 (p95−p05 0.00416); net Sharpe seed SD 0.0817 (p95−p05 0.219). | complete |
| EXP-010B | The horizon-aligned 21-session portfolio improved validation net Sharpe in 10/10 seeds and cut turnover about two-thirds; three folds were worse; seed-0 prototype exposure disclosed. | complete, validation only |
| EXP-011 | `IMPROVES_ONLY_LINEAR`: the 50 PIT characteristics raised Ridge Rank IC (0.0053 → 0.0149) but produced **no detectable ordering gain** for the frozen boosting model (median ΔIC −0.0008), a worse covered-subset IC in 10/10 seeds, and lower validation economics than the frozen baseline. The linear gain is concentrated in folds 0 and 2 and reverses in fold 4. | complete, `docs/EXP_011_RESULTS.md` |

Nothing is promoted. The sealed holdout (2025-08-26 → 2026-08-28) is untouched. Standing data limits: `security_master_pit = false`; ALFRED `BLOCKED_EXTERNAL_FRED_KEY`; size and industry controls withheld;
foreign 10-K/10-Q-less issuers and unrecoverable delisted names have no new features; survivorship caveats apply.

## What the next cycle must not be

**It must not be "try more models until one wins."** EXP-011 held everything but the data fixed and found that the data did not help the model that performs best. Adding a model family, a neural network,
a tuned Ridge, a different boosting library, a different subset of the 50 features or a different fold set in response to that result would be a search through the validation period that the record is built to prevent:
every such variant is another look at the same eight folds, and a better number found that way would say little about the future. The cadence question is also closed (EXP-010B), as are dropout and cost changes.

## Direction A — Data-completion study

Finish the data that is currently missing or withheld, then test whether it matters, under a new preregistration.

1. **Historical security identity:** close the trusted-identity gap (91.8–95.0% by fold against the preregistered 95%): vendor-independent evidence for delisted or renamed names (currently 0.0–1.6% of name-dates unresolved) and a documented treatment of re-domiciled issuers.
2. **Foreign issuer / IFRS mapping:** a 20-F/40-F/IFRS tag map so the filers with no 10-K/10-Q (4.2–7.1% of name-dates) can have fundamentals, with the same acceptance-time discipline.
3. **Delisted-name evidence:** exit dates and identities for names that left the universe, so missingness stops correlating with delisting (currently 85.3% vs 93.6% trusted for names about to exit).
4. **PIT size and industry coverage:** once the master gate is met (thresholds unchanged), the seven withheld controls become admissible.
5. **ALFRED vintages:** obtain a FRED key and build vintage histories for the macro series in use, replacing revised-value leakage risk with real-time vintages.

Then **preregister a new experiment** (new ID, fingerprint, pushed before any run) testing the incremental value of the previously withheld controls — for example the seven size/industry-relative features — against the completed data, using the
frozen ordering rule style, the frozen boosting settings and the frozen 21-session portfolio, with the EXP-010A noise floor as the yardstick. Any threshold is fixed before results exist. This direction may conclude that the additional data still adds nothing; that is a valid outcome.

Cost and character: mostly data engineering; no new model search; the holdout stays sealed.

## Direction B — Final-candidate freeze

If the owner judges the current evidence sufficient to stop research and evaluate one candidate:

1. **Select one candidate specification using only already-declared evidence** — the evidence in the record (EXP-010A/B, EXP-011), not new fits. For orientation only: under the frozen 21-session portfolio both boosting specifications had positive validation net Sharpe at 10 bp in all ten seeds (baseline 0.41–0.85, mean 0.64; rich 0.41–0.58, mean 0.49); the baseline had the higher mean, the shallower mean net drawdown (−0.117 vs −0.185) and the shallower worst fold (−0.015 vs −0.042 Rank IC); the rich Ridge specification lost money. This note lists these facts and does not select a candidate.
2. **Freeze the entire pipeline:** data build, features, model settings, seeds, portfolio and costs, each with hashes and a fingerprint.
3. **Write the final holdout contract:** the single evaluation, the metrics, the pass/fail criteria and what will be reported whatever the result, committed and pushed before the holdout is opened (`docs/HOLDOUT_CONTRACT.md` is currently unarmed).
4. **Open the sealed holdout only later, with explicit user authorisation.** One shot; a failure is reported as a failure and is not followed by retuning.

Cost and character: little new computation; irreversible use of the holdout; a negative holdout result cannot be retried on the same window.

## The two are not exclusive in time, but the order matters

Direction A leaves the holdout sealed and can precede B. Direction B, once executed, uses up the holdout and ends the current research cycle. Choosing B before A means accepting the current data limits as the final data limits.

## Decision needed from the owner

Choose A, B, or A-then-B. Until a choice is made, no new experiment is registered, no model or feature is changed, and nothing is promoted.
