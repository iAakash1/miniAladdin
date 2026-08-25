/* ============================================================
   API types — mirrors the FastAPI backend response shapes,
   captured from the live service (July 2026).
   ============================================================ */

export type Verdict = 'Strong Buy' | 'Buy' | 'Hold' | 'Sell' | 'Strong Sell'

/** Raw shape of GET /api/macro */
export interface RawMacroResponse {
  risk_multiplier: number
  stats?: {
    yield_spread?: number
    inflation_rate?: string // "4.47%"
    fed_funds_rate?: string // "3.63%"
    yield_curve_inverted?: boolean
    status?: string // "NORMAL" | "ELEVATED" | ...
    recession_warning?: boolean
  }
  elapsed_seconds?: number
}

/** Macro block nested inside GET /api/research (flat, unlike /api/macro) */
export interface RawResearchMacro {
  risk_multiplier?: number
  yield_spread?: number
  inflation_rate?: string
  fed_funds_rate?: string
  yield_curve_inverted?: boolean
  status?: string
  recession_warning?: boolean
}

export interface RawTechnicals {
  ticker?: string
  current_price?: number
  return_5d?: number
  return_21d?: number
  volatility?: number
  sharpe_ratio?: number
  sortino_ratio?: number
  rsi_14?: number
  max_drawdown?: number
  momentum?: number
  raw_signal?: string
  risk_adjusted_signal?: string
  macd_crossover?: string | null
  macd_histogram?: number | null
  pe_ratio?: number | null
  forward_pe?: number | null
  eps?: number | null
  analyst_target?: number | null
  week_52_high?: number | null
  week_52_low?: number | null
  beta?: number | null
  market_cap?: string | null // pre-formatted, e.g. "$4.79T"
  sector?: string | null
  company_name?: string | null
}

export interface RawHeadline {
  title?: string
  score?: number
  label?: string
  source?: string
  url?: string
  published_at?: string
  corroborated_by?: string[]
  image_url?: string
  sentiment_score?: number | null
  sentiment_label?: string | null
  sentiment_source?: string | null
  relevance?: number | null
  author?: string
}

export interface RawSentiment {
  average_score?: number
  dominant_label?: string
  headline_count?: number
  headlines?: RawHeadline[]
}

/** Raw AI explanation block (additive; null in fast mode). Narrative fields
    come from the model; recommendation/confidence/risk are engine values
    attached server-side. */
export interface RawFactorImpact {
  contribution: number
  factors: Array<{ name: string; contribution: number }>
}

export interface RawFactorImpacts {
  momentum?: RawFactorImpact
  quality?: RawFactorImpact
  value?: RawFactorImpact
  pead?: RawFactorImpact
  news?: RawFactorImpact
}

export interface RawAiAnalysis {
  recommendation?: string
  confidence?: number
  risk?: string
  executive_summary?: string
  investment_thesis?: string
  verdict_rationale?: string
  bull_case?: string
  bear_case?: string
  technical_reasoning?: string
  momentum_impact?: string
  quality_impact?: string
  value_impact?: string
  pead_impact?: string
  macro_reasoning?: string
  news_reasoning?: string
  risk_reasoning?: string
  confidence_reason?: string
  top_positive_narrative?: string
  top_negative_narrative?: string
  key_catalysts?: string[]
  key_risks?: string[]
  things_to_watch?: string[]
  investment_horizon?: string
  market_outlook?: string
  conclusion?: string
  factor_impacts?: RawFactorImpacts
  generated?: boolean
  model?: string | null
  cached?: boolean
}

export interface ConfidenceComponent {
  component: string
  points: number
}

