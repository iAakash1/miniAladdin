import { normalizeAnalysis } from '@/lib/api'
import type { Analysis, RawResearchResponse } from '@/lib/types'

/**
 * One research run, recorded from production and shown on the public page so
 * a visitor sees the product's real output rather than a mock-up of it.
 *
 * It is a record, not live data: the page labels it with the time it ran, and
 * nothing here is refreshed or implied to be current. Trimmed to what the
 * previews render. Third-party headlines, article images and the narrative
 * sentences that paraphrase them are left out; every figure that remains is
 * the engine's own output or a filed/vendor observation it read.
 */
export const RECORDED_AT = '2026-09-24T12:37:44Z'
export const RECORDED_LABEL = 'Recorded production run · AAPL · 24 Sep 2026, 12:37 UTC'

type Tuple = [id: string, value: number | string | boolean, unit: string | null, source: string]

const EVIDENCE: Tuple[] = [
  ['decision.confidence', 53, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.less_conflicting_signals', -1, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.less_data_completeness', -12, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.less_data_freshness', -3, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.less_family_dispersion', -21, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.less_macro_uncertainty', -1, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.less_model_reliability_unmeasured', -10, 'percent', 'deterministic_engine'],
  ['decision.confidence_component.model_confidence_base', 100, 'percent', 'deterministic_engine'],
  ['decision.recommendation', 'BUY', null, 'deterministic_engine'],
  ['decision.risk', 'MEDIUM', null, 'deterministic_engine'],
  ['decision.verdict', 'Buy', null, 'deterministic_engine'],
  ['factor.high52_prox.contribution', 0.0538, null, 'deterministic_engine'],
  ['factor.r63.contribution', 0.0599, null, 'deterministic_engine'],
  ['factor.rel21_vs_spy.contribution', 0.0579, null, 'deterministic_engine'],
  ['factor.vol_confirm.contribution', -0.0424, null, 'deterministic_engine'],
  ['factor_family.momentum.contribution', 0.1497, null, 'deterministic_engine'],
  ['factor_family.quality.contribution', 0.0572, null, 'deterministic_engine'],
  ['factor_family.value.contribution', -0.0121, null, 'deterministic_engine'],
  ['macro.recession_warning', false, null, 'macro_evidence'],
  ['macro.risk_multiplier', 1, null, 'macro_evidence'],
  ['macro.status', 'STABLE', null, 'macro_evidence'],
  ['macro.yield_curve_inverted', false, null, 'macro_evidence'],
  ['quant.conflict_index', 0.0348, null, 'deterministic_engine'],
  ['quant.fundamental_score', -0.0481, null, 'deterministic_engine'],
  ['quant.momentum_score', 0.4005, null, 'deterministic_engine'],
  ['quant.quality_score', 0.3812, null, 'deterministic_engine'],
  ['quant.raw_score', 0.2071, null, 'deterministic_engine'],
  ['quant.risk_score', 46, null, 'deterministic_engine'],
  ['quant.uncertainty', 0.4652, null, 'deterministic_engine'],
  ['sentiment.average_score', 0.08, null, 'news_reconciliation'],
  ['sentiment.dominant_label', 'Neutral', null, 'news_reconciliation'],
  ['sentiment.headline_count', 50, null, 'news_reconciliation'],
  ['technical.analyst_target', 328.22, null, 'deterministic_engine'],
  ['technical.current_price', 337.02, null, 'deterministic_engine'],
  ['technical.forward_pe', 35.46, null, 'deterministic_engine'],
  ['technical.max_drawdown', -0.1105, null, 'deterministic_engine'],
  ['technical.pe_ratio', 38.92, null, 'deterministic_engine'],
  ['technical.raw_signal', 'Buy', null, 'deterministic_engine'],
  ['technical.return_21d', 0.086, null, 'deterministic_engine'],
  ['technical.return_5d', 0.0139, null, 'deterministic_engine'],
  ['technical.risk_adjusted_signal', 'Buy', null, 'deterministic_engine'],
  ['technical.rsi_14', 62.44, null, 'deterministic_engine'],
  ['technical.sharpe_ratio', 3.0139, null, 'deterministic_engine'],
  ['technical.volatility', 0.2889, null, 'deterministic_engine'],
]

const factor = (name: string, family: string, value: number, z: number | null, score: number, contribution: number) =>
  ({ name, family, value, z, score, contribution })

