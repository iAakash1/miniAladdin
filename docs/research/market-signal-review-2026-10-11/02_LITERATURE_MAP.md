# Literature map

Counts come from `screening_log.csv` through `code/make_literature_map.py` and can be regenerated. Statements about what a work found are taken from its
abstract as recorded by the screener (`03_ANNOTATED_BIBLIOGRAPHY.md`); no full text was read, so findings are reported as the abstracts state them and not
independently checked. Coverage limits (OpenAlex partial, no SSRN, Scopus or Web of Science, three unscreened batches) are in `01_REVIEW_PROTOCOL.md`; every
statement that something is "thin" or "absent" is a statement about this search, not about the literature.

## What was found

2,011 records were screened: 1,028 included, 210 maybe, 773 excluded. 300 further records are unscreened. A record can belong to several of the twelve topic
families, so the family rows overlap.

| Family | Topic | Included + maybe | Relevance 3 | Peer-reviewed journal | Empirical | Median year | Share 2023-2026 |
|---|---|---|---|---|---|---|---|
| A | Return predictability, anomalies, factors | 535 | 89 | 242 | 375 | 2018 | 29% |
| B | Technical and price/volume signals | 271 | 18 | 145 | 176 | 2020 | 41% |
| C | Machine learning and learning-to-rank | 371 | 31 | 220 | 198 | 2024 | 74% |
| D | Time-series foundation models | 20 | 6 | 5 | 8 | 2026 | 100% |
| E | Financial language models and text | 192 | 24 | 67 | 102 | 2025 | 81% |
| F | Multimodal and alternative data | 143 | 12 | 75 | 84 | 2024 | 66% |
| G | Data fusion, reliability, point-in-time data, uncertainty | 138 | 27 | 57 | 62 | 2023 | 52% |
| H | Regimes, drift, signal decay | 153 | 22 | 58 | 102 | 2021 | 44% |
| I | Costs, portfolios, decision quality | 185 | 28 | 81 | 86 | 2023 | 53% |
| J | Research credibility and inference | 198 | 96 | 75 | 81 | 2020 | 40% |
| K | Cross-field reliability and fusion methods | 75 | 2 | 23 | 9 | 2025 | 68% |
| L | Datasets and benchmarks | 44 | 14 | 10 | 8 | 2025 | 66% |

| Period | Included + maybe |
|---|---|
| 1985-1999 | 61 |
| 2000-2009 | 142 |
| 2010-2019 | 271 |
| 2020-2022 | 168 |
| 2023-2026 | 596 |

| Publication status | Included + maybe | | Evidence type | Included + maybe |
|---|---|---|---|---|
| working paper or preprint | 632 | | empirical | 665 |
| peer-reviewed journal | 580 | | methodology | 366 |
| thesis or report | 10 | | unclear | 109 |
| peer-reviewed conference | 8 | | review or survey | 37 |
| unknown | 8 | | theory / benchmark / commentary | 28 / 28 / 5 |

Almost half the included records (596 of 1,238) are from 2023-2026, and 632 are preprints that have not been through review. That is a recency and
quality warning in itself: the newest evidence on machine learning, language models and foundation models is mostly unreviewed, and the review weights it that way.

## What the literature says, by theme

**Predictability is real but smaller and less stable than the first wave claimed (A, H, J).** Replication studies find that many published anomalies fail
under stricter breakpoints, value weighting and multiple-testing hurdles (Hou, Xue and Zhang, *Replicating Anomalies*, 452 anomalies; Harvey, Liu and Zhu on the
multiple-testing hurdle), that returns weaken after publication (McLean and Pontiff; judged from title and venue, no abstract was available), and, in a Bayesian multi-country replication, that most factors do replicate
once the hurdle is applied properly (Jensen, Kelly and Pedersen). Open code and data now reproduce several hundred predictors (Chen and Zimmermann). The
consequence for any new signal is a high bar for claims and a strong obligation to publish the whole search, which `docs/EXP_012_PREREGISTRATION.md` does.

**Machine learning improves forecasts mostly through nonlinearity and interactions, and its apparent size depends on design choices (C).** The canonical
comparison (Gu, Kelly and Xiu) and its no-arbitrage and deep-learning successors (Chen, Pelger and Zhu) report out-of-sample gains from nonlinear methods that
capture interactions, and a theory-and-evidence line argues that over-parameterised models help (Kelly, Malamud and Zhou). Replications in other markets exist, and one
reports that research-design choices across 5,376 portfolios create nonstandard errors up to five times the standard errors (Lalwani and co-authors, 2025). This is why EXP-012 keeps the model class, grid and cost
assumptions fixed from earlier registered experiments instead of tuning them.