/** Raw v2 scorecard (additive `quant` field; null in fast/legacy mode) */
export interface RawQuant {
  raw_score?: number
  ungated_score?: number
  verdict?: string
  raw_verdict?: string
  confidence?: number
  confidence_losses?: Array<{ component: string; points: number }>
  uncertainty?: number
  uncertainty_components?: Record<string, number>
  conflict_index?: number
  momentum_score?: number | null
  fundamental_score?: number | null
  quality_score?: number | null
  news_score?: number | null
  reversal_score?: number | null
  macro_gate?: number
  stress_probability?: number | null
  risk_score?: number
  risk_components?: Array<{ name: string; percentile: number; weight: number; contribution: number }>
  weights_used?: Record<string, number>
  regimes?: string[]
  factors?: Array<{
    name: string
    family: string
    value?: number | null
    z?: number | null
    score?: number | null
    contribution: number
  }>
  data_completeness?: number
  model_version?: string
}

export interface QuantFactor {
  name: string
  family: string
  value: number | null
  z: number | null
  score: number | null
  contribution: number
}

export interface QuantCard {
  rawScore: number
  ungatedScore: number
  verdict: string
  rawVerdict: string
  confidence: number
  confidenceLosses: Array<{ component: string; points: number }>
  uncertainty: number
  uncertaintyComponents: Record<string, number>
  conflictIndex: number
  momentumScore: number | null
  fundamentalScore: number | null
  qualityScore: number | null
  newsScore: number | null
  reversalScore: number | null
  macroGate: number
  stressProbability: number | null
  riskScore: number
  riskComponents: Array<{ name: string; percentile: number; weight: number; contribution: number }>
  weightsUsed: Record<string, number>
  regimes: string[]
  factors: QuantFactor[]
  dataCompleteness: number
  modelVersion: string
}

/** Raw shape of GET /api/research/{ticker} */
/* ---------- Technical intelligence (v4.5 additive) ----------
   Deterministic output of src/scoring/technical_intelligence.py — a
   presentation-layer read of the same OHLCV frame the engine scored.
   Passed through verbatim; the frontend computes nothing. */

export type TechTone = 'pos' | 'neg' | 'neutral'

export interface TechIndicatorRow {
  key: string
  label: string
  value: string
  detail: string
  state: string
  tone: TechTone
}

export interface TechRegime {
  label: string
  tone: TechTone
  note: string
}

export interface TechLevels {
  close: number
  support: number
  resistance: number
  support_distance_pct: number
  resistance_distance_pct: number
  lookback_days: number
}

export interface TechnicalIntelligence {
  indicators: TechIndicatorRow[]
  regimes: { trend: TechRegime; momentum: TechRegime; volatility: TechRegime; volume: TechRegime }
  levels: TechLevels
  findings: Array<{ text: string; tone: TechTone }>
  as_of: string
  bars: number
}

export interface StreetIntelligence {
  recommendations?: {
    period: string; analysts: number; strong_buy: number; buy: number
    hold: number; sell: number; strong_sell: number
    buy_ratio: number | null; trend: 'improving' | 'steady' | 'deteriorating'; months: number
  }
  surprises?: {
    quarters: number; beats: number; avg_surprise_pct: number
    last_surprise_pct: number | null; last_period: string
  }
  insider?: { mspr: number; net_shares: number | null; read: 'buying' | 'selling' | 'neutral' }
  findings: Array<{ text: string; tone: TechTone }>
}

export interface RawResearchResponse {
  ticker?: string
  macro?: RawResearchMacro
  technicals?: RawTechnicals
  sentiment?: RawSentiment | null
  verdict?: string
  // v1.1 additive fields
  confidence?: number // 0–100
  confidence_breakdown?: ConfidenceComponent[]
  risk_level?: string // "LOW" | "MEDIUM" | "HIGH"
  rationale?: string
  quant?: RawQuant | null
  ai?: RawAiAnalysis | null
  disclaimer?: string
  elapsed_seconds?: number
  mode?: string
  // v3.5 additive: id of the automatically persisted history row (null when
  // persistence or authentication is unavailable).
  history_id?: string | null
  // v4.5 additive: deterministic technical read (null on thin history).
  technical_intelligence?: TechnicalIntelligence | null
  street_intelligence?: StreetIntelligence | null
  /** v5 additive: chain of custody for this run (see src/services/provenance.py). */
  provenance?: Provenance | null
  /** v5.1 additive: parallel multi-vendor blocks. Null when no vendor
   *  contributed — never a fabricated stand-in. */
  consensus_price?: ConsensusPrice | null
  series_integrity?: SeriesIntegrity | null
  statements?: StatementUnion | null
  news_stream?: NewsStream | null
  profile?: CompanyProfile | null
  filings?: FilingsBlock | null
  ratios?: RatiosBlock | null
  macro_context?: MacroContext | null
  ownership?: OwnershipBlock | null
  analyst?: AnalystBlock | null
  detail?: string
}

