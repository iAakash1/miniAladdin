# EXP-009 candidate: date-grouped learning to rank

Status: design candidate only; not preregistered, implemented, or run.

## Evidence

[Poh et al.](https://arxiv.org/abs/2012.07149) report material gains from
pairwise/listwise ranking in cross-sectional strategies, and
[Zhang, Wu & Chen](https://arxiv.org/abs/2104.12484) propose a listwise loss
that emphasizes both tails of a long/short portfolio. A 2026
[35-market target study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615698)
finds ordinal targets strong on average, but warns that ranks discard magnitude
information. These are credible reasons to test LTR, not promises that it will
beat EXP-007 in liquid US equities after cost.

## Candidate hypothesis

On identical folds, features and costs, a date-grouped rank objective produces
more stable out-of-sample ordering than point regression and either improves
net economics or demonstrates that objective mismatch is not binding.

## Unit of ranking

- Query/group: one rebalance date.
- Items: PIT-universe stocks eligible on that date.
- Continuous reference target: `fwd_rank_21`.
- Ranker relevance label: preregistered within-date ordinal bins, e.g. five
  ordered levels 0--4. Boundaries and tie behavior must be frozen before fit.
- Never pass the whole panel as one group; never allow a group across dates.

## Candidate cells

1. Frozen EXP-007 selected HGB point-regression control.
2. LightGBM `lambdarank`, one fixed configuration.
3. XGBoost `rank:pairwise`, one fixed configuration.

Do not tune either ranker. If dependency/implementation reproducibility cannot
pin deterministic CPU results, drop that model before registration rather than
replace it after viewing metrics. NDCG@top/bottom is diagnostic only; it is not
the promotion metric.

## Evaluation

Inherit the existing PIT universe, eight walk-forward folds, 21-session purge,
five-session embargo, one-period lag, five-session cadence, 10 bp primary
half-spread and sealed holdout. Report Rank IC/t/ICIR, fold dispersion, top-
minus-bottom gross/net spread, net Sharpe/Sortino/drawdown, annual turnover,
cost curve, rank autocorrelation, quintile retention, sector/size/beta exposure
when the PIT security master exists, PBO and deflated Sharpe.

## Risks and stop rule

LTR labels are an additional transformation, group sizes vary, and optimizing
top-heavy relevance can destabilize the bottom book. Stop the objective line if
neither ranker improves worst-fold IC and rank stability without worsening net
Sharpe or turnover. Do not tune NDCG cutoffs to rescue a negative result.

Expected compute: CPU, <24 GB RAM, hours rather than days for three fixed cells;
exact time requires a dry benchmark. Storage is predictions/metrics only,
likely <2 GB. Licensing risk is low for algorithms and unchanged for inputs.
