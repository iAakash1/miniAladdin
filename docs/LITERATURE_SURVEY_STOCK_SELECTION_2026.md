# Literature survey: cross-sectional stock selection, 2026

Search cutoff: 2026-09-19. Scope: cross-sectional return ranking/selection,
learning to rank, probability/distribution forecasts, alternative data, and
net portfolio construction. This is a decision survey, not a claim that every
working paper has survived peer review. Of the 34 works below, 25 are dated
2024--2026 (18 from 2024, 3 from 2025 and 4 from 2026); 9 are foundational
2014–2023 works. Peer-reviewed work is separated from working/preprint evidence.

## Verification addendum (2026-09-19)

Rows below were re-read against primary sources in
`docs/DEEP_METHOD_RECONSTRUCTION.md`; that document is authoritative where the
two differ. Corrections made in place in this file: the ListFold code link
(the named repository does not exist), the ListFold and Poh et al. market and
data descriptions, and the JKMP publication status. Corrections that are
qualifiers rather than replacements are listed here:

- **Poh et al.** "roughly threefold Sharpe improvement" holds for the paper's
  *gross-of-cost*, monthly, NYSE 1980-2019, momentum-only, volatility-scaled
  table against heuristic/MLP baselines. It is not a net result.
- **Zhang, Wu & Chen** used 80 survivor-filtered A-share stocks; costs (30 bp)
  were charged; weekly turnover 0.39-0.48 (ranking loss did not lower it).
- **Gu, Kelly & Xiu**: no transaction costs are charged; the authors do link
  a repository (simulation code only) and a public characteristic dataset.
- **Azevedo et al.**: the "57%" figure could not be verified; the abstract's
  headline is that ML strategies remain profitable net.
- **Bianchi & Zheng**, **Chen-Hanauer-Kalsbach**, **Brownlees & Souza**: primary
  text unreachable (SSRN HTTP 403); their figures are UNVERIFIED and must not
  be cited as fact.
- **Post-EXP-009 evidence:** the turnover hypothesis reproduced (top-k dropout
  cut turnover 66%), but ranking losses and aggregate analyst revisions did not.
  Those outcomes update implementation priority; they do not rewrite the
  preregistered studies or the papers.

## Method

Searches combined `cross-sectional stock returns`, `machine learning`,
`learning to rank`, `probability forecast`, `options`, `earnings`, `analyst
revisions`, `turnover`, and `transaction costs`. Primary publisher, DOI,
author, SSRN, or arXiv pages were preferred. A paper is HIGH evidence only
when peer reviewed with broad data and credible out-of-sample evaluation;
MEDIUM is a substantial working paper or narrower published study; LOW is an
unreviewed, narrow, or presently hard-to-replicate preprint. Working papers
can motivate a preregistered test but cannot establish production readiness.

## Evidence matrix

Abbreviations: CS = cross-sectional; OOS = out of sample; TC = transaction
costs; LTR = learning to rank; NN = neural network.

