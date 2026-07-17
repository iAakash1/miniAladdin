'use client'

import dynamicImport from 'next/dynamic'
import { useEffect, useMemo, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import Section from '@/components/ui/Section'
import MetricExplainer from './MetricExplainer'
import { METRIC_GLOSSARY } from '@/lib/metricGlossary'
import { failureModes, overallHealth } from '@/lib/validationInsights'
import { FACTOR_LABELS } from '@/lib/history'

const EquityCurveChart = dynamicImport(
  () => import('./ValidationCharts').then((m) => ({ default: m.EquityCurveChart })),
  { ssr: false, loading: () => <Skeleton height={240} /> },
)
const RollingIcChart = dynamicImport(
  () => import('./ValidationCharts').then((m) => ({ default: m.RollingIcChart })),
  { ssr: false, loading: () => <Skeleton height={240} /> },
)

export interface BacktestData {
  ticker: string
  scope_note: string
  samples: number
  period: { start: string; end: string }
  ic: number | null
  baseline_12_1_ic: number | null
  baseline_12_1_strategy: Record<string, number | null> | null
  rolling_ic: Array<{ date: string; ic: number }>
  recent: { rolling_ic_last: number | null; verdict_flips_last6: number }
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
  factor_diagnostics: Record<string, { ic: number | null; sign_stability: number | null; samples: number }>
  factor_correlations: Record<string, number>
  prediction_drift_psi: number | null
  psi_note: string
  error?: string
}

const HEALTH_BADGE = { pos: 'badge--pos', warn: 'badge--warn', neg: 'badge--neg' } as const

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

function fmt(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits)
}