const input = (label: string, kind: string, detail: string, source: string | null, used: string[], health: 'ok' | 'missing' = 'ok', note: string | null = null, age: string | null = 'just now') =>
  ({ label, kind, detail, source, used_for: used, health, note, age, cached: false, stale: false, confidence: health === 'ok' ? 1 : 0, sources_consulted: source ? source.split(', ') : [] })

const form4 = (accession: string, filed: string, period: string) => ({
  form: '4', meaning: 'Insider transaction', filed_at: filed, report_date: period, accession, items: null,
  url: `https://www.sec.gov/Archives/edgar/data/320193/${accession.replace(/-/g, '')}/xslF345X06/form4.xml`,
})

const trend = (concept: string, latest: number, prior: number, change: number) => ({
  concept, latest_year: 2025, latest_value: latest, prior_year: 2024, prior_value: prior,
  change_pct: change, unit: 'USD', form: '10-K', filed: '2025-10-31',
})

const RAW = {
  ticker: 'AAPL',
  verdict: 'Buy',
  confidence: 53,
  confidence_breakdown: [
    { component: 'Model confidence base', points: 100 },
    { component: 'Less: Family dispersion', points: -21 },
    { component: 'Less: Data completeness', points: -12 },
    { component: 'Less: Data freshness', points: -3 },
    { component: 'Less: Model reliability (unmeasured)', points: -10 },
    { component: 'Less: Macro uncertainty', points: -1 },
    { component: 'Less: Conflicting signals', points: -1 },
  ],
  risk_level: 'MEDIUM',
  rationale: 'Composite score +0.21 (momentum 0.4005, fundamental -0.0481, news 0.0496; macro gate 0.9915); Neutral sentiment (avg score 0.08); Macro environment is STABLE (SRM=1.0)',
  elapsed_seconds: 6.93,
  mode: 'full',
  disclaimer: 'Research and education only — not investment advice.',
  macro: {
    stale: false, source: 'fred', status: 'STABLE',
    fetched_at: '2026-09-24T12:30:42Z',
    yield_spread: 0.26, fed_funds_rate: '3.63%', inflation_rate: '3.40%', risk_multiplier: 1,
    observation_dates: { yield_spread: '2026-09-23', fed_funds_rate: '2026-08-01', inflation_rate: '2026-08-01' },
    recession_warning: false, yield_curve_inverted: false,
  },
  technicals: {
    ticker: 'AAPL', company_name: 'Apple Inc.', sector: 'TECHNOLOGY', market_cap: '$4.92T',
    current_price: 337.02, raw_signal: 'Buy', risk_adjusted_signal: 'Buy',
  },
  quant: {
    model_version: 'scoring-v2.1',
    verdict: 'Buy', raw_verdict: 'Buy', confidence: 53, risk_score: 46,
    raw_score: 0.2071, ungated_score: 0.2085, macro_gate: 0.9915, stress_probability: 0.0171,
    momentum_score: 0.4005, fundamental_score: -0.0481, quality_score: 0.3812, news_score: 0.0496, reversal_score: -0.1841,
    weights_used: { momentum: 0.4, fundamental: 0.2, quality: 0.15, news: 0.2, reversal: 0.05 },
    data_completeness: 1, uncertainty: 0.4652, conflict_index: 0.0348, regimes: [],
    uncertainty_components: { data: 0.15, dispersion: 0.2125, event: 0, freshness: 0.0408, macro: 0.0202, model: 0.15, stability: 0 },
    factors: [
      factor('r63', 'momentum', 0.1509, 1.655, 0.6792, 0.0599),
      factor('r21', 'momentum', 0.086, 1.633, 0.6732, 0.0297),
      factor('vol_confirm', 'momentum', 0.8079, -1.049, -0.4811, -0.0424),
      factor('high52_prox', 'momentum', 0.9919, 1.419, 0.6102, 0.0538),
      factor('rel21_vs_spy', 'momentum', 0.0759, 1.576, 0.6573, 0.0579),
      factor('reversal', 'reversal', 0.0139, -0.372, -0.1841, -0.0092),
      factor('target_upside', 'fundamental', -0.0261, -0.157, -0.0782, -0.0039),
      factor('earnings_yield', 'fundamental', 0.0257, -0.972, -0.4511, -0.0226),
      factor('pe_gap', 'fundamental', 0.0889, 0.593, 0.288, 0.0144),
      factor('pead', 'fundamental', 6.74, 1.348, 0.049, 0.0025),
      factor('gross_profitability', 'quality', 0.5434, 1.422, 0.6115, 0.0306),
      factor('net_issuance', 'quality', -0.0227, 0.454, 0.2234, 0.0112),
      factor('asset_growth', 'quality', -0.0157, 0.638, 0.3087, 0.0154),
      factor('sentiment', 'news', 0.0637, null, 0.0496, 0.0099),
    ],
    confidence_losses: [
      { component: 'Family dispersion', points: 21 },
      { component: 'Data completeness', points: 12 },
      { component: 'Data freshness', points: 3 },
      { component: 'Model reliability (unmeasured)', points: 10 },
      { component: 'Macro uncertainty', points: 1 },
      { component: 'Conflicting signals', points: 1 },
    ],
    risk_components: [
      { name: 'downside_dev', weight: 0.2, percentile: 34.6, contribution: 6.91 },
      { name: 'tail_risk', weight: 0.15, percentile: 66.4, contribution: 9.96 },
      { name: 'drawdown', weight: 0.12, percentile: 25.9, contribution: 3.11 },
      { name: 'vol_regime', weight: 0.13, percentile: 41.7, contribution: 5.43 },
      { name: 'beta', weight: 0.1, percentile: 52.2, contribution: 5.22 },
      { name: 'idiosyncratic', weight: 0.1, percentile: 94.6, contribution: 9.46 },
      { name: 'liquidity', weight: 0.08, percentile: 39.6, contribution: 3.17 },
      { name: 'macro', weight: 0.07, percentile: 1.7, contribution: 0.12 },
      { name: 'sector', weight: 0.05, percentile: 50, contribution: 2.5 },
    ],
  },
  decision_quality: {
    grade: 'STRONG', eligible: true, reasons: [], version: 'decision-quality-v1',
    summary: 'The evidence behind this analysis is complete, fresh and internally consistent.',
  },
  profile: {
    symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', industry: 'Consumer Electronics',
    exchange: 'NMS', country: 'United States', currency: 'USD', market_cap: 4918530277376,
    employees: 150000, domain: 'apple.com', website: 'https://www.apple.com', providers: ['yfinance'], conflicts: [],
    // Not returned by the vendor for this run; absent, not blank.
    description: '', ceo: '', ipo_date: '', beta: null, vendor_image: '',
  },
  provenance: {
    ticker: 'AAPL',
    generated_at: '2026-09-24T12:37:44Z',
    engine_version: 'scoring-v2.1',
    elapsed_seconds: 6.93,
    summary: { total: 14, ok: 12, degraded: 0, missing: 2, sources: ['alpha_vantage', 'alpha_vantage, yfinance', 'sec', 'yfinance'] },
    confidence_losses: [
      { component: 'Family dispersion', points: 21 },
      { component: 'Data completeness', points: 12 },
      { component: 'Data freshness', points: 3 },
      { component: 'Model reliability (unmeasured)', points: 10 },
      { component: 'Macro uncertainty', points: 1 },
      { component: 'Conflicting signals', points: 1 },
    ],
    ai: { generated: true, model: 'deepseek-flash', role: 'explanation only — never produces verdict, confidence, risk level or any factor value' },
    notes: ['Macro regime gate applied at SRM 1.00'],
    inputs: [
      { ...input('Daily price history', 'market', '251 daily bars, 1y window', 'yfinance', ['momentum factors', 'volatility', 'technical intelligence', 'risk score']), age: '2m ago', cached: true },
      input('Company profile', 'fundamental', '12 fields from 1 vendor', 'yfinance', ['sector identity', 'news query', 'logo domain']),
      input('Consensus quote', 'market', '1/1 vendors agree · 0.000% spread', 'yfinance', ['price consensus', 'cross-vendor agreement']),
      input('Reported statements', 'fundamental', '1 line item from 2 vendors', 'alpha_vantage, yfinance', ['valuation ratios', 'fundamental trend']),
      input('Series integrity', 'market', 'only one vendor returned history — nothing to check against', 'yfinance', ['cross-vendor history validation']),
      input('Ownership & short interest', 'fundamental', 'short interest as of 2026-08-30', 'yfinance', ['presentation only — never a scoring input']),
      input('Price targets', 'fundamental', '0 vendor targets', null, ['presentation only — not reconciled across vendors'], 'missing', 'alpha_vantage: unavailable', null),
      input('Analyst targets', 'fundamental', '1 vendor consensus reading', 'yfinance', ['presentation only — not reconciled across vendors']),
      input('SEC filings', 'fundamental', '10 recent filings', 'sec', ['primary-source evidence', 'filing recency']),
      input('Point-in-time filings', 'fundamental', '1650 filed observations', 'sec', ['restatement detection', 'look-ahead-free reads']),
      input('XBRL reported facts', 'fundamental', '10 tagged concepts', 'sec', ['primary-source figures', 'multi-year trend']),
      input('News & headlines', 'evidence', '50 unique of 50 collected · 0 corroborated', 'alpha_vantage', ['news factor', 'evidence weighting', 'sentiment']),
      input('Street & insider activity', 'fundamental', 'analyst ratings, EPS surprises, insider sentiment', null, ['presentation only — never a scoring input'], 'missing', 'no configured vendor can answer this', null),
      { ...input('SPY benchmark series', 'market', '1y daily bars', 'yfinance', ['relative strength vs benchmark']), age: '2m ago', cached: true },
    ],
  },
  consensus_price: {
    consensus: 337.02, low: 337.02, high: 337.02, dispersion_pct: 0, provider_count: 1, agreeing: 1,
    agreement: '1/1', conflict: false, bid: null, ask: null, spread_bps: null, spread_source: null, volume: null, session: null,
    readings: [{ provider: 'yfinance', price: 337.02, basis: null, bid: null, ask: null, spread_bps: null, volume: null, as_of: null, latency_ms: 228.6 }],
  },
  statements: {
    period: '',
    providers: ['alpha_vantage', 'yfinance'],
    fields: {
      eps: {
        value: 8.695, agrees: true, providers: ['alpha_vantage', 'yfinance'],
        observations: [{ provider: 'alpha_vantage', value: 8.66 }, { provider: 'yfinance', value: 8.73 }],
      },
    },
    conflicts: [],
    history: [],
  },
  filings: {
    source: 'SEC EDGAR',
    by_form: { '4': 8, '10-Q': 1, '8-K': 1 },
    filings: [
      form4('0001140361-26-037020', '2026-09-17', '2026-09-15'),
      form4('0001140361-26-036226', '2026-09-10', '2026-09-08'),
      form4('0001140361-26-035636', '2026-09-03', '2026-09-01'),
      form4('0001140361-26-035362', '2026-09-01', '2026-09-01'),
      form4('0001140361-26-034741', '2026-08-27', '2026-08-25'),
      form4('0001140361-26-033928', '2026-08-20', '2026-08-18'),
      form4('0001140361-26-032884', '2026-08-13', '2026-08-11'),
      {
        form: '10-Q', meaning: 'Quarterly report', filed_at: '2026-07-31', report_date: '2026-06-27',
        accession: '0000320193-26-000020', items: null,
        url: 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm',
      },
      {
        form: '8-K', meaning: 'Material event', filed_at: '2026-07-30', report_date: '2026-07-30',
        accession: '0000320193-26-000018', items: '2.02,9.01',
        url: 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/aapl-20260730.htm',
      },
      form4('0001140361-26-025622', '2026-06-17', '2026-06-15'),
    ],
    latest: form4('0001140361-26-037020', '2026-09-17', '2026-09-15'),
    xbrl_trend: [
      trend('Shareholders’ equity', 73733000000, 56950000000, 29.47),
      trend('Cash & equivalents', 35934000000, 29943000000, 20.01),
      trend('Net income', 112010000000, 93736000000, 19.5),
      trend('R&D expense', 34550000000, 31370000000, 10.14),
      trend('Long-term debt', 78328000000, 85750000000, -8.66),
    ],
  },
  ai: {
    generated: true,
    cached: true,
    provider: 'deepseek',
    model: 'deepseek-flash',
    pipeline_mode: 'fast',
    validation: {
      status: 'PASSED',
      section_level_fail_closed: true,
      dropped_sections: [
        'executive_summary', 'investment_thesis', 'bear_case', 'value_impact', 'macro_reasoning',
        'top_negative_narrative', 'market_outlook', 'key_catalysts.2', 'things_to_watch.0',
        'executive_summary.replaced_by_engine',
      ],
    },
    executive_summary: 'BUY at 53% confidence with MEDIUM risk.',
    verdict_rationale: 'The deterministic engine returns Buy with 53% confidence and MEDIUM risk. The composite score of 0.21 is driven by momentum 0.4005 and quality 0.3812, partially offset by a fundamental score of -0.0481. Macro conditions are STABLE with a risk multiplier of 1.0, supporting the verdict.',
    bull_case: 'Momentum is the strongest family, contributing 0.1497, with r63 at 0.0599, rel21_vs_spy at 0.0579 and high52_prox at 0.0538. Quality adds 0.0572. The 21-day return is 8.6% and the Sharpe ratio is 3.01. Macro is STABLE with no recession warning and no yield curve inversion.',
    bear_case: '',
    key_risks: [
      'Negative fundamental score of -0.0481 and value contribution of -0.0121.',
      'Current price of 337.02 exceeds the analyst target of 328.22.',
      'Elevated valuation with a PE ratio of 38.92 and forward PE of 35.46.',
    ],
    key_catalysts: ['Momentum factor strength, with a family contribution of 0.1497 and a momentum score of 0.4005.'],
    things_to_watch: [
      'Macro status and risk multiplier, currently STABLE at 1.0.',
      'Sentiment, currently Neutral with an average score of 0.08 across 50 headlines.',
    ],
    conclusion: 'The deterministic engine returns Buy at 53% confidence with MEDIUM risk. Momentum at 0.4005 and quality at 0.3812 drive the 0.21 composite, while the fundamental score of -0.0481 and value contribution of -0.0121 weigh against. Macro is STABLE and sentiment Neutral.',
    confidence_reason: 'Confidence is 53%, starting from a 100% base. Deductions are family dispersion -21, data completeness -12, model reliability unmeasured -10, data freshness -3, macro uncertainty -1 and conflicting signals -1. Uncertainty is 46.52%.',
    risk_reasoning: 'Risk is MEDIUM with a risk score of 46. Uncertainty is 46.52% and the conflict index is 3.48%. Volatility is 28.89% and max drawdown is -11.05%. Confidence is reduced by family dispersion of -21 and data completeness of -12.',
    evidence_links: {
      executive_summary: ['decision.recommendation', 'decision.confidence', 'decision.risk'],
      verdict_rationale: ['decision.verdict', 'decision.confidence', 'decision.risk', 'quant.raw_score', 'quant.momentum_score', 'quant.quality_score', 'quant.fundamental_score', 'macro.status', 'macro.risk_multiplier'],
      bull_case: ['factor_family.momentum.contribution', 'factor.r63.contribution', 'factor.rel21_vs_spy.contribution', 'factor.high52_prox.contribution', 'factor_family.quality.contribution', 'technical.return_21d', 'technical.sharpe_ratio', 'macro.status', 'macro.recession_warning', 'macro.yield_curve_inverted'],
      key_risks: [
        ['quant.fundamental_score', 'factor_family.value.contribution'],
        ['technical.current_price', 'technical.analyst_target'],
        ['technical.pe_ratio', 'technical.forward_pe'],
      ],
      key_catalysts: [['factor_family.momentum.contribution', 'quant.momentum_score']],
      things_to_watch: [
        ['macro.status', 'macro.risk_multiplier'],
        ['sentiment.dominant_label', 'sentiment.average_score', 'sentiment.headline_count'],
      ],
      conclusion: ['decision.verdict', 'decision.confidence', 'decision.risk', 'quant.raw_score', 'quant.momentum_score', 'quant.quality_score', 'quant.fundamental_score', 'factor_family.value.contribution', 'macro.status', 'sentiment.dominant_label'],
      confidence_reason: ['decision.confidence', 'decision.confidence_component.model_confidence_base', 'decision.confidence_component.less_family_dispersion', 'decision.confidence_component.less_data_completeness', 'decision.confidence_component.less_model_reliability_unmeasured', 'decision.confidence_component.less_data_freshness', 'decision.confidence_component.less_macro_uncertainty', 'decision.confidence_component.less_conflicting_signals', 'quant.uncertainty'],
      risk_reasoning: ['decision.risk', 'quant.risk_score', 'quant.uncertainty', 'quant.conflict_index', 'technical.volatility', 'technical.max_drawdown', 'decision.confidence_component.less_family_dispersion', 'decision.confidence_component.less_data_completeness'],
    },
    evidence: EVIDENCE.map(([id, value, unit, source]) => ({
      id, field: id, value, unit, source, validation: 'VERIFIED', reconciliation: 'SINGLE_SOURCE', freshness: 'current_request', observed_at: null,
    })),
  },
} satisfies RawResearchResponse

/** The recorded run, normalised exactly as a live response would be. */
export const recordedAnalysis: Analysis = normalizeAnalysis(RAW)