| Work (link) | Year/status | Objective, data/universe | Model/evaluation/TC | Main result and limitation | OmniSignal relevance / quality |
|---|---|---|---|---|---|
| [Gu, Kelly & Xiu, Empirical Asset Pricing via ML](https://doi.org/10.1093/rfs/hhaa009) | 2020, RFS | Monthly US CS returns; ~30k stocks, 1957--2016, 94 characteristics | Trees and NNs; rolling OOS; portfolio tests | Nonlinear ML improves forecasts; momentum, liquidity and volatility dominate. Historical sample and implementation costs remain consequential. | Core benchmark for model/feature comparison; HIGH |
| [Chen, Pelger & Zhu, Deep Learning in Asset Pricing](https://doi.org/10.1287/mnsc.2023.4695) | 2024, Management Science | Return/risk-premium structure in broad US equities | Adversarial/deep conditional models; OOS asset-pricing tests | Flexible latent factors capture nonlinear structure. Complex, compute-heavy, not a direct low-turnover selector. | Cautions against equating model fit with deployable ranking; HIGH |
| [Avramov, Cheng & Metzker, ML vs. Economic Restrictions](https://doi.org/10.1287/mnsc.2022.4449) | 2023, Management Science | CS US returns with economic restrictions | ML with/without restrictions; OOS portfolios | Economic structure can improve ML reliability. Exact benefit depends on restriction and period. | Supports sector/size/risk controls; HIGH |
| [Kelly et al., Virtue of Complexity](https://doi.org/10.1111/jofi.13298) | 2024, Journal of Finance | Return prediction with large characteristic sets | Complex predictors; OOS tests | Complexity can help when regularized and evaluated correctly. Does not waive TC or multiple-testing concerns. | Test parsimonious complexity, not an unrestricted search; HIGH |
| [Bagnara, Asset Pricing and ML: a critical review](https://doi.org/10.1111/joes.12532) | 2024, Journal of Economic Surveys | Review of ML asset-pricing evidence | Critical synthesis | Gains are sensitive to design, data, and economic evaluation. | Governance and evidence standard; HIGH |
| [Factor Models, ML, and Asset Pricing](https://doi.org/10.1146/annurev-financial-101521-104735) | 2022, Annual Review of Financial Economics | Review of modern factor/ML methods | Survey | Connects flexible prediction with factor interpretation and identification limits. | Baseline taxonomy and caveats; HIGH |
| [Chen, Hanauer & Kalsbach, Design Choices, ML, and CS Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5031755) | 2024, rev. 2026, working paper | 1,000+ model/design combinations in CS stock returns | Large controlled comparison; OOS portfolios | Preprocessing, targets, and portfolio rules are first-order. Still a working paper and huge search space. | Direct reason to isolate objective and turnover effects; MEDIUM |
| [Han, He, Rapach & Zhou, New Fama-MacBeth Regressions in the Era of ML](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3185335) | 2024, Review of Finance forthcoming | About 200 characteristics, US equities | Regularized Fama-MacBeth and forecast combinations; OOS | Regularization and combinations improve stable CS forecasts. | Strong linear/combination baseline; MEDIUM-HIGH |
| [Barunik, Hronec & Tobek, Forecasting Stock Return Distributions Around the Globe](https://arxiv.org/abs/2408.07497) | 2024, rev. 2025, preprint | International firm-level return distributions | Quantile NNs; global OOS tests | Full distributions expose asymmetric opportunities/risk. Complex calibration and TC implementation remain. | Later-stage uncertainty-aware EXP-009-or-later candidate; MEDIUM |
| [Brownlees & Souza, How To Bet On Winners (and Losers)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5352643) | 2025, working paper | Winner/loser decisions rather than conditional mean | Classification/statistical decision framing | Decision-aligned losses can outperform mean regression for selection. Review pending. | Direct support for rank/classification objective test; MEDIUM |
| [He, Lv & Zhou, Empirical Asset Pricing with Probability Forecasts](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4717935) | 2024, working paper | Probability of relative return outcomes | Probability forecasts, OOS portfolios | Probability framing can improve portfolio decisions. Calibration and search choices matter. | Candidate after ranking baseline; MEDIUM |
| [Girardi, Koerber & Schlag, Nonlinearities and Pricing Complexity](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5502838) | 2024, working paper | Nonlinear CS relations | Flexible ML/OOS comparison | Nonlinearity is heterogeneous rather than universally valuable. | Supports restrained model family; MEDIUM |
| [Azevedo, Hoegner & Velikov, Expected Returns on ML Strategies](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4702406) | 2024, rev. 2025, working paper | Published/implementable ML strategies | Post-publication and TC analysis | The abstract reports that selected sophisticated strategies remain profitable net; exact decay decomposition was not verified. | Supports net-first evaluation without supplying an OmniSignal prior; MEDIUM |
| [Chin, ML and the Cross-Section of Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4282614) | 2022, rev. 2026, working paper | Technical indicators and rolling US CS prediction | ML with rolling retraining | Technical inputs can contain OOS rank information. Revision history and publication status limit certainty. | Comparable feature family; MEDIUM-LOW |
| [Chin & Lin, ML and Technical Analysis in International Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6579120) | 2024, posted 2026, working paper | International equities/technical indicators | ML/OOS country tests | Tests portability of technical ML. Recent posting and reproducibility pending. | Regime/generalization context; LOW-MEDIUM |
| [Honarvar & Howard, Better Opt Out](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4766424) | 2024, working paper | Options-implied signals for underlying returns | Corrected synchronization and subperiod tests | Predictability weakens post-2008 and after look-ahead correction. | Strong warning against prioritizing costly options ingestion; MEDIUM |
| [Neuhierl, Tang, Varneskov & Zhou, Do Option Characteristics Predict Underlying Stock Returns?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3795486) | 2021, rev. 2024, working paper | US equity options and firm characteristics | Incremental CS tests | Few option characteristics add incremental power after firm characteristics. | Options should be a later ablation, not foundation; MEDIUM |
| [Kelly et al., Deep Learning from Implied Volatility Surfaces](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4531181) | 2023, rev. 2026, working paper | Proprietary option surfaces | CNN ensembles; OOS portfolios and costs | Surface shape contains predictive information. Proprietary data and complex filters impair replication. | Feasible only after contract-level data/license upgrade; MEDIUM |
| [Ye et al., IV Surface and the Cross-Section](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6890048) | 2026, preprint | Option IV surfaces and stock returns | Surface representation/ML | Reports CS predictability; too new for strong reliance. | Watchlist item; LOW |
| [Ke & Wang, Risk-Neutral Higher Moments](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4777204) | 2024, rev. 2026, working paper | Option-implied higher moments | CS portfolio sorts/regressions | Higher moments may price tail information. Vendor/method dependence is material. | Possible interpretable options features later; MEDIUM-LOW |
| [Siano, News in Earnings Announcement Disclosures](https://doi.org/10.1287/mnsc.2024.05417) | 2025, Management Science forthcoming | Earnings disclosures/text | LLM-based disclosure measures; return tests | Structured text adds information around earnings. Implementation requires exact filing-time text. | Supports SEC 8-K/exhibit corpus; MEDIUM-HIGH |
| [He & Zhang, Cross-Sectional Spillovers of Earnings Surprises](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5415255) | 2025, working paper | Earnings call/transcript relationships | Embeddings/network spillovers | Peer information can augment own-firm surprise. Transcript licensing and timing are hard. | Later relational event feature; MEDIUM |
| [Avramov et al., Dual Industry Effects and Cross-Stock Predictability](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4849902) | 2024/25, working paper | Industry/customer-like cross-stock links | Network/industry predictors | Cross-stock structure may predict returns. Definition stability and data dependence matter. | Supports PIT sector/network controls; MEDIUM |
| [Kwon, Lee & Yoo, Disagreement versus Uncertainty](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4921479) | 2024, rev. 2026, working paper | Analyst forecast distributions | Disagreement/uncertainty decomposition | Distinguishing disagreement from uncertainty can matter for returns. | Motivates careful estimate-revision features; MEDIUM |
| [Listwise Learning-to-Rank for Long-Short Portfolios](https://arxiv.org/abs/2104.12484) | 2021, preprint | Direct stock ranking for long/short selection | Listwise LTR; portfolio evaluation | Aligns loss with ordering rather than point error. Narrow/preprint evidence and cost sensitivity. | Direct EXP-009 objective precedent; MEDIUM-LOW |
| [Interpretable Stock Selection with LambdaMART and SHAP](https://www.sciencedirect.com/science/article/pii/S1938025922000073) | 2022, journal article | Stock selection/ranking | LambdaMART plus SHAP | Demonstrates ranked selection and interpretation. Setting and external validity are limited. | Implementation precedent, not performance prior; MEDIUM |
| [Celeny et al., Cyber Risk and the Cross-Section of Stock Returns](https://arxiv.org/abs/2402.04775) | 2024, preprint | 7,059 US firms, 60,470 SEC 10-Ks, 2007–2022 | doc2vec DM/DBOW trained with MITRE; quarterly value-weight sorts; no implementation-cost analysis found | Filing text creates a distinct risk score and positive high-minus-low portfolio in the sample. CRSP/Compustat inputs remain licensed and result is not a 21-day selector. | Strong lawful SEC-text construction precedent; MEDIUM-LOW |
| [Qian et al., MDGNN](https://arxiv.org/abs/2402.06633) | 2024, preprint | Graph-based stock movement prediction on public benchmarks | Multi-relational dynamic GNN | Graph relations improve benchmark movement forecasts. Benchmark differs from liquid-US rank economics. | Defer until simpler relational controls pass; LOW-MEDIUM |
| [Poh, Lim, Zohren & Roberts, Building Cross-Sectional Strategies by LTR](https://arxiv.org/abs/2012.07149) | 2020, preprint | Cross-sectional momentum across instruments | Pairwise/listwise ranking; OOS trading | Reports roughly threefold Sharpe improvement over traditional ranking in its setting. Preprint, portability and cost detail constrain the prior. | Strong LTR precedent; MEDIUM |
| [Jensen, Kelly, Malamud & Pedersen, Implementable Efficient Frontier](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4187217) | 2026, Review of Financial Studies (2024 working-paper version) | ML portfolio weights under trading costs | Economic objective and cost-aware optimization | Directly learns implementable weights and economic feature importance. Official code reports 25–75 GB/job on Slurm; exact run is infeasible here. | Strong net-objective principle; exact replication rejected; MEDIUM-HIGH |
| [Cakici & Zaremba, Getting the Target Right](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615698) | 2026, preprint | 35 markets, 1994--2024 | Raw versus ordinal/rank targets | Ordinal targets nearly triple predictive accuracy and double portfolio returns on average, but lose magnitude information in high-dispersion/skewed settings. | Direct target evidence; MEDIUM |
| [Bianchi & Zheng, Posterior Uncertainty in Portfolio Policies](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6359140) | 2026, preprint | Characteristic-based portfolio policies | Bayesian NN position intervals/no-trade rule | Primary text was unavailable; numerical turnover claims remain **UNVERIFIED** and are not used. | No-trade concept only; LOW pending verification |
| [Analyst Stickiness and Stock Return Predictability](https://doi.org/10.1093/rof/rfag022) | 2026, Review of Finance | Analyst-level forecast revisions | Sticky-analyst consensus revision | Sticky analysts' revisions predict more strongly, especially under forecast difficulty. Requires analyst-level IBES-like history absent locally. | Validates revision family, not directly reproducible; HIGH |
| [Campbell et al., Expectations Matter](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4495297) | 2024, working paper | Firm earnings forecasts | ML forecasts versus analysts | About 90% of evaluated ML specifications fail to beat analysts; best models correct nonlinear analyst biases. | Warns against assuming richer model beats consensus; MEDIUM |

## Required-field paper register

This register makes unavailable evidence explicit. `NR` means not verified in
the primary public record reviewed; it is not a negative claim. “Data available”
means sufficient raw data for full replication, not merely a sample or schema.

| Paper | Year | Venue | Market | Universe | Period | Target | Data | Features | Model | Validation | Costs | Primary result | Code available? | Data available? | Point-in-time? | Key contribution | Weakness / limitation | Relevance to OmniSignal |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gu, Kelly & Xiu | 2020 | RFS | US | CRSP common stocks, ~30k names | 1957--2016 | next-month excess return | CRSP/Compustat | 94 chars + macro interactions | linear, trees, NN | rolling/expanding OOS | portfolio costs discussed; full replication assumptions material | nonlinear models improve OOS CS prediction | No official code verified; community replications exist | No, WRDS inputs licensed | Publication-lag construction; exact vendor vintages licensed | Canonical ML comparison | Historical and expensive proprietary panel | Benchmark models/features |
| Chen, Pelger & Zhu | 2024 | Management Science | US | broad equities/assets | long US sample | SDF/risk-premium moments | firm + macro | characteristics and macro states | FFN/GAN | train/validation/test OOS | not directly a retail execution study | nonlinear SDF improves pricing tests | [Author repository](https://github.com/LouisChen1992/Deep_Learning_in_Asset_Pricing) | No, core market/fundamental inputs licensed | Mixed; depends on source construction | Deep conditional asset-pricing framework | Not direct stock-ranking objective | Complexity/authority caution |
| Avramov, Cheng & Metzker | 2023 | Management Science | US | common equities | NR | future return | CRSP/Compustat-style | firm chars + economic restrictions | regularized/ML | temporal OOS | portfolio tests | restrictions can improve ML robustness | NR | No | Research design aims PIT; exact vintages NR | Combines economics and ML | Not a low-turnover recipe | Neutralization/constraints |
| Kelly et al., Virtue of Complexity | 2024 | Journal of Finance | US | broad equity characteristic panel | long historical | future return | licensed asset-pricing panel | many characteristics | high-complexity regularized predictors | OOS | economic portfolios | complexity helps under regularization | NR | No | NR | Explains useful complexity | Implementation/search sensitivity | Restrained nonlinear candidate |
| Bagnara review | 2024 | Journal of Economic Surveys | multi | literature | through review cutoff | n/a | published studies | n/a | review | evidence synthesis | reviews cost/evaluation limits | gains depend on design and data | n/a | n/a | n/a | Critical synthesis | No new empirical test | Evidence standard |
| Factor Models, ML, Asset Pricing | 2022 | Annual Review of Financial Economics | multi | literature | through review cutoff | n/a | published studies | n/a | review | evidence synthesis | discusses economic tests | unifies factors and ML | n/a | n/a | n/a | Taxonomy | Predates newest methods | Method framing |
| Chen, Hanauer & Kalsbach | 2024/26 | SSRN preprint | US | NYSE/AMEX/Nasdaq; avg ~2,093/month, excludes microcaps | 1957--2021 | excess/market-/factor-adjusted return variants | CRSP + OSAP | 207 anomaly predictors | >1,000 linear/nonlinear designs | expanding/rolling OOS, 1987--2021 test | top-bottom portfolios; cost treatment not primary contribution | design non-standard error exceeds statistical SE by 59% | NR | OSAP partly open; CRSP licensed | Lagged characteristics; vendor PIT details not fully public | Controlled design multiverse | Large multiple-design space; preprint | Strongest design-choice warning |
| Han, He, Rapach & Zhou | 2024 | Review of Finance forthcoming | US | CRSP equities | NR | next-period CS return | CRSP/characteristics | ~200 characteristics | regularized Fama-MacBeth, combinations | temporal OOS | portfolio evaluation | regularization/combinations stabilize forecasts | NR | No | NR | Modernizes interpretable linear baseline | Final publication/data details pending | Required baseline |
| Barunik, Hronec & Tobek | 2024/25 | arXiv preprint | global | WRDS + LSEG international equities | source files span 1926--2023; study windows vary | return quantiles/distribution | CRSP, Compustat, IBES, DataStream/Worldscope | firm, estimate, market predictors | quantile NN; GB/RF checks | international temporal OOS | portfolio analytics | distribution forecasts reveal asymmetric opportunities | [Author replication](https://github.com/ondrejtobek/quantile-neural-networks) | Partly; licensed core omitted | Uses historical tables; full PIT replication needs licenses | Distributional prediction | Proprietary inputs and complex calibration | Later uncertainty work |
| Brownlees & Souza | 2025 | SSRN preprint | NR | equities | NR | winner/loser decision | firm/return predictors | NR | classification/decision rules | OOS | economic decision evaluation | decision-aligned framing can beat conditional-mean framing | NR | NR | NR | Aligns loss and action | Preprint; public details limited | Rank/classification motivation |
| He, Lv & Zhou | 2024 | SSRN/AFA working paper | US | 31,492 unique NYSE/AMEX/Nasdaq stocks | 1957--2020; OOS 1987--2020 | probability of return event | CRSP + characteristics | 94 firm chars | probability models vs expected-return models | expanding, annual refit | portfolio/factor augmentation | probability forecasts add information | NR | No, CRSP licensed | Lagged annual/characteristic construction | Probability rather than mean | Working paper; calibration choices | Secondary target candidate |
| Girardi, Koerber & Schlag | 2024 | SSRN preprint | NR | equities | NR | future CS return | characteristic panel | firm chars | nonlinear ML | OOS | portfolio tests | nonlinear value is heterogeneous | NR | NR | NR | Studies complexity heterogeneity | Public metadata insufficient for replication | Avoid automatic deepening |
| Azevedo, Hoegner & Velikov | 2024/25 | SSRN preprint | US | ML strategies | publication-era sample | strategy returns | published strategies/data | model signals | replication/meta analysis | post-publication OOS | explicit TC/decay | reported combined erosion about 57% | NR | Mixed | Study-specific | Quantifies implementation decay | Working paper, strategy heterogeneity | Net-first promotion |
| Chin | 2022/26 | SSRN preprint | US | equities | NR | future CS return | prices/technical indicators | technical family | ML families | rolling OOS | portfolio tests | technical ML retains some OOS rank information | NR | NR | Price data naturally PIT if corrected | Focused technical test | Long revision history/unreviewed | Comparable to current features |
| Chin & Lin | 2024/26 | SSRN preprint | international | multiple markets | NR | future CS return | international prices | technical | ML | temporal/country OOS | portfolio tests | explores portability | NR | NR | NR | External-market evidence | New/unreviewed | Regime/generalization context |
| Honarvar & Howard | 2024/25 | Journal of Portfolio Management / SSRN version | US | optioned equities | 1996 onward with pre/post-2008 analysis | next-month underlying return | OptionMetrics + stocks | IV/skew option signals | portfolio sorts/regressions | subperiod and synchronization correction | trading strategies | power declines post-2008; lag correction reduces earlier result | NR | No, OptionMetrics licensed | Central contribution is correcting non-synchronous look-ahead | Falsification of options claims | Vendor-specific and not a broad ML contest | Deprioritize options |
| Neuhierl, Tang, Varneskov & Zhou | 2021/24 | SSRN preprint | US | optioned equities | NR | underlying stock return | options + firm chars | option characteristics | regularized/CS tests | temporal OOS | portfolio tests | few option variables add after firm chars | NR | No | Requires synchronized options | Incrementality test | Working paper/licensed data | Options ablation standard |
| Kelly et al., IV Surfaces | 2023/26 | SSRN preprint | US | optioned equities | NR | underlying return | proprietary option surfaces | IV surface images | CNN ensemble | temporal OOS | includes TC analysis | surface contains predictive information | NR | No | Requires quote-time synchronization | Learns full surface | Proprietary and compute-heavy | Later paid-data case |
| Ye et al., IV Surface | 2026 | SSRN preprint | NR | optioned equities | NR | CS stock return | option surfaces | surface representations | ML | OOS claimed | NR | reports surface predictability | NR | No/NR | NR | New surface evidence | Too recent/unreviewed | Watch only |
| Ke & Wang, Risk-Neutral Moments | 2024/26 | SSRN preprint | US | optioned equities | NR | future CS return | options | risk-neutral higher moments | sorts/regressions | temporal CS tests | portfolio returns | higher moments may carry tail information | NR | No | Method/vendor dependent | Interpretable option features | Preprint and input-sensitive | Possible later low-dimensional features |
| Siano | 2025 | Management Science forthcoming | US | earnings announcers | NR | disclosure news / return response | earnings filings/disclosures | LLM text measures | LLM/NLP + regressions | event/OOS checks | not a general TC study | disclosure text adds information | NR | SEC text may be open; labels/code NR | Exact filing time is feasible | Modern filing-text measurement | Event-specific; model/license details | Supports SEC 8-K corpus |
| He & Zhang | 2025 | SSRN preprint | US | earnings-call firms/peers | NR | surprise/spillover returns | transcripts + market data | embeddings and peer links | NLP/network | temporal/event OOS | NR | cross-firm earnings information spills over | NR | No, transcripts generally licensed | Must align call/publication timestamps | Relational event signal | Transcript license/preprint | Future multimodal candidate |
| Avramov et al., Dual Industry | 2024/25 | SSRN preprint | US | related firms | NR | future stock return | industry/firm links | dual-industry exposures | network/CS model | temporal OOS | portfolio evaluation | cross-stock structure predicts returns | NR | NR | Relation histories need effective dates | Adds relational structure | Definition stability and proprietary mappings | Sector/network direction |
| Kwon, Lee & Yoo | 2024/26 | SSRN preprint | US | analyst-covered equities | NR | future returns | analyst forecasts | dispersion/decomposition | CS regressions/portfolios | temporal tests | portfolio returns | disagreement and uncertainty differ economically | NR | No, analyst data licensed | Requires exact forecast vintages | Better estimate representation | Vendor access and preprint | Existing estimate audit |
| Zhang, Wu & Chen, *Constructing long-short stock portfolio with a new listwise learn-to-rank algorithm* | 2021 | arXiv preprint | China | 80 of 3,712 A-shares (missing-data filter) | 2006--2019 | ranked stock list | 68-factor weekly panel | 68 factors | new listwise neural LTR | OOS long/short | 30 bp per trade charged | excess return 38%, Sharpe 2.01, turnover 0.48 (MLP: Sharpe 0.72, turnover 0.39) | [Author code and data](https://github.com/TCtobychen/ListFold) (no license) | Paper states data are open; 80 survivor-filtered stocks | PIT quality NR | Loss emphasizes both tails | Different market; 80-stock filtered universe; preprint; costs (30 bp) were charged | Direct rank-objective precedent |
| LambdaMART + SHAP stock selection | 2022 | journal article | NR | stocks | NR | ranking | factor panel | factors | LambdaMART + SHAP | OOS | NR | demonstrates interpretable ranked selection | NR | NR | NR | Ranking plus interpretation | Setting/external validity limited | Implementation precedent |
| Celeny et al., Cyber Risk | 2024 | arXiv preprint | US | 7,059 SEC filers | 2007–2022; portfolios 2009–2022 | most-recent 10-K cyber score / future portfolio return | SEC 10-K, MITRE, CRSP/Compustat | doc2vec document score + controls | DM/DBOW doc2vec then sorts/regressions | 2008 validation documents; chronological portfolio sample | none found | positive high-minus-low returns/alphas reported | author repo reported | SEC/MITRE open; CRSP/Compustat licensed | filing date supports PIT; identity/returns still need mapping | Scalable filing-text construction | preprint; annual text, no turnover/cost analysis | Later SEC-text candidate |
| Qian et al., MDGNN | 2024 | arXiv preprint | benchmark markets | public benchmark universes | benchmark periods | stock movement class/rank | prices + relation graphs | dynamic relations | multi-relational GNN | benchmark temporal split | TC not central | improves benchmark prediction | NR | Benchmark data partly public | Benchmark-dependent | Dynamic multi-graph architecture | Not comparable to US net-long/short research | Defer graph complexity |
| Poh, Lim, Zohren & Roberts | 2020 | arXiv preprint | US equities (CRSP, NYSE common stocks) | price > $1, 100 long / 100 short | 1980--2019 | 21-day volatility-normalised return, learned as ranks | CRSP | price-based momentum/MACD features only | pairwise/listwise LTR (LambdaMART best) | 5-year retrain windows, temporal OOS | **none: all returns computed without transaction costs** | LambdaMART Sharpe 2.16 vs 0.70 (best heuristic) and 0.27 (MLP), gross, vol-scaled to 15% | Paper-linked implementation details; license not verified | No turnkey OmniSignal-equivalent panel | Price histories are naturally timestamped; exact execution alignment is study-specific | Directly aligns training with rank selection | Different instruments and preprint evidence | Adaptation completed; EXP-009B found no ordering gain, so reject next cycle |
| Jensen, Kelly, Malamud & Pedersen | 2024 (SSRN); published RFS 2026 | RFS | global/equity applications | characteristic-managed portfolios | paper sample | implementable portfolio weights/economic utility | market and characteristic data | firm characteristics and trading costs | cost-aware portfolio policy | temporal OOS economic tests | explicit transaction-cost-aware objective | shifts the efficient frontier after implementation frictions | Author repository exists (no license; needs WRDS/Markit data) | Core datasets are not an open turnkey package | Depends on source construction | Learns an implementable rather than frictionless policy | Complex end-to-end objective weakens attribution | Supports isolated turnover-aware construction |
| Cakici & Zaremba | 2026 | SSRN preprint | 35 markets | broad international equities | 1994--2024 | raw versus ordinal future-return targets | market/characteristic panels | firm characteristics | comparative ML models | temporal international OOS | portfolio evaluation; exact cost portability must be verified | ordinal targets improve average predictive and portfolio results in the reported tests | NR | No verified open full panel | Study-specific lagging | Direct evidence on target transformation | Very recent preprint; magnitude information can matter | Supports fixed rank-target comparison in EXP-009 |
| Bianchi & Zheng | 2026 | SSRN preprint | characteristic portfolios | equities | paper sample | posterior portfolio-position distribution | returns and characteristics | characteristic signals | Bayesian neural portfolio policy | temporal OOS | cost/no-trade treatment claimed but primary text unavailable | **UNVERIFIED** | NR | No verified open full data package | Study-specific | Converts uncertainty into a no-trade region | Recent preprint and inaccessible primary text | Concept only; no numeric reliance |
| Analyst Stickiness and Stock Return Predictability | 2026 | Review of Finance | US | analyst-covered firms | paper sample | future returns following analyst revisions | analyst-level forecast histories | analyst stickiness and revisions | portfolio sorts/regressions | temporal portfolio tests | economic portfolio evaluation | revisions by sticky analysts are reported as more predictive | NR | No; analyst-level history is licensed | Requires analyst-level vintages | Identifies heterogeneity inside consensus revisions | Local store lacks analyst identifiers | Supports revision family but is not exactly locally reproducible |
| Campbell et al., Expectations Matter | 2024 | SSRN working paper | US | analyst-covered firms | paper sample | earnings/return outcomes | analyst forecasts plus firm data | expectations and nonlinear corrections | broad ML comparison | temporal OOS | not primarily a turnover study | most tested ML specifications do not beat analysts; selected models correct nonlinear bias | NR | No verified open full panel | Requires vintage forecasts | Strong negative result against indiscriminate model complexity | Working paper and vendor dependence | Supports using consensus as information, not merely adding model size |

### Replication-control supplement

This table supplies the requested implementation fields that do not fit in the
register above. `NR` means the value was not verified in the primary public
record reviewed; it must be resolved from the full paper/supplement before a
faithful replication. S/Z/B means sector/size/beta neutralization.

| Work | Number of stocks | Rebalance / horizon | Target transform | Feature count | Hyperparameter strategy | Purge / embargo | Turnover reported | S/Z/B controls | Portfolio construction | Code / data license | Reproducibility | Feasibility for OmniSignal |
|---|---|---|---|---:|---|---|---|---|---|---|---|---|
| Gu, Kelly & Xiu | ~30k unique | monthly / 1 month | excess return | 94 plus macro interactions | validation-period model selection | temporal separation; explicit purge NR | portfolio turnover/cost sensitivity reported | risk-adjusted variants; exact S/Z/B varies | decile/value-weighted long-short tests | no verified official code; CRSP/Compustat licensed | MEDIUM-LOW without WRDS | HIGH for a reduced characteristic baseline |
| Chen, Pelger & Zhu | NR | monthly / conditional pricing horizon | SDF/moment objective | NR | validation-based architecture choice | temporal OOS; purge NR | not a direct stock-turnover recipe | latent-factor/economic restrictions | learned SDF/managed portfolios | author code, no visible reuse license; core data licensed | MEDIUM for method, LOW for exact data | LOW as next selector |
| Avramov, Cheng & Metzker | NR | monthly / next period | economic restrictions on return forecasts | NR | comparative fixed model families | temporal OOS; purge NR | NR | economic/risk restrictions central; exact S/Z/B NR | sorted/optimized OOS portfolios | code NR; licensed equity panel | MEDIUM-LOW | MEDIUM as a controls design |
| Kelly et al., Virtue of Complexity | NR | monthly / next period | future return | large characteristic panel | complexity regularized/validated | temporal OOS; purge NR | economic portfolio tests; exact turnover NR | risk evaluation; exact S/Z/B NR | characteristic-managed portfolios | code/data NR; core panel licensed | MEDIUM-LOW | MEDIUM after simpler baselines |
| Bagnara review | n/a | n/a | n/a | n/a | n/a | n/a | synthesis only | synthesis only | n/a | publisher article | HIGH for review, not replication | HIGH for governance |
| Factor Models, ML, Asset Pricing | n/a | n/a | n/a | n/a | n/a | n/a | synthesis only | synthesis only | n/a | publisher article | HIGH for review, not replication | HIGH for taxonomy |
| Chen, Hanauer & Kalsbach | avg ~2,093/month | monthly / target variants | raw, excess, market/factor-adjusted | 207 | controlled multiverse, >1,000 designs | temporal OOS; purge NR | portfolio implementation compared; exact figure design-specific | target/risk variants; exact S/Z/B design-specific | top-minus-bottom portfolios | OSAP partly open; CRSP licensed | MEDIUM | HIGH as a design checklist, not a search budget |
| Han, He, Rapach & Zhou | NR | monthly / next period | CS return/Fama-MacBeth coefficients | ~200 | regularization and forecast combinations | temporal OOS; purge NR | NR | characteristic/risk controls; exact S/Z/B NR | forecast-sorted portfolios | code NR; CRSP inputs licensed | MEDIUM-LOW | HIGH for linear baseline |
| Barunik, Hronec & Tobek | global panel; exact N study-specific | monthly / return distribution | conditional quantiles | large firm/estimate panel | validation across quantile NN/GB/RF | temporal and geographic OOS; purge NR | analytics include portfolio turnover/costs; exact cell-specific | regional/risk evaluation; S/Z/B NR | quantile-conditioned portfolios | MIT code; licensed WRDS/LSEG core omitted | MEDIUM with licenses | LOW-MEDIUM after core EXP-009 |
| Brownlees & Souza | NR | NR / winner-loser horizon | class/decision label | NR | comparative decision rules | temporal OOS; purge NR | NR | NR | winner/loser action portfolios | code/data/license NR | LOW-MEDIUM | MEDIUM as later classification cell |
| He, Lv & Zhou | 31,492 unique | monthly / next month | event probability | 94 | validation/model comparison | expanding OOS; purge NR | economic portfolios; exact turnover NR | factor augmentation; exact S/Z/B NR | probability-sorted and augmented portfolios | code NR; CRSP licensed | MEDIUM-LOW | MEDIUM after rank baseline |
| Girardi, Koerber & Schlag | NR | NR / future CS return | nonlinear return mapping | NR | comparative flexible models | temporal OOS; purge NR | NR | NR | OOS portfolios | code/data/license NR | LOW-MEDIUM | LOW as immediate action |
| Azevedo, Hoegner & Velikov | strategy-specific | strategy-specific | replicated strategy return | strategy-specific | replication/meta-analysis | post-publication OOS | central; decay and costs reported | study-specific | published-strategy portfolios | mixed underlying licenses | MEDIUM | HIGH for net-first gates |
| Chin | NR | monthly/rolling / future CS return | rank/return variants NR | technical family count NR | rolling validation | temporal OOS; purge NR | portfolio tests; exact turnover NR | NR | prediction-sorted portfolios | code/data/license NR | LOW-MEDIUM | MEDIUM as current-feature comparator |
| Chin & Lin | NR | NR / future CS return | NR | NR | cross-market comparison | temporal/country OOS | NR | country/risk comparisons; S/Z/B NR | sorted portfolios | code/data/license NR | LOW | LOW-MEDIUM |
| Honarvar & Howard | NR optioned equities | monthly / next month | option signal sorts | low-dimensional option signals | specification/subperiod checks | lag/synchronization correction central | strategy economics; exact turnover NR | firm controls; exact S/Z/B NR | option-signal sorts | code NR; OptionMetrics commercial | LOW without vendor data | HIGH as falsification warning |
| Neuhierl, Tang, Varneskov & Zhou | NR | monthly / future underlying return | incremental option residual | option + firm-characteristic panel | regularized/comparative CS tests | temporal OOS; synchronization required | NR | firm-characteristic controls; S/Z/B NR | prediction sorts | code NR; options data licensed | LOW-MEDIUM | MEDIUM as later isolated ablation |
| Kelly et al., IV Surfaces | NR optioned equities | NR / future underlying return | surface representation | learned surface pixels/features | CNN ensemble validation | temporal OOS; quote alignment required | cost analysis included; turnover NR | firm/risk controls NR | prediction-sorted portfolios | code NR; proprietary surfaces | LOW | LOW until contract-level source exists |
| Ye et al., IV Surface | NR | NR / CS future return | learned surface representation | NR | NR | OOS claimed; purge NR | NR | NR | NR | code/data/license NR | LOW | LOW; watch only |
| Ke & Wang | NR | monthly/NR | risk-neutral moments | small moment set | specification comparison | temporal CS; option synchronization required | portfolio returns; turnover NR | firm controls; exact S/Z/B NR | moment sorts/regressions | code NR; option vendor data licensed | LOW-MEDIUM | LOW-MEDIUM later |
| Siano | earnings announcers; N NR | event based / announcement response | disclosure-news measure | learned text measures | model/specification validation | chronological event tests; exact embargo NR | not a general turnover study | firm/event controls | event-return tests | code NR; SEC text open, labels NR | MEDIUM-LOW | MEDIUM after timestamped filing corpus |
| He & Zhang | earnings-call firms/peers; N NR | event based / spillover horizon | embeddings/network relation | learned text/network features | temporal/event validation | event chronology; exact embargo NR | NR | peer/industry controls central | event/spillover portfolios | code NR; transcripts licensed | LOW | LOW-MEDIUM |
| Avramov et al., Dual Industry | related-firm panel; N NR | NR / future return | relation-conditioned return | industry/network set NR | comparative specifications | temporal OOS; purge NR | portfolio evaluation; turnover NR | industry relation is central; Z/B NR | relation-sorted portfolios | code/data/license NR | LOW-MEDIUM | MEDIUM after PIT classifications |
| Kwon, Lee & Yoo | analyst-covered equities; N NR | monthly/NR | disagreement/uncertainty decomposition | analyst-distribution features | specification comparison | temporal tests; exact embargo NR | portfolio returns; turnover NR | firm controls; exact S/Z/B NR | feature sorts/regressions | code NR; analyst data licensed | LOW without IBES-like history | MEDIUM for consensus approximations only |
| Zhang, Wu & Chen | A-share count NR | paper cadence / ranked horizon NR | listwise relevance labels | 68 | paper-defined neural tuning | temporal OOS; purge NR | not credibly portable/fully verified | NR | top/bottom long-short | official code; license/data unverified | LOW-MEDIUM algorithmically | MEDIUM for loss mechanics only |
| LambdaMART + SHAP | NR | NR | ranking labels | NR | NR | OOS; purge NR | NR | NR | ranked selection | code/data/license NR | LOW-MEDIUM | MEDIUM as implementation precedent |
| Qian et al., MDGNN | benchmark-specific | benchmark cadence/horizon | movement class/rank | learned price + multi-graph | benchmark validation | temporal split; embargo NR | not central | graph relations include sector/market links; Z/B NR | benchmark trading evaluation | benchmark data partly open; code/license NR | MEDIUM for benchmark only | LOW for liquid-US net selection |
| Poh, Lim, Zohren & Roberts | instrument count NR | strategy cadence/horizon per paper | pairwise/listwise ranks | momentum set NR | comparative ranker validation | temporal OOS; purge NR | trading-cost detail not fully portable | cross-sectional scaling; equity S/Z/B n/a/NR | long-short cross-sectional momentum | implementation/license NR; market data required | MEDIUM algorithmically | HIGH for date-grouped LTR adaptation |
| Jensen, Kelly, Malamud & Pedersen | application-specific | learned policy cadence/horizon | economic utility/net weights | characteristic panel NR | jointly optimized policy | temporal OOS; purge NR | explicit in objective | risk/exposure constraints central; exact S/Z/B varies | direct implementable weights | code/data/license NR | MEDIUM-LOW exact, HIGH conceptually | HIGH for a simple isolated buffer; LOW for full policy |
| Cakici & Zaremba | 35 markets; stock count NR | monthly/NR | ordinal versus raw return | characteristic count NR | fixed comparative ML design | temporal international OOS; purge NR | portfolio results; exact turnover/cost NR | cross-market controls; S/Z/B NR | prediction-sorted portfolios | code/data/license NR | MEDIUM-LOW | HIGH for a fixed target comparison |
| Bianchi & Zheng | NR | policy cadence/NR | posterior position interval | characteristic set NR | Bayesian posterior tuning | temporal OOS; purge NR | central; 24--45% reduction reported | policy/risk controls; exact S/Z/B NR | hold inside credible/no-trade region | code/data/license NR | LOW-MEDIUM | MEDIUM for simple buffer, LOW for full BNN |
| Analyst Stickiness | analyst-covered count NR | forecast-event/monthly / future return | sticky-analyst revision | analyst-level revision set | specification comparison | historical vintages; exact embargo NR | portfolio tests; turnover NR | firm controls; exact S/Z/B NR | revision-sorted portfolios | code NR; IBES-like data licensed | LOW locally for exact design | MEDIUM for consensus-only family |
| Campbell et al., Expectations Matter | analyst-covered count NR | NR / earnings-return outcomes | ML correction to analyst expectation | specification-dependent | broad fixed ML comparison | temporal OOS; purge NR | not primarily a turnover study | firm controls; exact S/Z/B NR | forecast/economic comparisons | code/data/license NR | LOW-MEDIUM | HIGH as negative-evidence guardrail |

## Coverage of requested method families

| Family | Evidence read | Decision |
|---|---|---|
| Regularized linear/factor | GKX; Han et al.; Avramov et al. | Mandatory baseline; stable and interpretable, not obsolete |
| Trees/boosting | GKX; design-choice multiverse; current EXP-006/007 | Robust tabular baseline; changing tree brand alone is not a research gap |
| Learning to rank | Zhang/Wu/Chen; LambdaMART study | Objective alignment is plausible but evidence is narrower/different-market; preregister later |
| Deep tabular | GKX NN; CPZ; quantile NN | Can help large panels, but no strong basis to prioritize TabNet/FT-Transformer here |
| Temporal sequence models | CPZ macro LSTM context; limited direct rank evidence found | Do not add LSTM/GRU/TFT merely because observations are temporal |
| Graph | MDGNN; dual-industry work | Relationship data may add signal; data definition is the bottleneck |
| Text/NLP | Siano; earnings-spillover work | Filing/earnings text is promising when exact publication time is available |
| Multimodal | earnings text + market/relationship work | Scientific value is plausible; licensing and attribution make it post-core work |
| Ensembles | GKX/quantile NN/model combinations | Rank/model averaging can reduce variance, but adds a trial and must be registered |
| Uncertainty/selective prediction | probability/quantile works | Better decision framing; conformal/abstention evidence for this exact task remains early |

## Target formulas and cadence evidence

Exact formulas are recorded when the public paper/config exposes them; `NR` in
the full register is intentional for abstract-only studies.

| Study | Target / objective actually used | Horizon and decision cadence |
|---|---|---|
| GKX | `y[i,t] = r[i,t+1] - r[f,t+1]`; prediction losses include MSE/Huber and models are compared on OOS return forecasts | Next month; monthly characteristics and portfolios. Monthly inputs at `t`, quarterly lagged at least 4 months, annual at least 6 months |
| Poh et al. | Order stocks by realized 21-trading-day forward return; pairwise/listwise losses optimize within-date ranking. Portfolio return scales each selected asset by ex-ante EW volatility and a 15% target-volatility factor | 21 trading days; portfolio rebalanced on the last trading day of each month |
| ListFold | `y[i,t] = rank_cs(r[i,t+1])`; ListFold/ListMLE-style permutation likelihood emphasizes both tails | Weekly labels and weekly portfolio; 300-week train, 16-week test |
| Qlib Alpha158 config | `y[t] = close[t+2] / close[t+1] - 1`, then cross-sectional z-score; one-day offset separates signal and execution | Next day; daily signal and top-k/dropout update |
| Barunik et al. | `Q_tau(r[i,t+1] | F_t)` for 37 values of `tau`; pinball loss `rho_tau(u)=u(tau-1[u<0])`; second stage maps standardized quantiles and market volatility to 22-day raw-return quantiles | 22 trading days; monthly portfolios, annual expanding retraining |
| Chen–Pelger–Zhu | Choose SDF weights to minimize unconditional/conditional pricing moments; an adversary selects moments with largest pricing discrepancy | Monthly; fixed train/validation/test epochs rather than portfolio rebalancing study |
| OmniSignal | `rank_cs(prod_{j=1..21}(1+r[i,t+j])-1)` with prediction time before the forward window | 21 sessions, but current book updated every ~5 sessions |

The papers align label and portfolio cadence more often than OmniSignal does:
GKX is monthly/monthly, Poh is 21-day/monthly, Barunik is 22-day/monthly, and
Qlib is next-day/daily. They do not prove that 21-session cadence will win here,
but they make one preregistered 5d-versus-21d test scientifically justified.
Overlapping 21-session labels require block/HAC inference regardless of cadence.

## Official and author code reviewed

| Repository | Relationship | License / activity evidence | Training/data support | Reproducibility conclusion |
|---|---|---|---|---|
| [LouisChen1992/Deep_Learning_in_Asset_Pricing](https://github.com/LouisChen1992/Deep_Learning_in_Asset_Pricing) | Author repository for Chen–Pelger–Zhu | 13 commits; no license visible, so reuse rights are **not assumed** | FFN/GAN/linear notebooks, empirical outputs, links to data/models | Method inspectable; full data/licensed-use and environment not turnkey |
| [ondrejtobek/quantile-neural-networks](https://github.com/ondrejtobek/quantile-neural-networks) | Author replication package | MIT; package assembled April 2026; 9 commits visible | Full processing/training/analytics scripts and minimum notebook; licensed WRDS/LSEG inputs omitted except schemas/samples | Strongest package reviewed; full replication still requires proprietary inputs and much larger GPU/RAM host |
| [TCtobychen/ListFold](https://github.com/TCtobychen/ListFold) | Repository named in the listwise LTR paper | No license; reviewed commit `97939a5` | PyTorch implementation and links to feature/price arrays; 21 rolling pairs | Reference-only. The 80-stock survivor-filtered sample undermines portability |
| [microsoft/qlib](https://github.com/microsoft/qlib) | Official research platform | MIT; active large repository (2,000+ commits visible) | Alpha158/360 handlers, many models, strategy/backtest workflows and tests | Reproducible framework examples; China/community data and assumptions are not an OmniSignal substitute |
| [theisij/ml-and-the-implementable-efficient-frontier](https://github.com/theisij/ml-and-the-implementable-efficient-frontier) | Official JKMP replication | No license; reviewed commit `13d836b` | Full Slurm workflow and measured RAM/runtime disclosures; requires JKP/WRDS and optional Markit | Exact run needs 25–75 GB/job and cluster arrays; neither available environment fits |

The GKX paper links a small author simulation repository and a derived public
characteristic dataset, but not the full empirical pipeline; no repository
license was found. Community replications are not cited as official code.

## Answers to RQ1--RQ10

1. **Targets vary materially.** Raw/excess/residual return, ranks, winner
   probabilities and return quantiles all appear. No target dominates every
   market; the design-choice paper shows target/transformation is first-order.
2. Regression remains common. Classification/probability and LTR are credible
   alternatives when the action is selection, but the LTR evidence base is
   smaller and less US/PIT/cost-comparable.
3. Momentum, liquidity, volatility, value/quality/investment and earnings/
   analyst information recur. “More features” is not consistently better.
4. After costs, ordinary firm characteristics and carefully timed earnings/
   filing data have a stronger feasibility case than expensive options or
   alternative data for this project.
5. Strong designs remove microcaps and control market/industry/size/risk
   exposure. The exact neutralization must be tested rather than assumed.
6. Temporal OOS windows, lagged availability, survivor-inclusive databases and
   trial accounting are standard defenses. Vendor PIT semantics remain a major
   reproducibility barrier.
7. Costs and turnover often change conclusions. Capacity/borrow/impact evidence
   is less consistently available than headline Sharpe and is a literature gap.
8. Rank IC/ICIR, OOS R-squared, top-minus-bottom returns, Sharpe, alpha,
   drawdown and turnover are used. A deployable claim needs both predictive and
   economic metrics.
9. Regularized linear models and tree ensembles remain robust baselines. Deep,
   graph, text and distributional models can add value in the right data regime
   but do not dominate without qualification.
10. Data timestamps, target, preprocessing, sample and portfolio construction
    can matter as much as or more than swapping model families. That is the
    central lesson for OmniSignal.

## Synthesis by design question

### Target formulation

The strongest actionable consensus is not that one target always wins. Mean
regression is a robust baseline; direct rank, classification, probability, and
quantile objectives can better match a selection decision, but each changes
calibration and portfolio behavior. Therefore objective choice must be an
identified preregistered comparison on identical folds and features.

### Feature families

Momentum, liquidity, volatility, size/value/quality, rates/regime and earnings
information remain defensible. Recent evidence supports filing/earnings text,
analyst uncertainty and cross-stock relations, but with demanding point-in-
time provenance. Options evidence is mixed, synchronization-sensitive, and
costly; it is not the next highest-value acquisition for this repository.

### Evaluation

Credible work uses temporal OOS evaluation, realistic availability dates,
cross-sectional portfolio tests, risk controls, and costs. OmniSignal must add
block-aware uncertainty because its 21-session labels overlap. Model selection
must report fold dispersion, worst fold, trial count, turnover, capacity and
cost curves. A positive aggregate IC is insufficient.

### Portfolio construction

Recent evidence reinforces that design and implementation can dominate model
choice. Score smoothing, entry/exit buffers, neutralization, constraints and
abstention are legitimate hypotheses only when isolated from the predictive
model. EXP-006's 20.15x turnover made this the most urgent design axis;
EXP-009A has now confirmed one bounded-replacement solution, so the rule should
be frozen while information changes are tested.

## Post-EXP-009 governance boundary and decision

EXP-008 remains exactly as preregistered. EXP-009 now exists and is immutable:
its turnover result succeeded, its two ranking objectives failed, its analyst
arm failed, and duplicate-axis removal was equivalent. Nothing in this survey
retrofits a threshold, trial or interpretation into either study.

The immediate follow-on is a new **EXP-010A** ten-seed noise-floor study, then a
new **EXP-010B** 5d-versus-21d cadence study on frozen predictions. The next
information study becomes **EXP-011** only after an SEC as-reported fundamentals
panel and PIT security master exist. Its primary comparison is base data versus
base+PIT data under regularized linear and conservative boosted-tree models,
with the successful top-k dropout rule held fixed. Options, graphs and large
neural models are not supported for the next cycle.
