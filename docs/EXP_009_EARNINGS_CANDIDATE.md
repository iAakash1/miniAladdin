# EXP-009 candidate: earnings and PEAD

Status: candidate feature-family study; core features already implemented;
not run.

## Evidence

Earnings surprise and post-announcement drift are durable research families.
Recent [earnings-disclosure work](https://doi.org/10.1287/mnsc.2024.05417)
shows that contextual text adds information to numeric surprises, while a
2026 [PEAD study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7116238)
emphasizes fiscal-quarter heterogeneity. These findings support correct event
timing and focused ablation, not an immediate LLM text model.

## Local feasibility

`eps_history` has 168,473 period rows and `earnings_calendar` 117,601 events,
but calendar coverage starts 2020-01-22. The existing feature builder matches a
period forward to the first plausible announcement, makes BMO available that
session, shifts AMC/unknown to the next session, and drops unmatched periods.
It produces surprise, scaled surprise, SUE using prior observations only,
surprise sign and days since announcement. It deliberately cannot construct
days-to-next-earnings because the calendar lacks first-published schedule time.

## Candidate hypothesis

The existing event features improve ranking during a registered 1--63-session
post-announcement window, after controlling for base momentum, rather than
across every row. Compare base versus base + four earnings features in one
fixed model and report event-window IC/spread as secondary diagnostics.

Required safeguards: no same-close use after AMC; unknown session conservative;
no SUE denominator containing the current/future surprise; no event before
`available_from`; calendar coverage and fold counts disclosed. Guidance,
revenue surprise and text are absent and cannot be inferred.

The prior EXP-005 earnings/fundamental arm produced IC 0.0124 versus base
0.0290. A new study is justified only if it isolates earnings from contaminated
statements or changes the event-conditioned hypothesis, not to rerun the same arm.
