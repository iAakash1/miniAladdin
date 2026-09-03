'use client'

import Link from 'next/link'
import { useParams, useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

import Workbench from '@/components/system/Workbench'
import { useEntitlement, type EntitlementValue } from '@/components/system/Entitlement'
import { Panel } from '@/components/system'
import CompanyReport from '@/components/terminal/CompanyReport'
import EmptyState from '@/components/ui/EmptyState'
import ResearchLoader, { ANALYSIS_STAGES } from '@/components/ui/ResearchLoader'
import { fetchAnalysis, fetchChart, normalizeAnalysis, normalizeChart } from '@/lib/api'
import { recordAnalysis } from '@/lib/history'
import { FREE_DAILY_LIMIT, bumpTodayCount, readTodayCount } from '@/lib/usage'
import type { Analysis, PricePoint } from '@/lib/types'

const TICKER_RE = /^[A-Z.^-]{1,8}$/


/**
 * /company/{ticker} — the research report as a permanent URL. The URL is
 * the research request: visiting it runs the full deterministic pipeline
 * for that company and renders the complete report. Bookmark it, share it,
 * open it in a new tab — it always means the same thing.
 */
export default function CompanyPage() {
  return (
    <Workbench
      title="Company research"
      subtitle="a permanent URL for one security"
      context={
        <>
          <Panel title="What this URL means">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The URL is the research request. Visiting it runs the full
              deterministic pipeline for that company, so it always means the
              same thing — safe to bookmark, safe to share.
            </p>
          </Panel>
          <Panel title="Where the model record lives">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              This report is what the pipeline says about the security. How well
              the model has actually predicted it is a different question, and it
              is the Record tab on the Securities workspace.
            </p>
          </Panel>
        </>
      }
    >
      <CompanyLoader />
    </Workbench>
  )
}

function CompanyLoader() {
  const params = useParams<{ ticker: string }>()
  const ticker = decodeURIComponent(params.ticker ?? '').toUpperCase()
  const fast = useSearchParams().get('fast') === '1'
  const { resolved, isPro, requestUpgrade }: EntitlementValue = useEntitlement()

  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'ready'; analysis: Analysis; chart: PricePoint[] }
    | { status: 'limited' }
    | { status: 'error'; message: string }
  >({ status: 'loading' })
  const ranFor = useRef<string | null>(null)
  // Stages the pipeline has *confirmed* finished. Never guessed.
  const [done, setDone] = useState(0)

  // Ticker validity is derived from the URL, not fetched, so it is computed
  // during render rather than written into state by an effect. The effect
  // below now only owns genuinely asynchronous work.
  const invalid = !TICKER_RE.test(ticker)

  useEffect(() => {
    if (invalid) return
    // Wait for the session before reading entitlement.
    //
    // The old shell rendered nothing until identity resolved, so `isPro` was
    // never observed in its default state. This one does not block the page —
    // which is better — but it means an unresolved entitlement reads as false,
    // and starting the run here would charge a paying reader against the free
    // daily limit and show them an upgrade prompt they do not need.
    if (!resolved) return
    // One run per ticker per mount — period changes refetch only the chart.
    if (ranFor.current === ticker) return
    ranFor.current = ticker

    let cancelled = false
    let delivered = false

    // Both of the synchronous writes that used to sit here are gone. The
    // quota check is deferred to a microtask and the `loading` reset is
    // unnecessary: `ranFor` already guarantees this body runs once per
    // ticker, so state is still `loading` from its initial value.
    if (!isPro && readTodayCount() >= FREE_DAILY_LIMIT) {
      queueMicrotask(() => {
        if (cancelled) return
        delivered = true
        setState({ status: 'limited' })
        requestUpgrade('limit')
      })
      return () => { cancelled = true; release() }
    }

    // The chart resolves independently of the analysis, so its completion is
    // a *real* signal — the only one this pipeline exposes. It is used to
    // tick stage one and nothing else; the rest stay honest estimates.
    const chart = fetchChart(ticker, '3mo')
    chart.then(() => { if (!cancelled) setDone(1) }).catch(() => {})

    Promise.all([fetchAnalysis(ticker, fast), chart])
      .then(([rawResearch, rawChart]) => {
        if (cancelled) return
        delivered = true
        const analysis = normalizeAnalysis(rawResearch)
        setState({ status: 'ready', analysis, chart: normalizeChart(rawChart) })
        recordAnalysis(analysis)
        if (!isPro) bumpTodayCount()
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          delivered = true
          setState({
            status: 'error',
            message: e instanceof Error ? e.message : 'The analysis failed. Please try again.',
          })
        }
      })
    return () => {
      cancelled = true
      release()
    }

    /* Release the once-per-ticker guard when a run is torn down before it
     * delivered anything.
     *
     * Without this the page never loads in development. React StrictMode
     * mounts, unmounts and remounts: the first run claims the guard and
     * starts the fetch, the cleanup cancels it, and the second run sees the
     * guard already claimed and returns without fetching. The in-flight
     * response then arrives to a `cancelled` closure and is thrown away, so
     * the loader spins forever against a request that succeeded. Freeing the
     * ref on an undelivered teardown keeps the guard's intent — one fetch per
     * ticker — while letting a genuine remount try again. */
    function release() {
      if (!delivered && ranFor.current === ticker) ranFor.current = null
    }
  }, [ticker, fast, resolved, isPro, invalid, requestUpgrade])

  if (invalid) {
    return (
      <EmptyState
        title="That isn't a ticker symbol"
        description={`“${ticker}” doesn't look like a valid symbol. Ticker symbols are one to five letters — try AAPL, NVDA or MSFT.`}
        action={
          <Link href="/terminal/analyze" className="btn btn--primary btn--sm" style={{ textDecoration: 'none' }}>
            Search for a company
          </Link>
        }
      />
    )
  }

  if (state.status === 'loading') {
    return (
      <ResearchLoader
        title={resolved ? 'Researching' : 'Checking your session'}
        subject={ticker}
        stages={ANALYSIS_STAGES}
        completed={done}
        note={fast ? 'fast mode: sentiment and synthesis skipped' : undefined}
      />
    )
  }

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
