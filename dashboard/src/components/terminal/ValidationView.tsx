'use client'

import dynamicImport from 'next/dynamic'
import { useEffect, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'

const ValidationCharts = dynamicImport(() => import('./ValidationCharts'), {
  ssr: false,
  loading: () => <Skeleton height={300} />,
})

export interface BacktestData {
  ticker: string
  scope_note: string
  samples: number
  period: { start: string; end: string }
  ic: number | null
  rolling_ic: Array<{ date: string; ic: number }>
  hit_rate: number | null
  directional_samples: number
  confusion_matrix: Record<'long' | 'flat' | 'short', { up: number; down: number }>
  calibration: Array<{ bin: string; expected: number; actual: number; n: number }>
  strategy: Record<string, number | null>
  buy_hold: Record<string, number | null>
  win_rate_invested_days: number | null
  avg_holding_days: number | null
  time_invested_pct: number
  equity_curve: Array<{ date: string; strategy: number; buy_hold: number }>
  monthly_strategy_returns: Record<string, number>
  score_distribution: Array<{ bin: string; count: number }>
  verdict_distribution: Record<string, number>
  error?: string
}

function Metric({ label, value, suffix = '' }: { label: string; value: number | null | undefined; suffix?: string }) {
  return (
    <div>
      <span className="label" style={{ fontSize: '0.625rem' }}>{label}</span>
      <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600 }}>
        {value === null || value === undefined ? '—' : `${value}${suffix}`}
      </p>
    </div>
  )
}

