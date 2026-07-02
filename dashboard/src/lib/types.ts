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
}

export interface RawSentiment {
  average_score?: number
  dominant_label?: string
  headline_count?: number
  headlines?: RawHeadline[]
}

/** Raw shape of GET /api/research/{ticker} */
export interface RawResearchResponse {
  ticker?: string
  macro?: RawResearchMacro
  technicals?: RawTechnicals
  sentiment?: RawSentiment | null
  verdict?: string
  elapsed_seconds?: number
  mode?: string
  detail?: string
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
}

export interface PricePoint {
  date: string
  close: number
  volume: number
}

export interface Analysis {
  ticker: string
  companyName: string
  sector: string | null
  marketCap: string | null

  verdict: Verdict
  riskAdjusted: Verdict
  signalScore: number

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
