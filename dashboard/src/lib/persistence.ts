'use client'

/*
 * Persistence API client — the only place the frontend talks to the
 * Supabase-backed endpoints. Every call carries the Clerk session token;
 * the browser never touches the database directly.
 */

interface ClerkGlobal {
  session?: { getToken: () => Promise<string | null> } | null
}

async function sessionToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null
  try {
    const clerk = (window as unknown as { Clerk?: ClerkGlobal }).Clerk
    return (await clerk?.session?.getToken()) ?? null
  } catch {
    return null
  }
}

/** fetch() with the Clerk session token attached as a Bearer token. */
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await sessionToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  return fetch(path, { ...init, headers })
}

// ── shared shapes (mirror the FastAPI persistence router) ────────────────────

export interface Position {
  id: string
  ticker: string
  shares: number
  average_price: number
  created_at: string
  updated_at: string
}

export interface HistoryItem {
  id: string
  ticker: string
  company_name: string | null
  verdict: string
  confidence: number | null
  risk_level: string | null
  composite_score: number | null
  created_at: string
}

export interface HistoryPage {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

export interface SavedReport {
  id: string
  analysis_history_id: string
  custom_title: string | null
  notes: string | null
  saved_at: string
  analysis: HistoryItem | null
}

export interface FamilyDelta {
  family: string
  label: string
  before: number | null
  after: number | null
  delta: number
  changed: boolean
}

export interface FactorDelta {
  name: string
  family: string | null
  before: number | null
  after: number | null
  delta: number
  changed: boolean
}

export interface RunSummary {
  id: string
  ticker: string
  company_name: string | null
  verdict: string
  confidence: number | null
  risk_level: string | null
  composite_score: number | null
  created_at: string
}

export interface CompareResult {
  before: RunSummary
  after: RunSummary
  same_ticker: boolean
  factors: FactorDelta[]
  families: FamilyDelta[]
  macro: {
    srm_before: number | null
    srm_after: number | null
    srm_delta: number | null
    gate_before: number | null
    gate_after: number | null
  }
  risk: {
    score_before: number | null
    score_after: number | null
    score_delta: number | null
    level_before: string | null
    level_after: string | null
  }
}

export interface HistoryFilters {
  q?: string
  ticker?: string
  verdict?: string
  from?: string
  to?: string
  sort?: 'newest' | 'oldest' | 'confidence'
  page?: number
  pageSize?: number
}

// ── history ──────────────────────────────────────────────────────────────────

export async function fetchHistory(filters: HistoryFilters = {}): Promise<HistoryPage> {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.ticker) params.set('ticker', filters.ticker)
  if (filters.verdict) params.set('verdict', filters.verdict)
  if (filters.from) params.set('from', filters.from)
  if (filters.to) params.set('to', `${filters.to}T23:59:59Z`)
  if (filters.sort) params.set('sort', filters.sort)
  params.set('page', String(filters.page ?? 1))
  params.set('page_size', String(filters.pageSize ?? 20))
  const res = await authFetch(`/api/history?${params.toString()}`)
  if (!res.ok) throw new Error(String(res.status))
  return res.json()
}

export async function fetchHistoryDetail(id: string): Promise<{ quant_payload: unknown } & HistoryItem> {
  const res = await authFetch(`/api/history/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error(String(res.status))
  return res.json()
}

export async function deleteHistory(id: string): Promise<boolean> {
  const res = await authFetch(`/api/history/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return res.ok
}

export async function fetchComparison(a: string, b: string): Promise<CompareResult> {
  const res = await authFetch(`/api/history/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`)
  if (!res.ok) throw new Error(String(res.status))
  return res.json()
}

// ── saved reports ────────────────────────────────────────────────────────────

export async function fetchSavedReports(): Promise<SavedReport[]> {
  const res = await authFetch('/api/saved-reports')
  if (!res.ok) throw new Error(String(res.status))
  return (await res.json()).saved
}

export async function saveReport(
  historyId: string,
  fields: { custom_title?: string; notes?: string } = {},
): Promise<SavedReport | null> {
  const res = await authFetch('/api/saved-reports', {
    method: 'POST',
    body: JSON.stringify({ analysis_history_id: historyId, ...fields }),
  })
  return res.ok ? res.json() : null
}

export async function updateSavedReport(
  savedId: string,
  fields: { custom_title?: string; notes?: string },
): Promise<SavedReport | null> {
  const res = await authFetch(`/api/saved-reports/${encodeURIComponent(savedId)}`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  })
  return res.ok ? res.json() : null
}

export async function deleteSavedReport(savedId: string): Promise<boolean> {
  const res = await authFetch(`/api/saved-reports/${encodeURIComponent(savedId)}`, {
    method: 'DELETE',
  })
  return res.ok
}

// ── portfolio positions ──────────────────────────────────────────────────────

export async function fetchPositions(): Promise<Position[]> {
  const res = await authFetch('/api/portfolio')
  if (!res.ok) throw new Error(String(res.status))
  return (await res.json()).positions
}

export async function upsertPosition(
  ticker: string,
  shares: number,
  averagePrice: number,
): Promise<Position | null> {
  const res = await authFetch('/api/portfolio', {
    method: 'POST',
    body: JSON.stringify({ ticker, shares, average_price: averagePrice }),
  })
  return res.ok ? res.json() : null
}

