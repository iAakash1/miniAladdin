'use client'

import { useEffect, useMemo, useState } from 'react'

import { readAuthResource } from './auth-resource'
import type { RunSummary } from './persistence'

interface HistoryPage { items: RunSummary[]; total: number }

export interface ResearchIndex {
  status: 'loading' | 'ready' | 'unavailable'
  /** Newest run per ticker, newest first. */
  recent: RunSummary[]
  /** Newest run for a ticker, when this account has researched it. */
  latest: (ticker: string) => RunSummary | undefined
  total: number
}

/**
 * The account's research record, read once per page from the server — a
 * database read, no provider calls. It supplies company names and the last
 * recorded verdict for lists that only store tickers.
 */
export function useResearchHistory(pageSize = 50): ResearchIndex {
  const [state, setState] = useState<{ page?: HistoryPage; failed?: boolean } | null>(null)

  useEffect(() => {
    let alive = true
    readAuthResource<HistoryPage>(`/api/history?page=1&page_size=${pageSize}`, 'snapshot')
      .then((page) => { if (alive) setState({ page }) })
      .catch(() => { if (alive) setState({ failed: true }) })
    return () => { alive = false }
  }, [pageSize])

  return useMemo(() => {
    const items = state?.page?.items ?? []
    const byTicker = new Map<string, RunSummary>()
    for (const run of items) {
      const key = run.ticker.toUpperCase()
      if (!byTicker.has(key)) byTicker.set(key, run)
    }
    return {
      status: state === null ? 'loading' : state.failed ? 'unavailable' : 'ready',
      recent: [...byTicker.values()],
      latest: (ticker: string) => byTicker.get(ticker.toUpperCase()),
      total: state?.page?.total ?? 0,
    }
  }, [state])
}

export function verdictTone(verdict: string | null | undefined): 'pos' | 'neg' | 'muted' {
  if (!verdict) return 'muted'
  if (/buy/i.test(verdict)) return 'pos'
  if (/sell/i.test(verdict)) return 'neg'
  return 'muted'
}