/* ---------- Decision provenance ---------- */

/** How an input fared. `ok` means a live source answered; `degraded` means it
 *  answered from a stale cache, a fallback vendor, or with vendors
 *  disagreeing; `missing` means nothing answered at all. */
export type InputHealth = 'ok' | 'degraded' | 'missing'

export interface ProvenanceInput {
  /** What the input is, in the reader's language — "Daily price history". */
  label: string
  /** Which stage of the pipeline it belongs to. */
  kind: 'market' | 'fundamental' | 'evidence' | string
  detail: string | null
  /** Which parts of the decision consumed it. */
  used_for: string[]
  health: InputHealth
  /** Vendor that actually answered. Null when nothing did. */
  source: string | null
  sources_consulted: string[]
  confidence: number | null
  cached: boolean
  stale: boolean
  /** Coarse relative age — "just now", "4h ago". */
  age: string | null
  /** Why the input is degraded or missing. Null when it is neither. */
  note: string | null
  /** True when this input came from a parallel fan-out over every capable
   *  vendor rather than from a first-answer-wins chain. */
  parallel?: boolean
  /** Per-vendor outcome, present only on parallel inputs. */
  contributors?: Array<{
    provider: string
    ok: boolean
    status: string
    latency_ms: number
    error: string | null
  }>
}

/** Cross-vendor price agreement. Every vendor that could quote the symbol was
 *  asked; none was discarded. */
/** Cross-vendor agreement on the daily close series.
 *
 *  Separate from `ConsensusPrice` because it answers a different question.
 *  The consensus strip asks whether vendors agree on *the price now*; this
 *  asks whether they agree on *the history* — and the specific failure it
 *  exists to expose is a vendor returning raw closes where the others return
 *  split-adjusted ones, which is invisible in any single series and corrupts
 *  every technical reading taken from it.
 */
export interface SeriesIntegrity {
  providers: string[]
  /** Bars each vendor returned, by vendor. */
  coverage: Record<string, number>
  /** Sessions at least two vendors both covered — where comparison is possible. */
  shared_sessions: number
  union_sessions: number
  agreeing_sessions: number
  agreement_pct: number
  max_divergence_pct: number
  tolerance_pct: number
  conflict_count: number
  conflicts: Array<{
    date: string
    divergence_pct: number
    readings: Record<string, number>
  }>
  /** A vendor whose closes sit at a stable multiple of the others: an
   *  adjustment-policy difference, not a bad print. `likely_split` is named
   *  only when the ratio is unmistakably a plain split. */
  adjustment_mismatch: Array<{
    provider: string
    ratio: number
    stability: number
    sessions: number
    likely_split: string | null
  }>
  /** Sessions a vendor is missing relative to the union. Absent when none. */
  session_gaps: Record<string, number>
}

export interface ConsensusPrice {
  consensus: number
  low: number
  high: number
  dispersion_pct: number
  provider_count: number
  agreeing: number
  agreement: string
  conflict: boolean
  readings: Array<{
    provider: string
    price: number
    basis: string | null
    bid: number | null
    ask: number | null
    spread_bps: number | null
    volume: number | null
    as_of: string | null
    latency_ms: number
  }>
  bid: number | null
  ask: number | null
  spread_bps: number | null
  spread_source: string | null
  volume: number | null
  /** Session context, each field attributed to the vendor that supplied it.
   *  Deliberately not reconciled: a session high is a fact about one venue's
   *  tape, an average volume uses a window each vendor picks for itself, and
   *  a moving average carries its vendor's adjustment conventions. A median
   *  of any of them would describe no actual venue. */
  session: Record<string, { value: number; provider: string }> | null
}

