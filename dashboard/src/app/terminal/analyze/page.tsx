'use client'

import dynamicImport from 'next/dynamic'
import { useCallback, useEffect, useState } from 'react'

import AiPanel from '@/components/terminal/AiPanel'
import CommandBar from '@/components/terminal/CommandBar'
import CompanyBand from '@/components/terminal/CompanyBand'
import QuantPanel from '@/components/terminal/QuantPanel'
import VerdictTimeline from '@/components/terminal/VerdictTimeline'
import { recordAnalysis } from '@/lib/history'
import Fundamentals from '@/components/terminal/Fundamentals'
import Headlines from '@/components/terminal/Headlines'
import KeyStats from '@/components/terminal/KeyStats'
import MacroPanel from '@/components/terminal/MacroPanel'
import SentimentPanel from '@/components/terminal/SentimentPanel'
import TechnicalIntelligence from '@/components/terminal/TechnicalIntelligence'
import TerminalShell, { type TerminalShellContext } from '@/components/terminal/TerminalShell'
import Skeleton from '@/components/ui/Skeleton'
import EmptyState from '@/components/ui/EmptyState'
import { LogoMark } from '@/components/ui/Logo'

import { fetchAnalysis, fetchChart, fetchMacroClient, normalizeAnalysis, normalizeChart } from '@/lib/api'
import { fmtNum, fmtPctRaw } from '@/lib/format'
import { FREE_DAILY_LIMIT, bumpTodayCount, readTodayCount } from '@/lib/usage'
import type { Analysis, Macro, PricePoint } from '@/lib/types'

/* Recharts stays out of the initial bundle. */
const PriceChart = dynamicImport(() => import('@/components/terminal/PriceChart'), {
  ssr: false,
  loading: () => <Skeleton height={260} />,
})

const PERIODS: Array<{ value: string; label: string }> = [
  { value: '1mo', label: '1M' },
  { value: '3mo', label: '3M' },
  { value: '6mo', label: '6M' },
  { value: '1y', label: '1Y' },
  { value: '5y', label: '5Y' },
]

type Status = 'idle' | 'loading' | 'ready' | 'error'

