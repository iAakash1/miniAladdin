'use client'

/*
 * The Explore client.
 *
 * Mirrors the FastAPI shapes exactly, with every financial field nullable,
 * because every one of them genuinely can be absent and the backend says so
 * rather than sending a zero. Nothing here coerces a missing number into a
 * present one — `?? 0` on a price is how "we could not price this" becomes
 * "this is worth nothing".
 */

export type CategoryKey =
  | 'overall' | 'trending' | 'momentum' | 'quality' | 'value'
  | 'profitability' | 'low_risk' | 'news_buzz' | 'analyst_upside'

export interface ExploreCategory {
  key: CategoryKey
  label: string
  field: string
  descending: boolean
  blurb: string
}

export interface ExploreRow {
  symbol: string
  company_name: string
  sector: string
  price: number | null
  price_as_of: string | null
  price_age_days: number | null
  stale: boolean
  model_signal: string | null
  signal_strength: number | null
  signal_percentile: number | null
  confidence: number | null
  risk_score: number | null
  risk_level: string | null
  data_completeness: number | null
  overall_rank: number | null
  trend_score: number | null
  trend_direction: string | null
  momentum_percentile: number | null
  quality_percentile: number | null
  value_percentile: number | null
  profitability_percentile: number | null
  profitability_sector_percentile: number | null
  news_buzz: number | null
  analyst_upside: number | null
  analyst_count: number | null
  operating_margin_ttm: number | null
  gross_margin_ttm: number | null
  net_margin_ttm: number | null
  roe_ttm: number | null
  pe_ratio: number | null
  forward_pe: number | null
  headline_count: number | null
  sentiment_avg: number | null
  top_positive: string | null
  top_caution: string | null
  eligible: boolean
  exclusion_reasons: string[]
  validation_state: string
}

export interface ExploreResponse {
  category: string
  results: ExploreRow[]
  count: number
  eligible_count: number
  evaluated_count: number
  generated_at: string
  data_as_of: string | null
  universe_version: string
  scoring_version: string
  stale: boolean
  stale_reason: string | null
}

export interface RecommendationsResponse extends Omit<ExploreResponse, 'category'> {
  disclaimer: string
}

export interface ExploreQuery {
  category?: CategoryKey
  sector?: string
  signal?: string
  max_risk?: number
  min_confidence?: number
  min_data_completeness?: number
  limit?: number
}

function query(params: ExploreQuery): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  return search.toString()
}

export async function fetchCategories(): Promise<ExploreCategory[]> {
  const res = await fetch('/api/explore/categories')
  if (!res.ok) throw new Error(`categories unavailable (${res.status})`)
  const body = (await res.json()) as { categories: ExploreCategory[] }
  return body.categories
}

export async function fetchExplore(params: ExploreQuery = {}): Promise<ExploreResponse> {
  const res = await fetch(`/api/explore?${query(params)}`)
  if (res.status === 503) throw new Error('Rankings are being rebuilt. Try again shortly.')
  if (!res.ok) throw new Error(`Rankings unavailable (${res.status})`)
  return (await res.json()) as ExploreResponse
}

export async function fetchRecommendations(limit = 5): Promise<RecommendationsResponse> {
  const res = await fetch(`/api/recommendations?limit=${limit}`)
  if (res.status === 503) throw new Error('Rankings are being rebuilt. Try again shortly.')
  if (!res.ok) throw new Error(`Top ideas unavailable (${res.status})`)
  return (await res.json()) as RecommendationsResponse
}

/** "12 min ago", or null when there is no timestamp to describe. */
export function freshness(iso: string | null): string | null {
  if (!iso) return null
  const then = Date.parse(iso)
  if (!Number.isFinite(then)) return null
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`
}

/** Tone for a model signal. Never the only carrier of meaning — the label
 *  is always rendered too, so the verdict survives for a reader who cannot
 *  distinguish the colours. */
export function signalTone(signal: string | null): 'positive' | 'negative' | 'neutral' {
  const s = (signal ?? '').toLowerCase()
  if (s.includes('buy')) return 'positive'
  if (s.includes('sell')) return 'negative'
  return 'neutral'
}
