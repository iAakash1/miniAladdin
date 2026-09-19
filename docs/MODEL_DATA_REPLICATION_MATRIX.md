# Model × data replication matrix

Date: 2026-09-19. `Local match` compares the paper's actual input with the
current store, not whether a similarly named column exists. Compute marked
“reported” comes from the paper or official repository; all other timing is a
planning estimate defined in `MODEL_COMPUTE_FEASIBILITY.md`.

| Paper / method | Data required | Model / target | Actual or estimated training | GPU / VRAM | Mac feasible? | Kaggle feasible? | PIT safe? | Local match | New data / license issue | Replication difficulty | Expected value / decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GKX broad characteristic panel | CRSP returns, Compustat, 94 characteristics, 8 macro states | OLS/PCR/PLS/elastic net/RF/GBRT/NN; next-month excess return | Omni adaptation: 20–90 min/model family | optional; 2–8 GB for boosting | Yes, scaled | Yes | Paper lags accounting data; exact vintages licensed | **PARTIAL**: price/volume/macro; unsafe statement history | SEC as-reported fundamentals + PIT identity; CRSP exact replication licensed | Medium | **ADAPT first** after data build |
| Regularized Fama–MacBeth / forecast combination | ~200 PIT characteristics | regularized linear CS return forecast | 3–20 min | no | Yes | Yes | Depends on characteristic timestamps | **PARTIAL** | Same PIT characteristic gap | Low–medium | **Required baseline** |
| Qlib Alpha158 + top-k dropout | Daily OHLCV-derived Alpha158, CSI300 | LightGBM MSE; next-day z-scored return; top50/drop5 | Runtime NR; local analog <90 min | optional | Yes | Yes | Qlib sample not US PIT master | **APPROXIMATE** price family; portfolio rule exact concept | No new data for strategy layer; MIT code | Low | **Portfolio idea already adapted successfully** |
| Poh et al. LTR | CRSP NYSE momentum/volatility, 1980–2019 | RankNet/LambdaMART/ListNet/ListMLE; 21-day vol-scaled return rank | Runtime NR; local rankers measured minutes | no/optional | Yes | Yes | Standard temporal split; CRSP exact licensed | **APPROXIMATE** | None for method | Medium | **REJECT immediate**: EXP-009B null |
| ListFold | 68 China factors, 80 survivor-filtered stocks | 4-layer MLP; cross-sectional rank | Runtime NR; estimated <4 h | optional 2–6 GB | Yes | Yes | **No**: survivor filter is material | **NO** | Open sample claim; code no license | Medium | **REJECT evidence base** |
| Novy-Marx–Velikov sS / no-trade region | CRSP anomalies plus spread model | portfolio rule, not predictor | Portfolio-only minutes | no | Yes | Yes | Underlying CRSP licensed; rule itself safe | **YES APPROXIMATE** | Exact spread model absent | Low | **ADAPTED**; top-k dropout won, 20/40 sS did not |
| Implementable efficient frontier | JKP characteristics, daily/monthly returns, optional Markit borrow fees | direct cost-aware portfolio weights | **Reported:** 25–75 GB/job; 5 h to 2 d 16 h; many jobs | CPU/HPC | **No exact** | **No exact** | Depends on WRDS data construction | **NO** | WRDS/Markit; official repo no license | Very high | **ADAPT principle only**, not code/objective |
| Chen–Pelger–Zhu deep SDF | all CRSP stocks, 46 firm chars, 178 macro series | FFN + LSTM + adversarial moments; SDF weights | Runtime/hardware NR | likely GPU | Reduced only | Reduced only | Published construction lags variables; exact licensed | **PARTIAL** macro/price | CRSP/Compustat | Very high | **REJECT** for direct selection cycle |
| Barunik–Hronec–Tobek quantile NN | CRSP/Compustat/IBES + LSEG, 194 features, international | 37 quantiles of next 22-day return | **Reported:** >2 months full, ~4 days minimum on RTX4090/128 GB | 24 GB reported | No exact | No exact | Authors state available-at-time construction; licensed tables | **PARTIAL** and only 8 tested analyst features | WRDS/LSEG; full data omitted | Very high | **DEFER**; no cost/turnover result |
| Celeny et al. SEC cyber text | 60,470 10-Ks, MITRE ATT&CK, CRSP/Compustat | doc2vec DM/DBOW score; most-recent 10-K; quarterly value-weight quintiles | Runtime NR; embeddings estimated 2–8 h T4 | optional 6–12 GB | Feature extraction feasible | Yes | Filing dates permit PIT; return/fundamental identity still needed | **PARTIAL**: SEC is open but corpus not built | SEC open; CRSP/Compustat exact licensed | Medium–high | **ADAPT later** as SEC-text precedent |
| Siano earnings disclosure news | earnings press releases / SEC exhibits, exact event timing | LLM disclosure measures; short-window returns | NR | likely GPU for embeddings | Data build yes | Model likely yes | Must use accepted-at and after-close shift | **NO** corpus | SEC open approximation; full paper paywalled | High | **ADAPT only after fundamentals/security master** |
| Analyst stickiness | analyst-level forecasts/revisions, identity and timestamps | sticky-analyst consensus; future return | NR | no requirement established | Compute yes | Compute yes | Requires exact analyst-vintage history | **NO** (only consensus vintages) | IBES/FactSet/Refinitiv-like licensed | High | **DEFER/REJECT locally**; EXP-009C aggregate arm null |
| Option-surface CNN | contract-level option surfaces and synchronized stock closes | CNN ensemble; future return | NR | likely 8–16+ GB | Difficult | Possible | Synchronization is first-order; look-ahead documented in literature | **NO**: only daily aggregates, 2019+ | OptionMetrics/proprietary surface | Very high | **REJECT next cycle** |
| Option characteristics / moments | IV, skew, term, volume/OI, liquidity | linear/tree CS predictor | 10–60 min after clean panel | optional | Yes | Yes | Local aggregates are irregular; no OI/volume | **PARTIAL** | Need contract history or paid feed | Medium–high | **DEFER** due weak incremental evidence |
| MDGNN | dynamic industry/bank/stock graphs, 42 node features, 18.9–62.5m edges | temporal multi-relational GNN; daily positive-return classification | **Reported:** V100, 500 epochs; runtime NR | V100 class; VRAM NR | No at paper scale | Reduced only | Temporal split stated; relation timestamp provenance unclear | **NO** | China relationship graph absent | Very high | **REJECT now** |
| Plain boosted tree on SEC PIT characteristics | SEC as-reported facts + price/volume + FRED + PIT size/industry controls | LightGBM/sklearn GB; 21-session CS rank | Estimated Mac 20–90 min / 10 seeds after materialization | optional 2–8 GB | **Yes** | **Yes** | **Yes if remediation plan passes** | **PARTIAL today; YES after build** | Open SEC/FRED; engineering only | Medium | **Highest-value model/data combination** |
| Small MLP on same rich tabular panel | Same as row above | 2–4 layer MLP; 21-session rank or Huber return | Estimated Kaggle 30–120 min / 10 seeds | 2–6 GB | Yes but slower | **Yes** | Same prerequisite | **PARTIAL today** | No data-license issue after SEC build | Medium | Third model, only after linear/tree baselines |