function fmtSigned(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function toneFor(value: number | null | undefined, goodAbove: number, badBelow: number): 'pos' | 'neg' | 'neutral' {
  if (value === null || value === undefined) return 'neutral'
  if (value > goodAbove) return 'pos'
  if (value < badBelow) return 'neg'
  return 'neutral'
}

export default function ValidationView() {
  const [ticker, setTicker] = useState('SPY')
  const [query, setQuery] = useState('SPY')
  const [data, setData] = useState<BacktestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

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
  }, [query, reloadKey])

  const maxScoreCount = data ? Math.max(1, ...data.score_distribution.map((row) => row.count)) : 1

  const health = useMemo(
    () => data && !data.error
      ? overallHealth({ ic: data.ic, hitRate: data.hit_rate, sharpe: data.strategy.sharpe, samples: data.samples })
      : null,
    [data],
  )
  const flags = useMemo(
    () => data && !data.error
      ? failureModes({
          psi: data.prediction_drift_psi,
          factorDiagnostics: data.factor_diagnostics,
          confusionMatrix: data.confusion_matrix,
          scoreDistribution: data.score_distribution,
        })
      : [],
    [data],
  )
  const sortedFactors = useMemo(
    () => data
      ? Object.entries(data.factor_diagnostics).sort(([, a], [, b]) => Math.abs(b.ic ?? 0) - Math.abs(a.ic ?? 0))
      : [],
    [data],
  )
  const sortedCorrelations = useMemo(
    () => data
      ? Object.entries(data.factor_correlations).sort(([, a], [, b]) => Math.abs(b) - Math.abs(a)).slice(0, 10)
      : [],
    [data],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h2 className="h-panel" style={{ fontSize: '1rem', marginBottom: 6 }}>Model validation</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', maxWidth: '78ch', lineHeight: 1.6 }}>
          Walk-forward evaluation of the scoring engine on real price history — the question this
          page answers is simple: can this model be trusted, and under what conditions.
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
          style={{ maxWidth: 160, letterSpacing: '0.06em' }}
          maxLength={8}
          value={ticker}
          onChange={(event) => setTicker(event.target.value.toUpperCase().replace(/[^A-Z.^-]/g, ''))}
        />
        <button type="submit" className="btn btn--primary" disabled={loading}>
          {loading ? 'Computing…' : 'Run validation'}
        </button>
      </form>

      {failed && (
        <EmptyState
          title={`We couldn't run the validation for ${query}`}
          description="The backtest service didn't respond — it may be waking from idle, which takes a few seconds. Your ticker and settings are unchanged."
          action={
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => setReloadKey((key) => key + 1)}
            >
              Try again
            </button>
          }
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

      {!loading && !failed && data && !data.error && health && (
        <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Overall Model Health — the lead answer, always visible */}
          <section aria-label="Overall model health" className="panel" style={{ padding: '18px 20px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <h3 className="h-panel">Overall model health</h3>
              <span className={`badge ${HEALTH_BADGE[health.tone]}`}>{health.label}</span>
              <span className="num" style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--faint)' }}>
                {data.samples} samples · {data.period.start} → {data.period.end}
              </span>
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 5 }}>
              {health.reasons.map((reason) => (
                <li key={reason} style={{ fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--muted)' }}>{reason}</li>
              ))}
            </ul>
            <p style={{ fontSize: '0.75rem', color: 'var(--warn)', lineHeight: 1.6, marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--line)' }}>
              {data.scope_note}
            </p>
          </section>

          {/* Prediction Quality */}
          <Section id="val-prediction-quality" title="Prediction quality" defaultOpen>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 48px)', marginBottom: 16 }}>
              <MetricExplainer entry={METRIC_GLOSSARY.ic} value={fmt(data.ic)} valueTone={toneFor(data.ic, 0.05, 0)} />
              <div>
                <span className="label" style={{ fontSize: '0.625rem' }}>Naive 12-1 baseline IC</span>
                <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600, color: 'var(--muted)' }}>
                  {fmt(data.baseline_12_1_ic)}
                </p>
                <p style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>Sign of 12-1 return, no engine — the bar the engine should clear.</p>
              </div>
              <MetricExplainer
                entry={METRIC_GLOSSARY.rollingIc}
                value={fmt(data.recent.rolling_ic_last)}
                valueTone={toneFor(data.recent.rolling_ic_last, 0.05, 0)}
              />
            </div>
            <RollingIcChart data={data} />
          </Section>

          {/* Historical Performance */}
          <Section id="val-historical-performance" title="Historical performance" defaultOpen>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(18px, 3.5vw, 44px)', marginBottom: 16 }}>
              <MetricExplainer entry={METRIC_GLOSSARY.annualReturn} value={`${fmt(data.strategy.return, 1)}%`} valueTone={toneFor((data.strategy.return ?? 0) - (data.buy_hold.return ?? 0), 0, 0)} />
              <MetricExplainer entry={METRIC_GLOSSARY.volatility} value={`${fmt(data.strategy.volatility, 1)}%`} />
              <MetricExplainer entry={METRIC_GLOSSARY.sharpe} value={fmt(data.strategy.sharpe, 2)} valueTone={toneFor(data.strategy.sharpe, 1.0, 0)} />
              <MetricExplainer entry={METRIC_GLOSSARY.sortino} value={fmt(data.strategy.sortino, 2)} valueTone={toneFor(data.strategy.sortino, 1.5, 0)} />
              <MetricExplainer entry={METRIC_GLOSSARY.calmar} value={fmt(data.strategy.calmar, 2)} valueTone={toneFor(data.strategy.calmar, 1.0, 0.5)} />
              <MetricExplainer entry={METRIC_GLOSSARY.maxDrawdown} value={`${fmt(data.strategy.max_drawdown, 1)}%`} valueTone={toneFor(data.strategy.max_drawdown, -15, -40)} />
              <MetricExplainer entry={METRIC_GLOSSARY.winRate} value={`${fmt(data.win_rate_invested_days, 1)}%`} valueTone={toneFor(data.win_rate_invested_days, 50, 48)} />
              <Metric label="Avg holding" value={data.avg_holding_days} suffix="d" />
              <Metric label="Time invested" value={data.time_invested_pct} suffix="%" />
            </div>

            <div style={{ overflowX: 'auto', marginBottom: 16 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">vs.</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Return</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Sharpe</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Max drawdown</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontWeight: 550 }}>Engine signal</td>
                  <td className="num" style={{ textAlign: 'right' }}>{fmtSigned(data.strategy.return, 1)}%</td>
                  <td className="num" style={{ textAlign: 'right' }}>{fmt(data.strategy.sharpe, 2)}</td>
                  <td className="num" style={{ textAlign: 'right' }}>{fmt(data.strategy.max_drawdown, 1)}%</td>
                </tr>
                <tr>
                  <td style={{ color: 'var(--muted)' }}>Buy &amp; hold</td>
                  <td className="num" style={{ textAlign: 'right', color: 'var(--muted)' }}>{fmtSigned(data.buy_hold.return, 1)}%</td>
                  <td className="num" style={{ textAlign: 'right', color: 'var(--muted)' }}>{fmt(data.buy_hold.sharpe, 2)}</td>
                  <td className="num" style={{ textAlign: 'right', color: 'var(--muted)' }}>{fmt(data.buy_hold.max_drawdown, 1)}%</td>
                </tr>
                {data.baseline_12_1_strategy && (
                  <tr>
                    <td style={{ color: 'var(--muted)' }}>Naive 12-1 baseline</td>
                    <td className="num" style={{ textAlign: 'right', color: 'var(--muted)' }}>{fmtSigned(data.baseline_12_1_strategy.return, 1)}%</td>
                    <td className="num" style={{ textAlign: 'right', color: 'var(--muted)' }}>{fmt(data.baseline_12_1_strategy.sharpe, 2)}</td>
                    <td className="num" style={{ textAlign: 'right', color: 'var(--muted)' }}>{fmt(data.baseline_12_1_strategy.max_drawdown, 1)}%</td>
                  </tr>
                )}
              </tbody>
            </table>
            </div>

            <EquityCurveChart data={data} />

            <div style={{ marginTop: 16 }}>
              <p className="label" style={{ fontSize: '0.625rem', marginBottom: 10 }}>Monthly strategy returns</p>
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
            </div>
          </Section>

          {/* Reliability */}
          <Section id="val-reliability" title="Reliability">
            <div style={{ marginBottom: 16 }}>
              <MetricExplainer
                entry={METRIC_GLOSSARY.hitRate}
                value={`${fmt(data.hit_rate, 1)}%`}
                valueTone={toneFor((data.hit_rate ?? 0) - 50, 5, -2)}
              />
              <p style={{ fontSize: '0.75rem', color: 'var(--faint)', marginTop: 6 }}>
                {data.directional_samples} directional calls (Holds excluded).
              </p>
            </div>
            <div style={{ marginBottom: 12 }}>
              <MetricExplainer entry={METRIC_GLOSSARY.confusionMatrix} />
            </div>
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
          </Section>

          {/* Calibration */}
          <Section id="val-calibration" title="Calibration">
            <div style={{ marginBottom: 12 }}>
              <MetricExplainer entry={METRIC_GLOSSARY.calibration} value="" />
            </div>
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
          </Section>

          {/* Risk */}
          <Section id="val-risk" title="Risk">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 48px)', marginBottom: 14 }}>
              <MetricExplainer entry={METRIC_GLOSSARY.maxDrawdown} value={`${fmt(data.strategy.max_drawdown, 1)}%`} valueTone={toneFor(data.strategy.max_drawdown, -15, -40)} />
              <MetricExplainer entry={METRIC_GLOSSARY.volatility} value={`${fmt(data.strategy.volatility, 1)}%`} />
            </div>
            {data.strategy.calmar !== null && (
              <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
                Calmar of {fmt(data.strategy.calmar, 2)}: the {fmtSigned(data.strategy.return, 1)}% annualized return came
                against a worst drawdown of {fmt(data.strategy.max_drawdown, 1)}% — the number an investor would have had
                to sit through at the low point.
              </p>
            )}
          </Section>

          {/* Stability */}
          <Section id="val-stability" title="Stability">
            <div style={{ marginBottom: 18 }}>
              <MetricExplainer
                entry={METRIC_GLOSSARY.psi}
                value={fmt(data.prediction_drift_psi, 3)}
                valueTone={toneFor(0.25 - (data.prediction_drift_psi ?? 0), 0.15, 0)}
              />
              <p style={{ fontSize: '0.75rem', color: 'var(--faint)', marginTop: 6 }}>{data.psi_note}</p>
            </div>

            <div style={{ marginBottom: 18 }}>
              <MetricExplainer entry={METRIC_GLOSSARY.factorStability} value="" />
              {sortedFactors.length === 0 ? (
                <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginTop: 8 }}>Not enough per-factor history yet.</p>
              ) : (
                <div style={{ overflowX: 'auto', marginTop: 10 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Factor</th>
                      <th scope="col" style={{ textAlign: 'right' }}>IC</th>
                      <th scope="col" style={{ textAlign: 'right' }}>Sign stability</th>
                      <th scope="col" style={{ textAlign: 'right' }}>Samples</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedFactors.map(([name, diag]) => (
                      <tr key={name}>
                        <td>{FACTOR_LABELS[name] ?? name}</td>
                        <td className="num" style={{ textAlign: 'right' }}>{fmtSigned(diag.ic, 3)}</td>
                        <td className="num" style={{ textAlign: 'right', color: diag.sign_stability !== null && diag.sign_stability < 0.5 ? 'var(--neg)' : undefined }}>
                          {fmt(diag.sign_stability, 2)}
                        </td>
                        <td className="num" style={{ textAlign: 'right', color: 'var(--faint)' }}>{diag.samples}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </div>

            <div>
              <MetricExplainer entry={METRIC_GLOSSARY.factorCorrelation} value="" />
              {sortedCorrelations.length === 0 ? (
                <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginTop: 8 }}>Not enough overlapping factor history yet.</p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                  {sortedCorrelations.map(([pair, rho]) => {
                    const [a, b] = pair.split('~')
                    return (
                      <span
                        key={pair}
                        className="num"
                        style={{
                          fontSize: '0.75rem', padding: '4px 9px', borderRadius: 'var(--r-sm)',
                          background: Math.abs(rho) > 0.8 ? 'var(--neg-wash)' : 'var(--surface-2)',
                          color: Math.abs(rho) > 0.8 ? 'var(--neg)' : 'var(--muted)',
                        }}
                      >
                        {FACTOR_LABELS[a] ?? a} ~ {FACTOR_LABELS[b] ?? b}: {fmtSigned(rho, 2)}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          </Section>

          {/* Failure Modes */}
          <Section id="val-failure-modes" title="Failure modes" summary={flags.length > 0 ? `${flags.length} flagged` : 'none flagged'}>
            {flags.length === 0 ? (
              <p style={{ fontSize: '0.8125rem', color: 'var(--pos)', lineHeight: 1.6 }}>
                No known failure mode is flagged for this ticker over the tested window.
              </p>
            ) : (
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {flags.map((flag) => (
                  <li key={flag} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--text)' }}>
                    <span aria-hidden="true" style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: 'var(--neg)' }} />
                    {flag}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {/* Limitations */}
          <Section id="val-limitations" title="Limitations" defaultOpen>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text)', lineHeight: 1.65, maxWidth: '80ch' }}>
              {data.scope_note}
            </p>
            <ul style={{ listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                'This validates one ticker at a time — it is not a portfolio-level backtest and says nothing about diversification effects.',
                'The long/flat strategy test assumes no transaction costs, slippage, taxes or borrow fees.',
                'Signals recompute weekly on an expanding window; the live product may re-score more frequently on new data intraday.',
              ].map((item) => (
                <li key={item} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--muted)' }}>
                  <span aria-hidden="true" style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: 'var(--faint)' }} />
                  {item}
                </li>
              ))}
            </ul>
          </Section>

          {/* Current Confidence */}
          <Section id="val-current-confidence" title="Current confidence" defaultOpen>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 48px)' }}>
              <div>
                <span className="label" style={{ fontSize: '0.625rem' }}>Most recent rolling IC</span>
                <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600, color: toneFor(data.recent.rolling_ic_last, 0.05, 0) === 'pos' ? 'var(--pos)' : toneFor(data.recent.rolling_ic_last, 0.05, 0) === 'neg' ? 'var(--neg)' : undefined }}>
                  {fmt(data.recent.rolling_ic_last)}
                </p>
                <p style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
                  vs. {fmt(data.ic)} over the full window
                  {data.recent.rolling_ic_last !== null && data.ic !== null && data.recent.rolling_ic_last < data.ic - 0.03
                    ? ' — recent skill is running below the historical average.'
                    : ' — consistent with the historical average.'}
                </p>
              </div>
              <div>
                <span className="label" style={{ fontSize: '0.625rem' }}>Verdict flips, last 6 signals</span>
                <p className="num" style={{ fontSize: '1.0625rem', fontWeight: 600, color: data.recent.verdict_flips_last6 >= 3 ? 'var(--warn)' : undefined }}>
                  {data.recent.verdict_flips_last6}
                </p>
                <p style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
                  {data.recent.verdict_flips_last6 >= 3
                    ? 'The verdict has been unusually unstable recently — treat the current read with extra caution.'
                    : 'A stable recent verdict history — the current call is not the product of rapid flip-flopping.'}
                </p>
              </div>
            </div>
          </Section>

          {/* Score distribution */}
          <Section id="val-score-distribution" title="Score distribution">
            <MetricExplainer entry={METRIC_GLOSSARY.scoreDistribution} value="" />
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 90, marginTop: 12 }}>
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
          </Section>
        </div>
      )}
    </div>
  )
}