export default function ValidationView() {
  const [ticker, setTicker] = useState('SPY')
  const [query, setQuery] = useState('SPY')
  const [data, setData] = useState<BacktestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let alive = true
    queueMicrotask(() => {
      if (alive) {
        setLoading(true)
        setFailed(false)
      }
    })
    fetch(`/api/backtest/${encodeURIComponent(query)}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((json: BacktestData) => {
        if (alive) setData(json)
      })
      .catch((error: unknown) => {
        if (alive && (error as Error).name !== 'AbortError') setFailed(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [query])

  const maxScoreCount = data ? Math.max(1, ...data.score_distribution.map((row) => row.count)) : 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h2 className="h-panel" style={{ fontSize: '1rem', marginBottom: 6 }}>Model validation</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', maxWidth: '78ch', lineHeight: 1.6 }}>
          Walk-forward evaluation of the scoring engine on real price history — signals
          recompute weekly on an expanding window, measured against 21-day forward returns.
          No look-ahead, no simulation.
        </p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (ticker.trim()) setQuery(ticker.trim().toUpperCase())
        }}
        style={{ display: 'flex', gap: 8 }}
      >
        <label htmlFor="bt-ticker" className="visually-hidden">Ticker to validate</label>
        <input
          id="bt-ticker"
          className="input mono"
          style={{ maxWidth: 160, height: 38, letterSpacing: '0.06em' }}
          maxLength={8}
          value={ticker}
          onChange={(event) => setTicker(event.target.value.toUpperCase().replace(/[^A-Z.^-]/g, ''))}
        />
        <button type="submit" className="btn btn--primary btn--sm" style={{ height: 38 }} disabled={loading}>
          {loading ? 'Computing…' : 'Run validation'}
        </button>
      </form>

      {failed && (
        <EmptyState
          title="Validation service unreachable"
          description="Try again shortly."
          action={<button type="button" className="btn btn--secondary btn--sm" onClick={() => setQuery(`${query}`)}>Retry</button>}
        />
      )}

      {loading && !failed && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} aria-busy="true">
          <Skeleton height={90} />
          <Skeleton height={300} />
          <Skeleton height={220} />
        </div>
      )}

      {!loading && !failed && data?.error && (
        <EmptyState title={`Cannot validate ${data.ticker}`} description={data.error} />
      )}

      {!loading && !failed && data && !data.error && (
        <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--warn)', lineHeight: 1.6, maxWidth: '86ch' }}>
            {data.scope_note}
          </p>

          {/* Headline metrics */}
          <section aria-label="Headline metrics" className="panel" style={{ padding: '16px 20px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(18px, 3.5vw, 44px)' }}>
              <Metric label={`IC (Spearman, n=${data.samples})`} value={data.ic} />
              <Metric label={`Hit rate (${data.directional_samples} calls)`} value={data.hit_rate} suffix="%" />
              <Metric label="Strategy Sharpe" value={data.strategy.sharpe} />
              <Metric label="Sortino" value={data.strategy.sortino} />
              <Metric label="Calmar" value={data.strategy.calmar} />
              <Metric label="Max drawdown" value={data.strategy.max_drawdown} suffix="%" />
              <Metric label="Ann. volatility" value={data.strategy.volatility} suffix="%" />
              <Metric label="Ann. return" value={data.strategy.return} suffix="%" />
              <Metric label="Win rate (invested days)" value={data.win_rate_invested_days} suffix="%" />
              <Metric label="Avg holding" value={data.avg_holding_days} suffix="d" />
              <Metric label="Time invested" value={data.time_invested_pct} suffix="%" />
            </div>
            <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 12, lineHeight: 1.6 }}>
              IC = rank correlation between signal score and 21-day forward return (0 = no signal;
              sustained |IC| above ~0.05 is meaningful for a single name). Hit rate counts only
              non-Hold calls. Strategy = long when score ≥ +0.15, flat otherwise, daily returns, no costs —
              buy &amp; hold over the same window returned {data.buy_hold.return ?? '—'}% ann.
              ({data.period.start} → {data.period.end}).
            </p>
          </section>

          {/* Charts: equity + rolling IC */}
          <ValidationCharts data={data} />

          {/* Reliability diagram */}
          <section aria-label="Confidence calibration" className="panel" style={{ padding: '16px 20px' }}>
            <h3 className="h-panel" style={{ marginBottom: 4 }}>Confidence calibration</h3>
            <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 14, lineHeight: 1.6 }}>
              Reliability diagram: within each confidence bucket, the bar shows the realized hit
              rate. A calibrated model tracks the expected marker — bars far below their marker
              mean overconfidence.
            </p>
            {data.calibration.length === 0 ? (
              <p style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
                Not enough non-Hold calls per confidence bucket to measure calibration on this ticker.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {data.calibration.map((row) => (
                  <div key={row.bin} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span className="num" style={{ width: 58, fontSize: '0.75rem', color: 'var(--muted)' }}>{row.bin}%</span>
                    <div style={{ position: 'relative', flex: 1, height: 10, background: 'var(--surface-2)', borderRadius: 3 }}>
                      <span style={{
                        position: 'absolute', left: 0, top: 0, bottom: 0,
                        width: `${row.actual}%`, background: 'var(--accent)', borderRadius: 3, opacity: 0.75,
                      }} />
                      <span
                        title={`expected ~${row.expected}%`}
                        style={{
                          position: 'absolute', left: `${row.expected}%`, top: -3, bottom: -3,
                          width: 2, background: 'var(--text)',
                        }}
                      />
                    </div>
                    <span className="num" style={{ width: 92, fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'right' }}>
                      {row.actual}% (n={row.n})
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Confusion matrix + distributions */}
          <div className="terminal-grid-main">
            <section aria-label="Confusion matrix" className="panel" style={{ padding: '16px 20px' }}>
              <h3 className="h-panel" style={{ marginBottom: 4 }}>Confusion matrix</h3>
              <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 12 }}>
                Signal direction vs. realized 21-day direction. Off-diagonal mass = wrong-way calls.
              </p>
              <table className="data-table">
                <thead>
                  <tr><th scope="col">Signal</th><th scope="col" style={{ textAlign: 'right' }}>Realized ▲</th><th scope="col" style={{ textAlign: 'right' }}>Realized ▼</th></tr>
                </thead>
                <tbody>
                  {(['long', 'flat', 'short'] as const).map((row) => (
                    <tr key={row}>
                      <td style={{ fontWeight: 550 }}>{row}</td>
                      <td className="num" style={{ textAlign: 'right', color: row === 'long' ? 'var(--pos)' : undefined }}>
                        {data.confusion_matrix[row].up}
                      </td>
                      <td className="num" style={{ textAlign: 'right', color: row === 'short' ? 'var(--pos)' : undefined }}>
                        {data.confusion_matrix[row].down}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section aria-label="Distributions" className="panel" style={{ padding: '16px 20px' }}>
              <h3 className="h-panel" style={{ marginBottom: 4 }}>Score distribution</h3>
              <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 12 }}>
                Composite scores across all walk-forward samples — most days should sit near zero
                (Hold); fat action tails would mean an overactive model.
              </p>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 90 }}>
                {data.score_distribution.map((bucket) => (
                  <div key={bucket.bin} title={`${bucket.bin}: ${bucket.count}`}
                       style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
                    <div style={{
                      height: `${(bucket.count / maxScoreCount) * 100}%`,
                      background: bucket.bin.startsWith('-') ? 'var(--neg)' : 'var(--pos)',
                      opacity: 0.65, borderRadius: '2px 2px 0 0', minHeight: bucket.count > 0 ? 2 : 0,
                    }} />
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
                <span className="num" style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>−0.6</span>
                <span className="num" style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>0</span>
                <span className="num" style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>+0.6</span>
              </div>
              <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--muted)', marginTop: 10 }}>
                Verdicts: {Object.entries(data.verdict_distribution).map(([verdict, count]) => `${verdict} ${count}`).join(' · ')}
              </p>
            </section>
          </div>

          {/* Monthly table */}
          <section aria-label="Monthly strategy returns" className="panel" style={{ padding: '16px 20px' }}>
            <h3 className="h-panel" style={{ marginBottom: 4 }}>Monthly strategy returns</h3>
            <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 12 }}>
              Long/flat signal-following, by calendar month. Flat months show 0.00 — the model was out.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {Object.entries(data.monthly_strategy_returns).map(([month, value]) => (
                <span key={month} className="num" style={{
                  fontSize: '0.6875rem', padding: '3px 8px', borderRadius: 'var(--r-sm)',
                  background: value > 0 ? 'var(--pos-wash)' : value < 0 ? 'var(--neg-wash)' : 'var(--surface-2)',
                  color: value > 0 ? 'var(--pos)' : value < 0 ? 'var(--neg)' : 'var(--faint)',
                }}>
                  {month} {value > 0 ? '+' : ''}{value}%
                </span>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
