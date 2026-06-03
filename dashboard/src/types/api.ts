export interface MacroData {
  srm: number
  srm_status?: string
  yield_spread: number
  cpi: number
  fed_funds_rate: number
  macro_env?: string
}

export interface ResearchResult {
  ticker: string
  current_price?: number
  verdict: string
  signal_score: number
  risk_adjusted_signal?: string
  srm: number

  /* Technicals */
  rsi: number
  sharpe_ratio: number
  sortino_ratio: number
  volatility: number
  momentum: number
  max_drawdown: number

  /* Sentiment */
  sentiment_score: number
  sentiment_label: string
  sentiment_headline_count?: number

  /* MACD / Fundamentals (optional, require API keys) */
  macd?: number
  macd_signal?: number
  pe_ratio?: number
  forward_pe?: number
  eps?: number
  analyst_target?: number
  analyst_upside?: number
  beta?: number
  market_cap?: number
  week52_low?: number
  week52_high?: number

  /* Price history & macro */
  price_history?: Array<{ date: string; close: number }>
  macro: MacroData

  generated_at?: string
  error?: string
}
