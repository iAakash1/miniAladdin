/**
 * One factor in full: its IC through time, its stability, and the portfolio a
 * quantile spread on it would have produced.
 *
 * The stability panel is the reason this exists separately from the factor
 * table. A mean IC is a single number over a whole history, and two factors
 * with the same mean can be entirely different objects: one that worked
 * throughout, and one that worked in the first half and stopped. `first_half`
 * against `second_half`, sign flips and the best and worst windows are what
 * separate them, and a table of means cannot.
 *
 * The portfolio panel is labelled carefully. It is a quantile spread on one
 * factor, not the research book, and its Sharpe is not the evidence any
 * promotion rests on.
 */
'use client'

import { useMemo } from 'react'

import { TimeSeries } from '@/components/system/charts'
import { Panel, Prose, Section, StateBlock, Status, Strip, Value } from '@/components/system'

export interface Portfolio {
  buckets: number
  rebalances: number
  total_return: number
  annualised_return: number
  annualised_volatility: number
  sharpe: number
  max_drawdown: number
  hit_rate: number
  turnover: number
  long_leg_return: number
  short_leg_return: number
  benchmark_return: number
  beat_benchmark: boolean
  assessment: string
  equity_curve: Array<{ date: string; strategy: number; benchmark: number }>
}

export interface Stability {
  window: number
  rolling: Array<{ date: string; ic: number }>
  first_half_ic: number | null
  second_half_ic: number | null
  best_window: { start: string; end: string; mean_ic: number } | null
  worst_window: { start: string; end: string; mean_ic: number } | null
  concentration: number
  sign_flips: number
  decayed: boolean
  assessment: string
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

export default function FactorDetail({
  factor, icSeries, stability, portfolio, saturation, quantiles,
}: {
  factor: string
  icSeries?: Array<[string, number]> | null
  stability?: Stability | null
  portfolio?: Portfolio | null
  saturation?: number | null
  quantiles?: number | null
}) {
  const ic = useMemo(
    () => (icSeries ?? []).map(([date, value]) => ({ x: date, y: value })),
    [icSeries],
  )

  const rolling = useMemo(
    () => (stability?.rolling ?? []).map((p) => ({ x: p.date, y: p.ic })),
    [stability],
  )

  const halves = stability && stability.first_half_ic !== null && stability.second_half_ic !== null
    ? { first: stability.first_half_ic, second: stability.second_half_ic }
    : null

  return (
    <>
      {ic.length > 2 || rolling.length > 2 ? (
        <Panel title="Information coefficient" subtitle={factor}>
          <TimeSeries
            series={[
              ...(ic.length > 2 ? [{ name: 'IC', points: ic, color: 'var(--ink-faint)' }] : []),
              ...(rolling.length > 2
                ? [{ name: `${stability?.window ?? ''}-period rolling`, points: rolling, color: 'var(--ink)' }]
                : []),
            ]}
            unit="rank correlation per date"
            method="Spearman IC between the factor score and the forward rank"
            zeroLine
            height={210}
          />
        </Panel>
      ) : null}

      {stability ? (
        <Panel
          title="Stability"
          subtitle={stability.decayed ? 'decayed' : 'no decay detected'}
          state={stability.decayed ? 'blocked' : 'recorded'}
        >
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)' }}>
            <Section title="Through time">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>First half IC</td><td className="num"><Value value={n(stability.first_half_ic)} digits={4} signed tone /></td></tr>
                  <tr><td>Second half IC</td><td className="num"><Value value={n(stability.second_half_ic)} digits={4} signed tone /></td></tr>
                  <tr>
                    <td>Decayed</td>
                    <td className="num"><Status state={stability.decayed ? 'blocked' : 'recorded'} label={String(stability.decayed)} /></td>
                  </tr>
                  <tr><td>Sign flips</td><td className="num"><Value value={n(stability.sign_flips)} digits={0} title="How often the rolling IC changed sign" /></td></tr>
                  <tr>
                    <td>Concentration</td>
                    <td className="num"><Value value={n(stability.concentration)} digits={4} title="How much of the total IC came from a small number of periods" /></td>
                  </tr>
                  <tr><td>Best window</td><td className="num" style={{ textAlign: 'left', fontSize: 'var(--t-micro)' }}>{stability.best_window ? `${stability.best_window.start} → ${stability.best_window.end}` : '—'}</td></tr>
                  <tr><td>Worst window</td><td className="num" style={{ textAlign: 'left', fontSize: 'var(--t-micro)' }}>{stability.worst_window ? `${stability.worst_window.start} → ${stability.worst_window.end}` : '—'}</td></tr>
                </tbody>
              </table>
            </Section>
            <Section title="Why halves matter more than the mean">
              <Prose>
                {halves
                  ? `First half ${halves.first.toFixed(4)}, second half ${halves.second.toFixed(4)}. `
                  : ''}
                Two factors with the same mean IC can be entirely different objects:
                one that worked throughout, and one that worked early and stopped.
                A mean over the whole history cannot separate them, which is why the
                halves, the sign flips and the concentration are reported beside it.
              </Prose>
              <Prose size="tight">
                {stability.assessment}
              </Prose>
            </Section>
          </div>
        </Panel>
      ) : null}

      {portfolio ? (
        <Panel
          title="Quantile spread"
          subtitle={`${portfolio.buckets} buckets · ${portfolio.rebalances} rebalances`}
          state="experimental"
        >
          <Strip metrics={[
            { label: 'Annualised return', value: n(portfolio.annualised_return), digits: 4, signed: true, tone: true },
            { label: 'Annualised volatility', value: n(portfolio.annualised_volatility), digits: 4 },
            { label: 'Sharpe', value: n(portfolio.sharpe), digits: 3, signed: true, tone: true , kind: 'sharpe'},
            { label: 'Max drawdown', value: n(portfolio.max_drawdown), digits: 4, tone: true , kind: 'drawdown'},
            { label: 'Hit rate', value: n(portfolio.hit_rate), digits: 3 },
            { label: 'Turnover', value: n(portfolio.turnover), digits: 3 , kind: 'multiple'},
          ]} />

          {portfolio.equity_curve?.length > 2 ? (
            <div style={{ marginTop: 'var(--d-3)' }}>
              <TimeSeries
                series={[
                  { name: 'spread', points: portfolio.equity_curve.map((p) => ({ x: p.date, y: p.strategy })), color: 'var(--ink)' },
                  { name: 'benchmark', points: portfolio.equity_curve.map((p) => ({ x: p.date, y: p.benchmark })), color: 'var(--ink-faint)', dashed: true },
                ]}
                unit="cumulative"
                method="top bucket minus bottom bucket, rebalanced at each date"
                height={200}
              />
            </div>
          ) : null}

          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)', marginTop: 'var(--d-3)' }}>
            <Section title="Legs">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Long leg</td><td className="num"><Value value={n(portfolio.long_leg_return)} digits={4} signed tone /></td></tr>
                  <tr><td>Short leg</td><td className="num"><Value value={n(portfolio.short_leg_return)} digits={4} signed tone /></td></tr>
                  <tr><td>Benchmark</td><td className="num"><Value value={n(portfolio.benchmark_return)} digits={4} signed /></td></tr>
                  <tr><td>Beat benchmark</td><td className="num"><Status state={portfolio.beat_benchmark ? 'candidate' : 'blocked'} label={String(portfolio.beat_benchmark)} /></td></tr>
                  <tr><td>Total return</td><td className="num"><Value value={n(portfolio.total_return)} digits={4} signed tone /></td></tr>
                </tbody>
              </table>
            </Section>
            <Section title="What this is not">
              <Prose>
                {portfolio.assessment}
              </Prose>
              <Prose size="tight">
                This is a quantile spread on one factor, not the research book. Its
                Sharpe is a diagnostic of the factor and is not the evidence any
                promotion rests on — that comes from the costed apparatus in
                Evidence, measured against the cumulative trial count.
              </Prose>
            </Section>
          </div>
        </Panel>
      ) : null}

      {saturation !== null && saturation !== undefined ? (
        <Panel title="Saturation">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--d-3)' }}>
            <span className="sys-title"><Value value={n(saturation)} digits={3} /></span>
            <span className="sys-meta">{quantiles ? `${quantiles} quantiles` : ''}</span>
          </div>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
            How much of the factor&apos;s range is occupied by ties and clustered
            values. A saturated factor separates fewer names than its quantile
            count implies, so the top bucket is not the top of a smooth
            distribution — it is whatever fell on one side of a crowd.
          </p>
        </Panel>
      ) : null}

      {!icSeries?.length && !stability && !portfolio ? (
        <Panel title="Factor detail">
          <StateBlock
            state="unavailable"
            title={`No series recorded for ${factor}`}
            detail="The build returned no IC series, stability analysis or quantile spread for this factor."
          />
        </Panel>
      ) : null}
    </>
  )
}
