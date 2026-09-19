# Paper reference and access index

Cutoff: 2026-09-19. This is the repository-safe catalog for the literature
survey. `DOWNLOADED` means a lawful public copy is cached under the ignored
`research_papers/` directory. It does **not** mean the PDF or third-party code
may be redistributed. `NR` means not established from the primary material
reviewed, not that the item does not exist.

## Coverage and status

| Cohort | Count |
|---|---:|
| 2024 | 18 |
| 2025 | 3 |
| 2026 | 4 |
| Foundational / older (2014–2023) | 9 |
| **Total** | **34** |
| Public PDFs downloaded and read | **9** |

The 25 papers dated 2024–2026 exceed the requested recent-literature target.
Several are working papers or preprints; status is explicit below. The matrix
does not convert recency into evidentiary weight.

## Reference register

| Paper | Year | Venue / status | DOI or identifier | Primary URL | Public PDF / local filename | Supplement | Official code | Sufficient data | Notes | Relevant OmniSignal decision |
|---|---:|---|---|---|---|---|---|---|---|---|
| Novy-Marx & Velikov, *A Taxonomy of Anomalies and Their Trading Costs* | 2014/16 | NBER WP / RFS | NBER w20721 | https://www.nber.org/papers/w20721 | DOWNLOADED `2014_NovyMarx_AnomaliesTradingCosts.pdf` | paper appendix | NR | No; CRSP/TAQ licensed | complete | Top-k/dropout and no-trade region anchor |
| Gu, Kelly & Xiu, *Empirical Asset Pricing via Machine Learning* | 2020 | RFS | 10.1093/rfs/hhaa009 | https://doi.org/10.1093/rfs/hhaa009 | DOWNLOADED `2018_Gu_EmpiricalAssetPricingML.pdf` | paper appendix | partial simulation repo; no license found | Characteristic panel public; CRSP returns licensed | complete | Broad PIT characteristic baseline |
| Chen, Pelger & Zhu, *Deep Learning in Asset Pricing* | 2024 | Management Science | 10.1287/mnsc.2023.4695 | https://doi.org/10.1287/mnsc.2023.4695 | DOWNLOADED author manuscript `2019_Chen_DeepLearningAssetPricing.pdf` | paper appendix | yes; no license found | No; CRSP/Compustat licensed | complete | Reject exact SDF/GAN; retain economic restrictions |
| Poh et al., *Building Cross-Sectional Systematic Strategies by Learning to Rank* | 2020 | arXiv preprint | arXiv:2012.07149 | https://arxiv.org/abs/2012.07149 | DOWNLOADED `2020_Poh_CrossSectionalLTR.pdf` | no separate supplement | yes; license NR | No; CRSP licensed | complete | LTR replication tested and failed in EXP-009B |
| Yang et al., *Qlib: An AI-oriented Quantitative Investment Platform* | 2020 | arXiv / engineering paper | arXiv:2009.11189 | https://arxiv.org/abs/2009.11189 | DOWNLOADED `2020_Yang_Qlib.pdf` | repository configs | yes, MIT | China sample only; not US PIT | complete | Top-k dropout successfully adapted |
| Zhang, Wu & Chen, *Constructing Long-Short Stock Portfolio with ListFold* | 2021 | arXiv preprint | arXiv:2104.12484 | https://arxiv.org/abs/2104.12484 | DOWNLOADED `2021_Zhang_ListFold.pdf` | in paper | yes; no license found | Claimed open but narrow survivor sample | complete | Reject immediate replication |
| Celeny et al., *Cyber Risk and the Cross-Section of Stock Returns* | 2024 | arXiv preprint | arXiv:2402.04775 | https://arxiv.org/abs/2402.04775 | DOWNLOADED `2024_Celeny_CyberRisk.pdf` | paper appendix | author repo reported | SEC text open; CRSP/Compustat licensed | complete | SEC text precedent; later-stage feature |
| Qian et al., *MDGNN* | 2024 | AAAI workshop/preprint | arXiv:2402.06633 | https://arxiv.org/abs/2402.06633 | DOWNLOADED `2024_Qian_MDGNN.pdf` | none found | NR | China graph relations not locally available | complete | Reject until PIT relations exist |
| Barunik, Hronec & Tobek, *Forecasting Stock Return Distributions Around the Globe* | 2025 rev. | arXiv preprint | arXiv:2408.07497 | https://arxiv.org/abs/2408.07497 | DOWNLOADED `2025_Barunik_ReturnDistributions.pdf` | repository artifacts | yes, MIT | No; WRDS and LSEG licensed inputs omitted | complete | Defer exact quantile NN |
| Avramov, Cheng & Metzker, *Machine Learning versus Economic Restrictions* | 2023 | Management Science | 10.1287/mnsc.2022.4449 | https://doi.org/10.1287/mnsc.2022.4449 | Publisher/preprint reviewed; not cached | publisher appendix | NR | No | survey | Supports economically restricted baseline |
| Kelly et al., *The Virtue of Complexity in Return Prediction* | 2024 | Journal of Finance | 10.1111/jofi.13298 | https://doi.org/10.1111/jofi.13298 | Publisher access; not cached | publisher appendix | NR | No | survey | Regularized complexity, not model novelty |
| Bagnara, *Asset Pricing and Machine Learning: A Critical Review* | 2024 | Journal of Economic Surveys | 10.1111/joes.12532 | https://doi.org/10.1111/joes.12532 | Publisher access; not cached | n/a | n/a | n/a | survey | Evidence-quality anchor |
| *Factor Models, Machine Learning, and Asset Pricing* | 2022 | Annual Review | 10.1146/annurev-financial-101521-104735 | https://doi.org/10.1146/annurev-financial-101521-104735 | Publisher access; not cached | n/a | n/a | n/a | survey | Taxonomy and identification limits |
| Chen, Hanauer & Kalsbach, *Design Choices, ML, and Cross-Sectional Returns* | 2024 | working paper, rev. 2026 | SSRN 5031755 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5031755 | PREPRINT ONLY; SSRN PDF blocked in this environment | NR | NR | OSAP partial; CRSP licensed | abstract/table metadata | Design variance warning |
| Han et al., *New Fama-MacBeth Regressions in the Era of Machine Learning* | 2024 | Review of Finance forthcoming | SSRN 3185335 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3185335 | PREPRINT ONLY; not cached | NR | NR | No | survey | Regularized linear benchmark |
| Brownlees & Souza, *How to Bet on Winners (and Losers)* | 2025 | working paper | SSRN 5352643 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5352643 | PREPRINT ONLY; PDF unavailable here | NR | NR | NR | abstract only | Decision-aligned loss watchlist |
| He, Lv & Zhou, *Empirical Asset Pricing with Probability Forecasts* | 2024 | working paper | SSRN 4717935 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4717935 | PREPRINT ONLY; not cached | NR | NR | NR | abstract/survey | Probability-target watchlist |
| Girardi, Koerber & Schlag, *Nonlinearities and Pricing Complexity* | 2024 | working paper | SSRN 5502838 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5502838 | PREPRINT ONLY; not cached | NR | NR | NR | abstract/survey | Nonlinearity is conditional |
| Azevedo, Hoegner & Velikov, *Expected Returns on Machine-Learning Strategies* | 2024 | working paper, rev. 2025 | SSRN 4702406 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4702406 | PREPRINT ONLY; PDF unavailable here | NR | NR | No | abstract only | Net-first evaluation anchor |
| Chin, *Machine Learning and the Cross-Section of Stock Returns* | 2022 | working paper, rev. 2026 | SSRN 4282614 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4282614 | PREPRINT ONLY; not cached | NR | NR | NR | survey | Comparable price/technical family |
| Chin & Lin, *Machine Learning and Technical Analysis in International Markets* | 2024 | working paper, posted 2026 | SSRN 6579120 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6579120 | PREPRINT ONLY; not cached | NR | NR | NR | abstract/survey | Portability watchlist |
| Honarvar & Howard, *Better Opt Out?* | 2024 | working paper / JPM 2025 | SSRN 4766424 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4766424 | Publisher abstract; not cached | NR | NR | OptionMetrics-like data licensed | abstract only | Options synchronization warning |
| Neuhierl et al., *Do Option Characteristics Predict Underlying Stock Returns?* | 2021 | working paper, rev. 2024 | SSRN 3795486 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3795486 | PREPRINT ONLY; not cached | NR | NR | No | survey | Weak incremental options prior |
| Kelly et al., *Deep Learning from Implied Volatility Surfaces* | 2023 | working paper, rev. 2026 | SSRN 4531181 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4531181 | PREPRINT ONLY; not cached | NR | NR | Proprietary surfaces | survey | Reject without contract-level archive |
| Ye et al., *IV Surface and the Cross-Section* | 2026 | preprint | SSRN 6890048 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6890048 | PREPRINT ONLY; not cached | NR | NR | No | abstract only | Watchlist, not implementation basis |
| Ke & Wang, *Risk-Neutral Higher Moments* | 2024 | working paper, rev. 2026 | SSRN 4777204 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4777204 | PREPRINT ONLY; not cached | NR | NR | No | abstract/survey | Interpretable option features later |
| Siano, *News in Earnings Announcement Disclosures* | 2025 | Management Science | 10.1287/mnsc.2024.05417 | https://doi.org/10.1287/mnsc.2024.05417 | PAYWALLED; legal PDF unavailable | publisher supplement NR | NR | SEC exhibits open; exact sample construction NR | abstract only | Supports SEC 8-K text build |
| He & Zhang, *Cross-Sectional Spillovers of Earnings Surprises* | 2025 | working paper | SSRN 5415255 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5415255 | PREPRINT ONLY; not cached | NR | NR | Transcripts licensed | abstract/survey | Defer relational event text |
| Avramov et al., *Dual Industry Effects and Cross-Stock Predictability* | 2024 | working paper | SSRN 4849902 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4849902 | PREPRINT ONLY; not cached | NR | NR | Relationship data incomplete | abstract/survey | Supports PIT industry control |
| Kwon, Lee & Yoo, *Disagreement versus Uncertainty* | 2024 | working paper, rev. 2026 | SSRN 4921479 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4921479 | PREPRINT ONLY; not cached | NR | NR | Analyst-level history absent | abstract/survey | Explains why consensus aggregates may fail |
| Jensen et al., *Machine Learning and the Implementable Efficient Frontier* | 2024/26 | RFS 2026 | SSRN 4187217 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4187217 | PAYWALLED/SSRN blocked; abstract + official repo read | repository is supplement | yes; no license found | No; WRDS/Markit licensed | repo deeply reviewed | Net objective, but exact run impractical |
| Cakici & Zaremba, *Getting the Target Right in Return Prediction* | 2026 | preprint | SSRN 6615698 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615698 | PREPRINT ONLY; PDF unavailable here | NR | NR | NR | abstract only | Rank target already present locally |
| Bianchi & Zheng, *Posterior Uncertainty in Portfolio Policies* | 2026 | preprint | SSRN 6359140 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6359140 | PREPRINT ONLY; primary text unavailable here | NR | NR | NR | unverified | No-trade concept only; no numeric reliance |
| Cao et al., *Analyst Stickiness and Stock Return Predictability* | 2026 | Review of Finance | 10.1093/rof/rfag022 | https://doi.org/10.1093/rof/rfag022 | PAYWALLED abstract | NR | NR | No; analyst-level IBES-like history | abstract only | Not reproducible from consensus snapshots |
| Campbell et al., *Expectations Matter* | 2024 | working paper | SSRN 4495297 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4495297 | PREPRINT metadata; not cached | replication package | data/code package, CC BY 4.0 metadata | Partial; vendor inputs may remain | package metadata/survey | Analysts useful as an input, not assumed alpha |

## Legal-access record

All nine cached PDFs came from NBER, arXiv, or an author/university-hosted
manuscript. No publisher paywall was bypassed. The known high-value inaccessible
items are Siano (publisher text), Analyst Stickiness (publisher text), and the
Jensen et al. final article; for them the survey relies only on lawful abstract,
supplement, and official-code material. Third-party repositories were cloned
only into the ignored cache and inspected at fixed commits; their code is not
copied into OmniSignal.
