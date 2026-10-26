'use client'

/**
 * Market data for tracked securities, from `/api/tracker`.
 *
 * A row carries two observations kept apart on purpose: the latest quote, with
 * the provider's own timestamp and a freshness class, and period performance
 * computed on daily closes through the last close. Nothing here fills a gap:
 * a period the history does not cover is null, and a missing quote is shown
 * as missing (with the last close labelled as a close), never as a live price.
 *
 * Fetched 25 symbols per request and refreshed on a modest timer only while
 * the page is visible; the backend caches quotes for a minute and daily series
 * for five, so a refresh is cheap and never a request per row per provider.
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import { authFetch } from './persistence'

export type Freshness = 'live' | 'delayed' | 'end_of_day' | 'stale' | 'undated'
export type Period = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y'
export const PERIODS: Period[] = ['1D', '1W', '1M', '3M', '6M', '1Y']

export interface TrackerRow {
  symbol: string
  currency?: string
  price: number | null
  as_of?: string | null
  source?: string | null
  cached?: boolean
  freshness?: Freshness
  previous_close?: number | null
  change?: number | null
  change_pct?: number | null
  quote_status: 'ok' | 'stale' | 'unavailable' | 'no_data' | 'invalid' | 'error'
  performance?: Partial<Record<Exclude<Period, '1D'>, number | null>>
  history?: { source: string; sessions: number; through: string; basis: string; stale: boolean } | null
  spark?: number[]
  last_close?: number | null
  last_close_date?: string | null
}

const PAGE = 25
export const REFRESH_MS = 60_000

export async function fetchTracker(symbols: string[]): Promise<Record<string, TrackerRow>> {
  const unique = [...new Set(symbols.map((s) => s.toUpperCase()))]
  const pages: string[][] = []
  for (let i = 0; i < unique.length; i += PAGE) pages.push(unique.slice(i, i + PAGE))
  const out: Record<string, TrackerRow> = {}
  // Pages one after another: a long list should not open a burst of parallel
  // requests that each fan out to providers.
  for (const page of pages) {
    const r = await authFetch(`/api/tracker?symbols=${encodeURIComponent(page.join(','))}`)
    if (!r.ok) throw new Error(`market data returned ${r.status}`)
    const body = await r.json() as { rows: TrackerRow[] }
    for (const row of body.rows) out[row.symbol] = row
  }
  return out
}

export function useTracker(symbols: string[]): {
  rows: Record<string, TrackerRow>; at: Date | null; loading: boolean; error: string | null; refresh: () => void
} {
  const key = [...new Set(symbols.map((s) => s.toUpperCase()))].sort().join(',')
  const [rows, setRows] = useState<Record<string, TrackerRow>>({})
  const [at, setAt] = useState<Date | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tick = useRef(0)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!key) { setRows({}); return }
    let alive = true
    const run = async () => {
      const seq = ++tick.current
      setLoading(true)
      try {
        const next = await fetchTracker(key.split(','))
        if (alive && seq === tick.current) { setRows(next); setAt(new Date()); setError(null) }
      } catch (e) {
        if (alive && seq === tick.current) setError(e instanceof Error ? e.message : 'market data did not answer')
      } finally {
        if (alive && seq === tick.current) setLoading(false)
      }
    }
    void run()
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void run() }, REFRESH_MS)
    return () => { alive = false; clearInterval(timer) }
  }, [key, nonce])

  return { rows, at, loading, error, refresh: () => setNonce((n) => n + 1) }
}

/** The move for a period: the quote's change for 1D, daily closes otherwise. */
export function periodValue(row: TrackerRow | undefined, period: Period): number | null {
  if (!row) return null
  if (period === '1D') return row.change_pct ?? null
  const v = row.performance?.[period]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export const FRESHNESS_LABEL: Record<Freshness, string> = {
  live: 'live', delayed: 'delayed', end_of_day: 'last close', stale: 'stale', undated: 'undated',
}

export interface SortInput {
  ticker: string
  row?: TrackerRow
  alerts: number
  signalConfidence: number | null
  position: number
}

export type TrackerSort = 'manual' | 'symbol' | 'change' | 'change_pct' | 'perf' | 'updated' | 'alerts' | 'signal'

/**
 * Stable sort. Missing values sort last in either direction, so an unavailable
 * quote never floats to the top of a "biggest gainers" view, and ties keep the
 * list's own order.
 */
export function sortTracker(items: SortInput[], key: TrackerSort, period: Period, descending = true): SortInput[] {
  const value = (i: SortInput): number | string | null => {
    switch (key) {
      case 'manual': return i.position
      case 'symbol': return i.ticker
      case 'change': return i.row?.change ?? null
      case 'change_pct': return i.row?.change_pct ?? null
      case 'perf': return periodValue(i.row, period)
      case 'updated': return i.row?.as_of ? Date.parse(i.row.as_of) || null : null
      case 'alerts': return i.alerts
      case 'signal': return i.signalConfidence
    }
  }
  const dir = key === 'manual' || key === 'symbol' ? 1 : descending ? -1 : 1
  return items
    .map((item, index) => ({ item, index, v: value(item) }))
    .sort((a, b) => {
      if (a.v === null && b.v === null) return a.index - b.index
      if (a.v === null) return 1
      if (b.v === null) return -1
      if (a.v < b.v) return -dir
      if (a.v > b.v) return dir
      return a.index - b.index
    })
    .map((x) => x.item)
}

export function filterTracker(items: SortInput[], query: string, notes: Record<string, { note: string | null; tags: string[] }>): SortInput[] {
  const q = query.trim().toLowerCase()
  if (!q) return items
  return items.filter((i) => {
    const meta = notes[i.ticker]
    return i.ticker.toLowerCase().includes(q)
      || Boolean(meta?.note?.toLowerCase().includes(q))
      || Boolean(meta?.tags.some((t) => t.toLowerCase().includes(q)))
  })
}

export function useSortedTracker(items: SortInput[], key: TrackerSort, period: Period, descending: boolean): SortInput[] {
  return useMemo(() => sortTracker(items, key, period, descending), [items, key, period, descending])
}