export async function patchPosition(
  id: string,
  fields: { shares?: number; average_price?: number },
): Promise<Position | null> {
  const res = await authFetch(`/api/portfolio/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  })
  return res.ok ? res.json() : null
}

export async function deletePosition(id: string): Promise<boolean> {
  const res = await authFetch(`/api/portfolio/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return res.ok
}

/* ── portfolio intelligence ───────────────────────────────────────────────
   Concentration, exposure and risk over the whole book. Computed server-side
   from stored positions and stored analyses — see
   src/services/portfolio_intelligence.py — so the numbers on this screen
   come from one implementation that has tests against hand-worked values,
   rather than from arithmetic reproduced in the client. */

export interface PortfolioIntel {
  covered: boolean
  reason?: string
  positions: number
  total_basis?: number
  weight_basis?: string
  concentration?: {
    hhi: number
    band: 'diversified' | 'moderate' | 'concentrated'
    top_three_pct: number
    top_three: Array<{ ticker: string; weight_pct: number }>
    largest: { ticker: string; weight_pct: number }
  }
  coverage?: {
    scored: number
    unscored: number
    covered_pct: number
    unscored_tickers: string[]
  }
  risk?: {
    weighted_score: number | null
    basis: string
    /** Annualised stdev of the portfolio value's daily returns. Null below
     *  the observation floor — an annualised figure from six days is
     *  arithmetic, not a measurement. */
    volatility_pct?: number | null
    max_drawdown?: DrawdownReport | null
    holding_drawdowns?: Array<{ ticker: string } & Partial<DrawdownReport>>
    top_contributors: Array<{
      ticker: string; weight_pct: number; risk_score: number; risk_share_pct: number
    }>
    top_three_share_pct: number
  }
  sectors?: { rows: Array<{ sector: string; weight_pct: number }>; unknown_pct: number }
  verdict_mix?: { bullish: number; neutral: number; bearish: number }
  headlines?: Array<{ tone: string; text: string }>
  /** ISO-4217 code the figures are denominated in, from the server rather
   *  than assumed — the UI must not hardcode a symbol. */
  currency?: string
  valuation?: PortfolioValuation
  /** Null when too few holdings have enough overlapping history to plot. */
  curve?: PortfolioCurve | null
  /** Null when the benchmark and the book share too few sessions. */
  benchmark?: PortfolioBenchmark | null
  correlation?: CorrelationReport | null
  contributions?: HoldingContribution[]
  range?: string
  ranges?: string[]
  benchmarks?: Array<{ symbol: string; label: string }>
}

export interface PortfolioBenchmark {
  symbol: string
  label: string
  portfolio_return_pct: number
  benchmark_return_pct: number
  outperformance_pct: number
  /** Why this is a return difference and not alpha — rendered, not paraphrased. */
  basis: string
  sessions: number
  from: string
  to: string
  /** Both series rebased to 100 at the first shared date. */
  points: Array<{ date: string; portfolio: number; benchmark: number }>
}

export interface CorrelationReport {
  pairs: Array<{ a: string; b: string; rho: number; sessions: number }>
  highest: { a: string; b: string; rho: number; sessions: number }
  lowest: { a: string; b: string; rho: number; sessions: number }
  high_count: number
  mean_rho: number
  tickers: string[]
}

export interface HoldingContribution {
  ticker: string
  pnl: number
  pnl_pct: number | null
  /** Null when the book's winners and losers roughly cancel — a share of a
   *  near-zero net is arithmetically true and useless. */
  contribution_pct: number | null
  share_of_movement_pct: number | null
}

export interface DrawdownReport {
  pct: number
  peak: number
  trough: number
  peak_index: number
  trough_index: number
}

/** One holding, valued. `priced: false` means no current price could be
 *  fetched — the value fields are null rather than falling back to cost,
 *  which would report the holding as exactly break-even. */
export interface HoldingValuation {
  ticker: string
  shares: number
  avg_price: number
  invested: number
  current_price: number | null
  current_value: number | null
  pnl: number | null
  pnl_pct: number | null
  day_change_pct: number | null
  priced: boolean
  price_note: string | null
  stale?: boolean
  source?: string | null
}

export interface PortfolioValuation {
  rows: HoldingValuation[]
  totals: {
    /** Cost of the whole book — known even when no price is reachable. */
    invested: number
    /** Cost of only the holdings that could be priced. Every figure below
     *  covers this subset, not the whole book. */
    priced_invested: number
    current_value: number | null
    pnl: number | null
    pnl_pct: number | null
    day_pnl: number | null
    day_pnl_pct: number | null
  }
  coverage: {
    priced: number
    unpriced: number
    unpriced_tickers: string[]
    priced_pct: number
  }
}

export interface PortfolioCurve {
  points: Array<{ date: string; value: number }>
  invested_baseline: number
  tickers: string[]
  excluded_tickers: string[]
  /** What the curve does and does not claim — rendered, not paraphrased. */
  assumption: string
}

export async function fetchPortfolioIntel(
  opts: { range?: string; benchmark?: string } = {},
): Promise<PortfolioIntel> {
  const query = new URLSearchParams()
  if (opts.range) query.set('range', opts.range)
  if (opts.benchmark) query.set('benchmark', opts.benchmark)
  const suffix = query.toString() ? `?${query}` : ''
  const res = await authFetch(`/api/portfolio/intelligence${suffix}`)
  if (!res.ok) throw new Error(String(res.status))
  return res.json()
}

// ── profile ──────────────────────────────────────────────────────────────────

export async function syncProfile(fields: {
  email?: string
  full_name?: string
  avatar_url?: string
}): Promise<void> {
  try {
    await authFetch('/api/profile/sync', { method: 'POST', body: JSON.stringify(fields) })
  } catch {
    /* profile sync is best-effort — never surfaces to the user */
  }
}
