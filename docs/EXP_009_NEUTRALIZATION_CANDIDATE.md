# EXP-009 candidate: sector, size and beta controls

Status: prerequisite data missing; not run.

## Hypothesis

The model should rank security-specific expected return rather than rediscover
sector, size or market-beta exposures. Neutralization may improve stability and
capacity, but can also remove genuine priced information, so both predictive
target and portfolio exposure effects must be measured.

## Candidate comparisons

1. Raw `fwd_rank_21` control.
2. Sector-relative within-date rank.
3. Residual rank after cross-sectional sector fixed effects and log market cap.
4. Portfolio-only exposure neutralization with the raw target.

Beta residualization is a secondary candidate, not an automatic fourth target.
Adding all target variants and portfolio variants creates a factorial search;
the final registration must cap and count cells explicitly.

## PIT requirements

- Sector/industry mapping with effective-from/to dates.
- PIT shares outstanding and close for market cap; no current shares backfill.
- Trailing beta estimated only from prior returns, with minimum history.
- Delisted names and identifier changes retained.

The frozen artifact lacks sector and PIT market cap, so dependence cannot be
measured honestly today. Current symbol metadata begins 2017-10-26 and is not a
complete historical sector master. This candidate is blocked until that layer
exists.

## Metrics

Rank IC/t/ICIR against each declared target, raw-return spread, sector/size/beta
exposure, concentration, turnover, gross/net Sharpe, fold/regime stability and
cost sensitivity. Neutralized IC cannot be compared to raw IC without also
showing the raw economic portfolio.
