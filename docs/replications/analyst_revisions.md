# Replication candidate: analyst revision momentum

| Item | Assessment |
|---|---|
| Original evidence | [Analyst stickiness and stock return predictability](https://doi.org/10.1093/rof/rfag022), Review of Finance 2026; foundational revision literature |
| Hypothesis | Slow/sticky belief updates make recent forecast revisions informative for future cross-sectional returns |
| Original data | Analyst-level PIT forecasts, typically IBES-like, with analyst identities and revision dates |
| Target/model | Future stock returns; revision portfolios/regressions and stickiness model |
| Evaluation/result | Stronger predictability for sticky-analyst consensus revisions, particularly under forecast difficulty |
| Data we have | Weekly firm-level EPS/sales consensus vintages, range and contributor count, 2017-10-26 onward |
| Data we lack | Analyst identity/history, recommendation/target changes, intraday issue time |
| Feasible substitute | 4/13-week firm consensus revisions, dispersion and coverage already implemented |
| Exact reproduction | Direction and vintage construction of consensus revisions only |
| Approximation | Cannot identify sticky analysts or exact daily revision breadth |
| Compute/storage | LOW; current Parquet and feature builder; one fixed ablation |
| Complexity | LOW |
| Leakage risk | Fiscal-period rollover and stale consensus; existing tests guard both |
| Licensing risk | Local DoltHub license recorded as open; original IBES is academic/commercial |
| Recommended ID | One isolated data arm after `EXP-009-LTR` and turnover rule freeze |

EXP-005's estimate arm underperformed, so this replication has a cautious prior
and must not be presented as previously untested data.