**Language models: the main finding is a warning about look-ahead (E).** The strongest recent claim, that headline scores from a language model predict
returns using text published after the model's training cutoff (Lopez-Lira and Tang, *Journal of Financial Economics*, 2026), sits beside work showing that
backtests are contaminated when the model has seen the future (GPT sentiment look-ahead study; "Caution Ahead", 2026) and a position paper auditing 164
studies for such biases. Point-in-time language models are an active response. The lesson transfers directly to this project's design: every input must
be shown to have been public on the decision date.

**Data vintages and revisions are well studied for macro series and thin for firm-level data (G, L).** Real-time versus revised data changes out-of-sample
predictability in macro-finance (Guo, 2009: the consumption-wealth ratio forecasts less well in real time, a gap the author attributes to measurement error in unrevised data) and for inflation forecasts ("Forecasting in the Fog", 2026), and revision-aware time-series models appear
(Ahmad 2026; a vintage-consistent macro model). For company fundamentals, the closest works handle missing characteristics (Freyberger and co-authors,
imputation in a GMM setting) and delisting and survivorship bias (Shumway 1997). A study of *filing-level* amendments and reporting delays as predictors
inside a cost-aware machine-learning ranking was not found; see `06_PRIOR_ART_AND_NOVELTY.md` for how far that statement can be trusted.

**Disagreement and uncertainty are priced and moderate other signals (G, H).** Analyst forecast dispersion predicts lower returns (Diether, Malloy and
Scherbina), information uncertainty conditions price continuation (Zhang 2006) and post-earnings drift (Francis and co-authors, 2007), and the
disagreement of machine-learning forecasts itself predicts returns, including in options (Bali and co-authors, 2023, 2026). One recent paper shows that the
major investor-disagreement proxies are nearly uncorrelated with each other (Goulding, Harvey and Kurtovic, 2026), which is a measurement-reliability finding
about the *proxies*. This theme is the nearest established neighbour of "reliability conditions signal value", and it is why novelty is rated low-to-medium.

**Abstention and uncertainty-aware ranking exists (G, K).** A cross-sectional ranking study with a two-level uncertainty estimate and a decision of whether to
trade (Sanderink, 2026, preprint) is the closest abstention work; the transferable ideas from sensor fusion and truth discovery (K) are barely present in the
finance records (75 records, 9 empirical, 2 rated relevance 3).

**Costs and implementability decide many headline results (I).** Dynamic trading with predictable returns and costs (Garleanu and Pedersen), anomaly returns
concentrated where short fees or illiquidity bind, and net-of-cost Sharpe collapses are recurring findings. EXP-012's contrasts are reported gross for the
information-coefficient tests and net at 10 bp for the portfolio, as in the registered earlier experiments.

**Foundation models for returns (D).** Twenty records, all but a handful from 2025-2026 and mostly preprints, benchmark pretrained time-series models
against simple baselines. The evidence base is too young and too unreviewed to anchor a study.

## Gaps this review can state with its limits

1. **No archive of vendor disagreement or source health exists to study.** The literature on cross-source disagreement concerns analysts and forecasters, not
   data vendors, and OmniSignal's own database holds none (`07_RESEARCH_CANDIDATES.md`, verified 2026-10-12). Only a prospective logging protocol can create it.
2. **Disclosure-process reliability as a point-in-time, vendor-free measurement** (amendment history, lateness against the firm's own record, missed
   filings) tested as predictor and moderator in a placebo-controlled machine-learning pipeline: not returned by this search, which has a measured sensitivity
   of 77% against known anchors, so the gap is provisional.
3. **Firm-level restatement look-ahead inside ML pipelines** (training on restated values that were not public at the time): not found; the macro
   analogues are well documented. This was the first alternative candidate.
4. **Honest reporting of a null.** The credibility literature (J: 198 records, 96 rated relevance 3) argues for it; very few applied ML papers show one.

## Using this map

For the primary study: `docs/EXP_012_PREREGISTRATION.md`. For the nearest prior art and its comparison with the claim: `06_PRIOR_ART_AND_NOVELTY.md`.
For the family definitions: `code/screening_rubric.md`. For the 300 unscreened records: `recovery/classifier_assisted.csv`.