/** Union of reported statement figures across every entitled vendor. */
export interface StatementUnion {
  period: string
  providers: string[]
  fields: Record<string, {
    value: number
    providers: string[]
    observations: Array<{ provider: string; value: number }> | null
    agrees: boolean
  }>
  conflicts: Array<{
    field: string
    observations: Array<{ provider: string; value: number }>
    spread_pct: number
  }>
  history: Array<Record<string, number | string>>
}

export interface NewsStream {
  collected: number
  unique: number
  providers: string[]
  corroborated: number
  categories: Record<string, number>
  with_image?: number
  /** Vendor-scored tone, over the articles that actually carry a score.
   *  Null when no vendor in the fan-out scores its feed — which is
   *  different from a neutral reading. */
  sentiment?: {
    scored: number
    unscored: number
    positive: number
    negative: number
    neutral: number
    mean: number
    source: string | null
  } | null
}

/** One SEC filing, from EDGAR. Primary-source evidence: this is the document
 *  itself, not a vendor's reading of it. */
export interface SecFiling {
  form: string
  meaning: string
  filed_at: string
  report_date: string | null
  accession: string
  url: string
  items: string | null
}

/** Valuation, margin, return, growth and leverage ratios.
 *
 *  Every key carries its own period — `_ttm`, `_3y`, `_5y`, `_yoy` — because
 *  that is what makes them comparable. A schema that called both a trailing
 *  margin and a five-year average `margin` would invite exactly the kind of
 *  averaging this system refuses to do. */
export interface RatiosBlock {
  pe_ratio?: number
  price_to_sales?: number
  price_to_book?: number
  ev_to_ebitda?: number
  ev_to_revenue?: number
  gross_margin_ttm?: number
  operating_margin_ttm?: number
  net_margin_ttm?: number
  net_margin_5y?: number
  roe_ttm?: number
  roa_ttm?: number
  roi_ttm?: number
  revenue_growth_ttm_yoy?: number
  revenue_growth_3y?: number
  eps_growth_ttm_yoy?: number
  eps_growth_3y?: number
  current_ratio?: number
  quick_ratio?: number
  debt_to_equity?: number
  long_term_debt_to_equity?: number
  payout_ratio_ttm?: number
  dividend_yield?: number
  /** Which vendor supplied the set. Not reconciled across vendors: these are
   *  one vendor's consistently-computed family, and mixing definitions
   *  between vendors is precisely what produces meaningless ratios. */
  source?: string
}

/** Who holds the shares, and how many are sold short.
 *
 *  Positions, not performance — which is why this is its own block rather
 *  than more fields on the ratios object. Percentages arrive as fractions
 *  (0.664, not 66.4) and are formatted at the edge. */
export interface OwnershipBlock {
  symbol: string
  shares_outstanding: number | null
  float_shares: number | null
  held_percent_insiders: number | null
  held_percent_institutions: number | null
  shares_short: number | null
  short_percent_of_float: number | null
  short_ratio: number | null
  /** Settlement date. Exchanges publish short interest twice a month, so a
   *  figure without this date is close to meaningless. */
  short_interest_date: string | null
  source: string
}

export interface AnalystReading {
  target_mean: number | null
  target_high: number | null
  target_low: number | null
  analyst_count: number | null
  recommendation: string | null
  recommendation_mean: number | null
  source: string
}

/** One entry per vendor, deliberately not reduced to a single consensus:
 *  each vendor polls a different analyst set, so a median across them would
 *  be a consensus of no actual group of people. */
export interface AnalystBlock {
  readings: AnalystReading[]
  vendor_count: number
}

/** One value as the company itself tagged it, with the document it came from. */
export interface XbrlFact {
  fiscal_year: number
  value: number
  unit: string
  form: string
  filed: string
}

/** Year-over-year change from consecutive fiscal years of the same concept.
 *  The prior value travels with the percentage so the arithmetic is checkable
 *  against the facts rendered beside it. */