function ResultSkeleton() {
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

export default function TerminalPage() {
  return (
    <TerminalShell loadingLabel="Loading terminal…">
      {(shell) => <AnalyzeView shell={shell} />}
    </TerminalShell>
  )
}

function AnalyzeView({ shell }: { shell: TerminalShellContext }) {
  const { isPro, usedToday, requestUpgrade } = shell

  const [status, setStatus] = useState<Status>('idle')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [chart, setChart] = useState<PricePoint[]>([])
  const [chartLoading, setChartLoading] = useState(false)
  const [error, setError] = useState('')
  const [macro, setMacro] = useState<Macro | null>(null)
  const [fast, setFast] = useState(false)
  const [period, setPeriod] = useState('3mo')

  useEffect(() => {
    let cancelled = false
    fetchMacroClient().then((m) => {
      if (!cancelled && m) setMacro(m)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const run = useCallback(
    async (symbol: string, forPeriod = period) => {
      const ticker = symbol.trim().toUpperCase()
      if (!ticker) return

      if (!isPro && readTodayCount() >= FREE_DAILY_LIMIT) {
        requestUpgrade('limit')
        return
      }

      setStatus('loading')
      setError('')
      try {
        const [rawResearch, rawChart] = await Promise.all([
          fetchAnalysis(ticker, fast),
          fetchChart(ticker, forPeriod),
        ])
        const normalized = normalizeAnalysis(rawResearch)
        setAnalysis(normalized)
        setChart(normalizeChart(rawChart))
        setStatus('ready')
        recordAnalysis(normalized) // verdict history (Phase 3)
        if (!isPro) bumpTodayCount()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'The analysis failed. Please try again.')
        setStatus('error')
      }
    },
    [fast, isPro, period, requestUpgrade],
  )

  /* Deep link: /terminal/analyze?ticker=NVDA (portfolio rows link here). */
  useEffect(() => {
    const symbol = new URLSearchParams(window.location.search).get('ticker')
    if (symbol && /^[A-Z.^-]{1,8}$/.test(symbol.toUpperCase())) {
      // Microtask: state updates stay out of the synchronous effect body.
      queueMicrotask(() => run(symbol.toUpperCase()))
    }
    // Run once on mount only — `run` identity changes with settings.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* Changing timeframe refetches only the chart — the verdict doesn't change with the window. */
  const changePeriod = useCallback(
    async (next: string) => {
      if (!isPro && next !== '3mo') {
        requestUpgrade('feature')
        return
      }
      setPeriod(next)
      if (!analysis) return
      setChartLoading(true)
      try {
        setChart(normalizeChart(await fetchChart(analysis.ticker, next)))
      } finally {
        setChartLoading(false)
      }
    },
    [analysis, isPro, requestUpgrade],
  )

  return (
    <>
        {/* Command area */}
        <section aria-label="Run an analysis" style={{ marginBottom: 24 }}>
          <CommandBar loading={status === 'loading'} fast={fast} onFastChange={setFast} onAnalyze={run} />
        </section>

        {/* Free-limit note, quiet */}
        {!isPro && usedToday > 0 && usedToday < FREE_DAILY_LIMIT && (
          <p style={{ fontSize: '0.75rem', color: 'var(--faint)', margin: '-12px 0 20px' }}>
            {FREE_DAILY_LIMIT - usedToday} of {FREE_DAILY_LIMIT} free analyses left today.
          </p>
        )}

        <div aria-live="polite">
          {status === 'idle' && (
            <div>
              <EmptyState
                icon={<LogoMark size={36} />}
                title="Analyze any US-listed equity"
                description="Type a ticker or pick one above. A full analysis reads price history, fundamentals, news sentiment and the macro regime — about ten seconds."
              />
              {macro && (
                <section
                  aria-label="Current macro conditions"
                  className="terminal-grid-four"
                  style={{ maxWidth: 880, margin: '0 auto' }}
                >
                  {[
                    {
                      label: 'Risk multiplier',
                      value: fmtNum(macro.srm, 2),
                      warn: macro.srm > 1.2,
                      note: macro.srm > 1.2 ? 'elevated regime' : 'normal regime',
                    },
                    {
                      label: '10Y–2Y spread',
                      value: `${fmtNum(macro.yieldSpread, 2)}%`,
                      warn: macro.inverted,
                      note: macro.inverted ? 'inverted curve' : 'positive slope',
                    },
                    {
                      label: 'CPI inflation',
                      value: fmtPctRaw(macro.cpi),
                      warn: macro.cpi > 4,
                      note: 'year over year',
                    },
                    {
                      label: 'Fed funds rate',
                      value: fmtPctRaw(macro.fedRate),
                      warn: false,
                      note: 'effective rate',
                    },
                  ].map((s) => (
                    <div key={s.label} className="panel" style={{ padding: '16px 18px' }}>
                      <p className="label" style={{ marginBottom: 8 }}>
                        {s.label}
                      </p>
                      <p
                        className="num"
                        style={{
                          fontSize: '1.25rem',
                          fontWeight: 600,
                          color: s.warn ? 'var(--warn)' : 'var(--text)',
                          marginBottom: 3,
                        }}
                      >
                        {s.value}
                      </p>
                      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>{s.note}</p>
                    </div>
                  ))}
                </section>
              )}
            </div>
          )}

          {status === 'loading' && <ResultSkeleton />}

          {status === 'error' && (
            <div className="panel" style={{ padding: '28px 30px', borderColor: 'color-mix(in srgb, var(--neg) 35%, transparent)' }}>
              <p className="h-panel" style={{ marginBottom: 8 }}>
                The analysis didn&apos;t complete
              </p>
              <p style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: 18, lineHeight: 1.6 }}>
                {error}
              </p>
              <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
                Check the ticker symbol, or try again — upstream data sources occasionally rate-limit.
              </p>
            </div>
          )}

          {status === 'ready' && analysis && (
            <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <CompanyBand analysis={analysis} />

              <AiPanel analysis={analysis} />

              <QuantPanel analysis={analysis} />

              <div className="terminal-grid-main">
                <section aria-label="Price history" className="panel" style={{ padding: '20px 22px' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 12,
                      flexWrap: 'wrap',
                      marginBottom: 12,
                    }}
                  >
                    <h3 className="h-panel">Price</h3>
                    <div className="seg" role="group" aria-label="Chart timeframe">
                      {PERIODS.map((p) => (
                        <button
                          key={p.value}
                          type="button"
                          className="seg__btn num"
                          aria-pressed={period === p.value}
                          onClick={() => changePeriod(p.value)}
                          style={{ fontSize: '0.75rem' }}
                        >
                          {p.label}
                          {!isPro && p.value !== '3mo' && (
                            <span aria-label="Pro feature" style={{ fontSize: '0.625rem', color: 'var(--warn)' }}>
                              PRO
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>

                  {chartLoading ? (
                    <Skeleton height={260} />
                  ) : chart.length > 0 ? (
                    <PriceChart
                      data={chart}
                      ticker={analysis.ticker}
                      periodLabel={PERIODS.find((p) => p.value === period)?.label ?? period}
                    />
                  ) : (
                    <EmptyState title="No price history" description="The chart service returned no data for this window." />
                  )}
                </section>

                <KeyStats analysis={analysis} />
              </div>

              <TechnicalIntelligence block={analysis.technicalIntelligence} />

              <div className="terminal-grid-three">
                <Fundamentals analysis={analysis} />
                <MacroPanel macro={analysis.macro} />
                <SentimentPanel analysis={analysis} />
              </div>

              <Headlines
                headlines={analysis.headlines}
                isPro={isPro}
                onUpgrade={() => requestUpgrade('feature')}
              />

              <VerdictTimeline ticker={analysis.ticker} />

              <p style={{ fontSize: '0.75rem', color: 'var(--faint)', textAlign: 'center', padding: '8px 0' }}>
                Research and education only — not investment advice.
              </p>
            </div>
          )}
        </div>
    </>
  )
}
