# EXP-009 candidate: options-implied information

Status: deferred candidate; existing features implemented; not run.

## Evidence

Options can encode forward-looking distributional information, but the evidence
is mixed. [Honarvar & Howard](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4766424)
find a marked post-2008 decline and show that correcting non-synchronous stock/
option observation reduces earlier predictability. [Neuhierl et al.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3795486)
find few option characteristics incremental to firm characteristics. Deep IV-
surface papers use proprietary contract histories and are not close replications.

## Local feasibility

Normalized data spans 2019-02/05--2026-08. `volatility_history` has 691,007
rows/745 symbols; daily chain aggregates have 1,918,396 rows/2,317 symbols.
There are no duplicate date/symbol keys. Cadence is irregular; optionable-name
membership is a size/liquidity selection. ATM IV is 28.58% missing in the chain
aggregate and near/far IV 38.26%/52.74% missing. No volume or open interest is
available.

Already implemented: IV level/rank/month change, IV/HV ratio, coarse 25-delta
skew, term slope, relative spread and expiration count, joined latest-on-or-
before with a 21-day staleness cap. Vendor IV/Greeks methodology is unpublished.

## Candidate design if later authorized

Use one fixed base-versus-base+options ablation, restrict to names/dates with
declared liquidity/coverage, and run both (a) common-universe comparison and
(b) missing-aware full-universe comparison. Synchronize the option snapshot no
later than the equity prediction cutoff; holiday/weekend snapshots map only to
the next tradable decision. Report coverage-conditioned exposure and the loss
of pre-2019 folds.

Do not implement put/call volume, OI change, dealer gamma, exact 30-day IV or
surface CNNs from these aggregates. The prior EXP-005 options arm IC 0.0275 was
below base 0.0290. Options are therefore not a top-three EXP-009 ingredient.