export interface XbrlTrend {
  concept: string
  latest_year: number
  latest_value: number
  prior_year: number
  prior_value: number
  change_pct: number
  unit: string
  form: string
  filed: string
}

/** A figure the company later reported differently for the same period.
 *
 *  Both filing dates survive so a reader can open the original and the
 *  revision and check the claim. */
export interface Restatement {
  label: string
  concept: string
  period_start: string | null
  period_end: string
  unit: string
  form: string
  original_value: number
  original_filed: string
  revised_value: number
  revised_filed: string
  change_pct: number
  revisions: number
}

/** One macro observation, carrying its own publication date.
 *
 *  The date is per-row on purpose: macro series publish on different
 *  cadences — the policy rate monthly, Treasury yields daily — so a single
 *  "as of" for the block would be wrong for most of it. */
export interface MacroRate {
  series_id: string
  label: string
  unit: string
  /** What this changes about a valuation, not what the series is. */
  why: string
  value: number
  as_of: string
  prior: number | null
  change: number | null
  source: string
}

export interface MacroStress {
  key: string
  label: string
  value: number
  note: string
  /** Whether the vendor supplied it or we computed it — a distinction the
   *  reader is entitled to. */
  source: string
}

/** The rate and stress environment a valuation sits in. The stress figures
 *  gate the engine's verdict; without them a reader is told a verdict was
 *  gated but not by what. */
export interface MacroContext {
  rates: MacroRate[]
  stress: MacroStress[]
  note: string
}

export interface FilingsBlock {
  filings: SecFiling[]
  /** Present only where a later filing genuinely revised an earlier one. */
  restatements?: Restatement[]
  /** Tagged concepts, newest first. Absent for filers with no XBRL. */
  xbrl?: Record<string, XbrlFact[]>
  xbrl_trend?: XbrlTrend[]
  /** Counts per form, so the shape of recent activity reads before any
   *  single row does. */
  by_form: Record<string, number>
  latest: SecFiling | null
  source: string
}

/** Company identity and narrative, assembled from whichever vendor answered.
 *  Every field optional: vendors differ in what they carry, and an absent
 *  headcount is an absence rather than zero employees. */
export interface CompanyProfile {
  symbol: string
  name: string
  sector: string
  industry: string
  market_cap: number | null
  currency: string
  exchange: string
  website: string
  /** Registrable domain — what the logo provider is keyed on. */
  domain: string
  description: string
  ceo: string
  employees: number | null
  country: string
  ipo_date: string
  beta: number | null
  vendor_image: string
  /** Vendors that contributed at least one field. */
  providers?: string[]
  /** Fields where vendors materially disagreed — surfaced, never averaged. */
  conflicts?: Array<{
    field: string
    observations: Array<{ provider: string; value: number }>
    spread_pct: number
  }>
  /** Which vendors supplied each field, so any value can be traced. */
  field_sources?: Record<string, string[]>
}

export interface Provenance {
  ticker: string
  generated_at: string
  engine_version: string | null
  elapsed_seconds: number | null
  inputs: ProvenanceInput[]
  summary: {
    total: number
    ok: number
    degraded: number
    missing: number
    sources: string[]
  }
  /** Verbatim from the scorecard — what the engine itself docked for. */
  confidence_losses: Array<{ component: string; points: number }>
  ai: {
    generated: boolean | null
    model: string | null
    role: string
  }
  notes: string[]
}

/** Raw shape of GET /api/chart/{ticker} */
export interface RawChartResponse {
  ticker?: string
  prices?: Array<{ date: string; close: number; volume?: number }>
}

/* ---------- Normalized shapes used by the UI ---------- */

export interface Macro {
  srm: number
  yieldSpread: number
  cpi: number
  fedRate: number
  inverted: boolean
  status: string
  recessionWarning: boolean
}

