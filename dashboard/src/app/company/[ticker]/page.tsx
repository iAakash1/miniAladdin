'use client'

import Link from 'next/link'
import { useParams, useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

import CompanyReport from '@/components/terminal/CompanyReport'
import TerminalShell, { type TerminalShellContext } from '@/components/terminal/TerminalShell'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { fetchAnalysis, fetchChart, normalizeAnalysis, normalizeChart } from '@/lib/api'
import { recordAnalysis } from '@/lib/history'
import { FREE_DAILY_LIMIT, bumpTodayCount, readTodayCount } from '@/lib/usage'
import type { Analysis, PricePoint } from '@/lib/types'

const TICKER_RE = /^[A-Z.^-]{1,8}$/

function ReportSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} aria-hidden="true">
      <Skeleton height={148} />
      <div className="terminal-grid-main">
        <Skeleton height={330} />
        <Skeleton height={330} />
      </div>
      <div className="terminal-grid-three">
        <Skeleton height={260} />
        <Skeleton height={260} />
        <Skeleton height={260} />
      </div>
    </div>
  )
}

/**
 * /company/{ticker} — the research report as a permanent URL. The URL is
 * the research request: visiting it runs the full deterministic pipeline
 * for that company and renders the complete report. Bookmark it, share it,
 * open it in a new tab — it always means the same thing.
 */
export default function CompanyPage() {
  return (
    <TerminalShell loadingLabel="Loading research…">
      {(shell) => <CompanyLoader shell={shell} />}
    </TerminalShell>
  )
}

function CompanyLoader({ shell }: { shell: TerminalShellContext }) {
  const params = useParams<{ ticker: string }>()
  const ticker = decodeURIComponent(params.ticker ?? '').toUpperCase()
  const fast = useSearchParams().get('fast') === '1'
  const { isPro, requestUpgrade } = shell

  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'ready'; analysis: Analysis; chart: PricePoint[] }
    | { status: 'limited' }
    | { status: 'error'; message: string }
  >({ status: 'loading' })
  const ranFor = useRef<string | null>(null)

  useEffect(() => {
    if (!TICKER_RE.test(ticker)) {
      setState({ status: 'error', message: `“${ticker}” is not a valid ticker symbol.` })
      return
    }
    // One run per ticker per mount — period changes refetch only the chart.
    if (ranFor.current === ticker) return
    ranFor.current = ticker

    if (!isPro && readTodayCount() >= FREE_DAILY_LIMIT) {
      setState({ status: 'limited' })
      requestUpgrade('limit')
      return
    }

    let cancelled = false
    setState({ status: 'loading' })
    Promise.all([fetchAnalysis(ticker, fast), fetchChart(ticker, '3mo')])
      .then(([rawResearch, rawChart]) => {
        if (cancelled) return
        const analysis = normalizeAnalysis(rawResearch)
        setState({ status: 'ready', analysis, chart: normalizeChart(rawChart) })
        recordAnalysis(analysis)
        if (!isPro) bumpTodayCount()
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setState({
            status: 'error',
            message: e instanceof Error ? e.message : 'The analysis failed. Please try again.',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [ticker, fast, isPro, requestUpgrade])

  if (state.status === 'loading') return <ReportSkeleton />

  if (state.status === 'limited') {
    return (
      <EmptyState
        title="Today's free analyses are used up"
        description={`The free tier includes ${FREE_DAILY_LIMIT} full analyses a day. Upgrade for unlimited research, or come back tomorrow — your Vault keeps everything you've already run.`}
        action={
          <span style={{ display: 'inline-flex', gap: 10 }}>
            <button type="button" className="btn btn--accent btn--sm" onClick={() => requestUpgrade('limit')}>
              Upgrade
            </button>
            <Link href="/terminal/vault" className="btn btn--secondary btn--sm" style={{ textDecoration: 'none' }}>
              Open Vault
            </Link>
          </span>
        }
      />
    )
  }

  if (state.status === 'error') {
    return (
      <div className="panel" style={{ padding: '28px 30px', borderColor: 'color-mix(in srgb, var(--neg) 35%, transparent)' }}>
        <p className="h-panel" style={{ marginBottom: 8 }}>The analysis didn&apos;t complete</p>
        <p style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: 18, lineHeight: 1.6 }}>
          {state.message}
        </p>
        <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
          Check the ticker symbol, or try again — upstream data sources occasionally rate-limit.
        </p>
      </div>
    )
  }

  return (
    <CompanyReport
      analysis={state.analysis}
      initialChart={state.chart}
      isPro={isPro}
      requestUpgrade={requestUpgrade}
    />
  )
}