## Local data match by family

| Family | Match | Why |
|---|---|---|
| Price, volume, volatility, macro | **YES APPROXIMATE / usable** | Long history and current PIT-safe feature pipeline; this is most of the 27-feature EXP-006/009 set. |
| Analyst consensus revisions | **YES APPROXIMATE / tested** | Vintages and strict backward attachment pass PIT gates, but no analyst identity/recommendations/targets; EXP-009C found no reliable value. |
| Earnings calendar / PEAD | **PARTIAL** | Calendar starts 2020, ~25% `when` missing, and appears to be a current scheduled snapshot; event timing needs archival validation. |
| Financial statements | **UNSAFE historically** | Period end but no filing/acceptance/vintage; today's restatements can leak into past rows. |
| Options | **PARTIAL / research-only** | 2019+, daily aggregates, irregular cadence, substantial IV missingness; no contract identity, volume or OI. |
| SEC filing text/XBRL | **NO corpus yet; open path exists** | EDGAR can supply accepted-at, accession and as-reported facts, but the local build has not occurred. |
| PIT security identity / SIC / size | **NO** | Current symbol snapshot is not an identifier history; neutralization would look ahead. |
| Insider Form 4 | **NO** | Public SEC source exists; no normalized local event table. |
| 13F / institutional | **NO** | Public filings exist but reporting lag/entity mapping and amendments require a dedicated build. |
| Short interest / borrow | **NO** | No local historical borrow/short-interest panel; complete history is usually licensed. |
| News/transcripts | **NO** | No legally licensed historical corpus with event timestamps. |

## Matrix conclusion

The best local-compute match is not the most elaborate published model. It is
a **regularized linear baseline plus a boosted tree on a new SEC-as-reported,
PIT-identified characteristic panel**, evaluated with the already successful
top-k dropout portfolio rule. That combination tests information content while
holding portfolio implementation constant. The immediate experiment before
that build is EXP-010A, a ten-seed noise-floor estimate of the existing frozen
model; it prevents a future data gain smaller than approximately 0.003 IC or
0.07 Sharpe from being misread as discovery.