export interface Headline {
  title: string
  score: number
  label: 'Bullish' | 'Bearish' | 'Neutral'
  source: string
  url: string
  publishedAt: string
  /** Vendors that independently carried this same story. More than one is
   *  corroboration — the closest thing a headline feed has to verification. */
  corroboratedBy: string[]
  /** The publisher's own photograph. Never a stock image: editorial context
   *  imagery is a separate field on a separate endpoint. */
  imageUrl: string
  /** Vendor-scored tone for this ticker. Null when nobody scored it, which
   *  is not the same as a neutral score. */
  sentimentScore: number | null
  sentimentLabel: string | null
  /** Which vendor scored the tone. Rendered, not hidden in a tooltip: the
   *  reader must not infer that every vendor independently agreed. */
  sentimentSource: string | null
  /** Search-engine match score, from a search vendor. A different scale from
   *  sentiment relevance and attributed separately. */
  relevance: number | null
  author: string
}

export interface PricePoint {
  date: string
  close: number
  volume: number
}

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH'

export interface FactorImpact {
  contribution: number
  factors: Array<{ name: string; contribution: number }>
}

export interface FactorImpacts {
  momentum: FactorImpact
  quality: FactorImpact
  value: FactorImpact
  pead: FactorImpact
  news: FactorImpact
}

export interface AiAnalysis {
  recommendation: 'BUY' | 'SELL' | 'HOLD'
  confidence: number // 0–100, engine value
  risk: RiskLevel
  executiveSummary: string
  investmentThesis: string
  verdictRationale: string
  bullCase: string
  bearCase: string
  technicalReasoning: string
  momentumImpact: string
  qualityImpact: string
  valueImpact: string
  peadImpact: string
  macroReasoning: string
  newsReasoning: string
  riskReasoning: string
  confidenceReason: string
  topPositiveNarrative: string
  topNegativeNarrative: string
  keyCatalysts: string[]
  keyRisks: string[]
  thingsToWatch: string[]
  investmentHorizon: string
  marketOutlook: string
  conclusion: string
  factorImpacts: FactorImpacts
  generated: boolean
  model: string | null
}

export interface Analysis {
  ticker: string
  /** Server-side history row for this run — enables "Save report". */
  historyId: string | null
  companyName: string
  sector: string | null
  marketCap: string | null

  verdict: Verdict
  riskAdjusted: Verdict
  signalScore: number

  /** v1.1 additive: deterministic engine synthesis */
  engineConfidence: number | null // 0–100
  riskLevel: RiskLevel | null
  rationale: string | null
  quant: QuantCard | null
  ai: AiAnalysis | null

  price: number
  return5d: number
  return21d: number
  volatility: number
  sharpe: number
  sortino: number
  rsi: number
  maxDrawdown: number
  macdCrossover: string | null

  peRatio: number | null
  forwardPe: number | null
  eps: number | null
  beta: number | null
  analystTarget: number | null
  week52High: number | null
  week52Low: number | null

  sentimentScore: number | null
  sentimentLabel: string | null
  headlineCount: number
  headlines: Headline[]

  macro: Macro
  mode: string
  technicalIntelligence: TechnicalIntelligence | null
  streetIntelligence: StreetIntelligence | null
  /** Chain of custody. Null for payloads produced before v5 or by a backend
   *  that does not emit it — the panel simply does not render. */
  provenance: Provenance | null
  consensusPrice: ConsensusPrice | null
  seriesIntegrity: SeriesIntegrity | null
  statements: StatementUnion | null
  newsStream: NewsStream | null
  profile: CompanyProfile | null
  filings: FilingsBlock | null
  ratios: RatiosBlock | null
  macroContext: MacroContext | null
  ownership: OwnershipBlock | null
  analyst: AnalystBlock | null
}

/* ---------- News (our own /api/news aggregation) ---------- */

export type NewsCategory =
  | 'markets'
  | 'economy'
  | 'companies'
  | 'technology'
  | 'crypto'

export interface NewsItem {
  id: string
  title: string
  summary: string
  url: string
  source: string
  category: NewsCategory
  publishedAt: string // ISO
  image: string | null
  author: string | null
}

export interface NewsResponse {
  items: NewsItem[]
  total: number
  page: number
  pageSize: number
  totalPages: number
  updatedAt: string
  sources: Array<{ name: string; ok: boolean }>
}
