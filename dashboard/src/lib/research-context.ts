'use client'

/**
 * The caller's latest research verdict per ticker, with how much it can bear.
 *
 * Shown beside a tracked security and on the order ticket as context. A
 * verdict is never shown bare: it travels with its confidence and with the
 * run's own grade of its evidence, and `signalCaution` says in words when the
 * two do not support acting on it. Nothing in this product turns a verdict
 * into an order.
 */

import { useEffect, useState } from 'react'

import { authFetch } from './persistence'

export interface LatestResearch {
  ticker: string
  history_id?: string | null
  company_name?: string | null
  verdict?: string | null
  confidence?: number | null
  risk_level?: string | null
  evidence_grade?: 'STRONG' | 'ACCEPTABLE' | 'WEAK' | 'INSUFFICIENT' | null
  evidence_reasons?: string[]
  analysed_at?: string | null
}

/** Below this confidence a verdict is shown as weakly supported. */
export const LOW_CONFIDENCE = 50

/**
 * Why this verdict should not be read as a recommendation, or null when the
 * run itself rates its evidence acceptable and its confidence reasonable.
 * Every research output still carries the general caveat; this is the
 * specific one.
 */
export function signalCaution(r: LatestResearch | null | undefined): string | null {
  if (!r || !r.verdict) return null
  const grade = r.evidence_grade ?? null
  if (grade === 'INSUFFICIENT') {
    return `The ${r.verdict} signal rests on insufficient evidence${r.evidence_reasons?.length ? ` (${r.evidence_reasons.join(', ').replace(/_/g, ' ').toLowerCase()})` : ''}. It is not a validated recommendation.`
  }
  if (grade === 'WEAK') return `The ${r.verdict} signal rests on weak evidence. Treat it as a lead to check, not a conclusion.`
  if (typeof r.confidence === 'number' && r.confidence < LOW_CONFIDENCE) {
    return `The ${r.verdict} signal has low confidence (${r.confidence}/100).`
  }
  if (grade === null) return `The evidence behind the ${r.verdict} signal was not graded for this run.`
  return null
}

const cache = new Map<string, { at: number; value: LatestResearch | null }>()
const TTL_MS = 60_000

export async function fetchLatestResearch(tickers: string[]): Promise<Record<string, LatestResearch>> {
  const wanted = [...new Set(tickers.map((t) => t.toUpperCase()).filter(Boolean))]
  const now = Date.now()
  const missing = wanted.filter((t) => !(cache.get(t) && now - (cache.get(t) as { at: number }).at < TTL_MS))
  if (missing.length) {
    try {
      const r = await authFetch(`/api/history/latest?tickers=${encodeURIComponent(missing.join(','))}`)
      if (r.ok) {
        const body = await r.json() as { latest: Record<string, LatestResearch> }
        for (const t of missing) cache.set(t, { at: now, value: body.latest?.[t] ?? null })
      }
    } catch { /* context is optional; the caller shows "no research yet" */ }
  }
  const out: Record<string, LatestResearch> = {}
  for (const t of wanted) {
    const hit = cache.get(t)?.value
    if (hit) out[t] = hit
  }
  return out
}

export function useLatestResearch(tickers: string[]): Record<string, LatestResearch> {
  const key = [...new Set(tickers.map((t) => t.toUpperCase()))].sort().join(',')
  const [state, setState] = useState<Record<string, LatestResearch>>({})
  useEffect(() => {
    if (!key) return
    let alive = true
    void fetchLatestResearch(key.split(',')).then((v) => { if (alive) setState(v) })
    return () => { alive = false }
  }, [key])
  return state
}
