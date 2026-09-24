'use client'

import { useEffect, useRef, useState } from 'react'

import { ApiError, fetchAnalysis, fetchChart, normalizeAnalysis, normalizeChartSeries } from '@/lib/api'
import { storedDepth } from '@/lib/report-depth'
import { recordAnalysis } from '@/lib/history'
import { shareResearch, type ResearchPayload } from '@/lib/research-cache'
import { fetchIdentity, type SecurityIdentity } from '@/lib/security'
import { rememberSymbol } from '@/lib/symbols'
import type { Analysis, ChartSeries } from '@/lib/types'
import { FREE_DAILY_LIMIT, bumpTodayCount, readTodayCount } from '@/lib/usage'

export type ResearchRun =
  | { status: 'waiting' }
  | { status: 'running'; startedAt: number }
  | { status: 'ready'; analysis: Analysis; finishedAt: number }
  | { status: 'limited' }
  | { status: 'error'; message: string; code: number | null }

/**
 * The research run for one company: a single authenticated request per
 * visit, shared with every panel that reads research.
 */
export function useResearch(ticker: string, {
  fast, resolved, isPro, onLimit,
}: {
  fast: boolean
  /** Whether the session has resolved; entitlement is unknown before it. */
  resolved: boolean
  isPro: boolean
  onLimit: () => void
}): { run: ResearchRun; retry: () => void } {
  const [run, setRun] = useState<ResearchRun>({ status: 'waiting' })
  const [attempt, setAttempt] = useState(0)
  const delivered = useRef<string | null>(null)
  const limitRef = useRef(onLimit)
  useEffect(() => { limitRef.current = onLimit })

  useEffect(() => {
    if (!resolved) return undefined
    const key = `${ticker}:${fast}:${attempt}`
    if (delivered.current === key) return undefined
    let alive = true

    if (!isPro && readTodayCount() >= FREE_DAILY_LIMIT) {
      queueMicrotask(() => {
        if (!alive) return
        delivered.current = key
        setRun({ status: 'limited' })
        limitRef.current()
      })
      return () => { alive = false }
    }

    // The narrative is written at the reader's usual depth; other depths are
    // re-explanations of the same evidence and never repeat this run.
    const request = fetchAnalysis(ticker, fast, storedDepth())
    shareResearch(ticker, request as unknown as Promise<ResearchPayload>)
    queueMicrotask(() => { if (alive) setRun({ status: 'running', startedAt: Date.now() }) })

    request
      .then((raw) => {
        if (!alive) return
        delivered.current = key
        const analysis = normalizeAnalysis(raw)
        setRun({ status: 'ready', analysis, finishedAt: Date.now() })
        recordAnalysis(analysis)
        if (!isPro) bumpTodayCount()
      })
      .catch((e: unknown) => {
        if (!alive) return
        delivered.current = key
        setRun({
          status: 'error',
          message: e instanceof Error ? e.message : 'The research run did not complete.',
          code: e instanceof ApiError ? e.status : null,
        })
      })

    return () => { alive = false }
  }, [ticker, fast, resolved, isPro, attempt])

  return { run, retry: () => setAttempt((n) => n + 1) }
}

/** The company's name, from the symbol database (fast path). */
export function useIdentity(ticker: string): SecurityIdentity | null {
  const [identity, setIdentity] = useState<{ for: string; value: SecurityIdentity | null } | null>(null)
  useEffect(() => {
    let alive = true
    rememberSymbol(ticker)
    fetchIdentity(ticker)
      .then((value) => { if (alive) setIdentity({ for: ticker, value }) })
      .catch(() => { if (alive) setIdentity({ for: ticker, value: null }) })
    return () => { alive = false }
  }, [ticker])
  return identity?.for === ticker ? identity.value : null
}

export const RANGES = [
  { value: '1mo', label: '1M' },
  { value: '3mo', label: '3M' },
  { value: '6mo', label: '6M' },
  { value: '1y', label: '1Y' },
  { value: '5y', label: '5Y' },
] as const

export type Range = (typeof RANGES)[number]['value']

/** Daily closes for a window, with the reason when there are none. */
export function usePriceSeries(ticker: string, range: Range): {
  series: ChartSeries | null
  loading: boolean
  retry: () => void
} {
  const [state, setState] = useState<{ for: string; series: ChartSeries } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const want = `${ticker}:${range}:${attempt}`
  useEffect(() => {
    let alive = true
    fetchChart(ticker, range)
      .then((raw) => { if (alive) setState({ for: want, series: normalizeChartSeries(raw) }) })
      .catch(() => {
        if (!alive) return
        // A transport failure has no reason worth quoting; say what did not happen.
        setState({
          for: want,
          series: { points: [], status: 'error', reason: 'The chart service did not answer.', source: null },
        })
      })
    return () => { alive = false }
  }, [ticker, range, want])
  const current = state?.for === want ? state.series : null
  return { series: current, loading: current === null, retry: () => setAttempt((n) => n + 1) }
}
