/**
 * Single-name validation of the scoring engine.
 *
 * Migrated from the legacy validation view, which had the strongest diagnostics
 * in the old product and the weakest presentation. Three of them are not
 * available anywhere else:
 *
 * Calibration asks whether a score of 0.6 actually corresponds to a 60% outcome.
 * A model can rank well and be badly calibrated, and every threshold decision
 * made on its output is wrong in that case even though its IC looks fine.
 *
 * The confusion matrix asks what the verdicts actually did, which a hit rate
 * averages away — a model right about "up" and wrong about "down" has the same
 * hit rate as one that is mediocre at both.
 *
 * Population stability quantifies drift: whether the scores being produced now
 * come from the same distribution the model was validated on. A model can be
 * perfectly calibrated on a population it no longer sees.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import { BarRows, Histogram, Scatter, TimeSeries } from '@/components/system/charts'
import { Grid, Panel, Prose, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { recordVisit } from '@/lib/research/history'
import { ChartSkeleton, ObjectHeader, StripSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'

interface Backtest {
  ticker?: string
  scope_note?: string
  samples?: number
  period?: { start: string; end: string }
  ic?: number | null
  baseline_12_1_ic?: number | null
  rolling_ic?: Array<{ date: string; ic: number }>
  recent?: { rolling_ic_last: number | null; verdict_flips_last6: number }
  hit_rate?: number | null
  directional_samples?: number
  confusion_matrix?: Record<string, { up: number; down: number }>
  calibration?: Array<{ bin: string; expected: number; actual: number; n: number }>
  strategy?: Record<string, number | null>
  buy_hold?: Record<string, number | null>
  win_rate_invested_days?: number | null
  avg_holding_days?: number | null
  time_invested_pct?: number
  equity_curve?: Array<{ date: string; strategy: number; buy_hold: number }>
  monthly_strategy_returns?: Record<string, number>
  score_distribution?: Array<{ bin: string; count: number }>
  verdict_distribution?: Record<string, number>
  factor_diagnostics?: Record<string, { ic: number | null; sign_stability: number | null; samples: number }>
  prediction_drift_psi?: number | null
  psi_note?: string
  error?: string
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Population stability index, on the conventional reading. */
function psiState(psi: number | null): ResearchState {
  if (psi === null) return 'unknown'
  if (psi < 0.1) return 'recorded'
  if (psi < 0.25) return 'stale'
  return 'blocked'
}

function psiWord(psi: number | null): string {
  if (psi === null) return 'not measured'
  if (psi < 0.1) return 'no material shift'
  if (psi < 0.25) return 'moderate shift'
  return 'major shift'
}

export default function Calibration({ symbol }: { symbol: string }) {
  const [tagged, setTagged] = useState<{ id: string; data: Backtest } | null>(null)
  const [failure, setFailure] = useState<{ id: string; message: string } | null>(null)

  useEffect(() => {
    let alive = true
    recordVisit({ kind: 'security', id: symbol, label: symbol, detail: 'calibration' })
    const id = symbol
    fetch(`/api/backtest/${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Backtest) => { if (alive) setTagged({ id, data: d }) })
      .catch((e: Error) => { if (alive) setFailure({ id, message: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const data = tagged?.id === symbol ? tagged.data : null
  const error = failure?.id === symbol ? failure.message : null

  const rolling = useMemo(
    () => (data?.rolling_ic ?? []).map((p) => ({ x: p.date, y: p.ic })),
    [data],
  )

  const calibration = useMemo(() => data?.calibration ?? [], [data])
  const psi = n(data?.prediction_drift_psi)

  if (error) {
    return <Panel title="Validation" state="unavailable"><StateBlock state="unavailable" title={`No backtest for ${symbol}`} detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!data) {
    return (
      <>
        <StripSkeleton items={7} />
        <Panel title="Rolling information coefficient" state="waking"><ChartSkeleton height={190} /></Panel>
      </>
    )
  }
  if (data.error) {
    return <Panel title="Validation" state="unavailable"><StateBlock state="unavailable" title={`Validation refused for ${symbol}`} detail={data.error} /></Panel>
  }

  const confusion = data.confusion_matrix ?? {}
  const verdicts = Object.keys(confusion)

  return (
    <>
      <ObjectHeader
        glyph="C"
        name={symbol}
        kind="calibration of the scoring engine"
        state={psiState(psi)}
        detail={data.period ? `${data.period.start} → ${data.period.end}` : undefined}
        facts={[
          { label: 'Samples', value: n(data.samples), digits: 0 , kind: 'count'},
          { label: 'IC', value: n(data.ic), digits: 4, signed: true, tone: true , kind: 'ic'},
          { label: 'Baseline IC', value: n(data.baseline_12_1_ic), digits: 4, signed: true },
          { label: 'Hit rate', value: n(data.hit_rate), digits: 3 },
          { label: 'PSI', value: psi, digits: 3 },
        ]}
      />

      <Strip metrics={[
        { label: 'Samples', value: n(data.samples), digits: 0 , kind: 'count'},
        { label: 'IC', value: n(data.ic), digits: 4, signed: true, tone: true , kind: 'ic'},
        { label: 'Baseline 12-1 IC', value: n(data.baseline_12_1_ic), digits: 4, signed: true, title: 'The 1993 momentum baseline this must beat to be worth anything' },
        { label: 'Hit rate', value: n(data.hit_rate), digits: 3 },
        { label: 'Directional samples', value: n(data.directional_samples), digits: 0 },
        { label: 'Time invested', value: n(data.time_invested_pct), digits: 3 },
        { label: 'Verdict flips', value: n(data.recent?.verdict_flips_last6), digits: 0, title: 'Changes of direction in the last six observations' },
      ]} />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href={`/terminal/security?symbol=${encodeURIComponent(symbol)}`} className="sys-btn" style={{ textDecoration: 'none' }}>security</Link>
          <Link href={`/terminal/relationships?symbol=${encodeURIComponent(symbol)}`} className="sys-btn" style={{ textDecoration: 'none' }}>relationships</Link>
          <Link href="/terminal/evidence" className="sys-btn" style={{ textDecoration: 'none' }}>model evidence</Link>
          <Link href="/terminal/handbook" className="sys-btn" style={{ textDecoration: 'none' }}>handbook</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">{data.samples ? `${data.samples} samples` : ''}</span>
      </Toolbar>

      {data.scope_note ? (
        <Panel title="Scope" state="recorded">
          <Prose>
            {data.scope_note}
          </Prose>
          {data.period ? (
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)' }}>
              {data.period.start} → {data.period.end}
            </p>
          ) : null}
        </Panel>
      ) : null}

      {rolling.length > 2 ? (
        <Panel title="Rolling information coefficient" subtitle={symbol}>
          <TimeSeries
            series={[{ name: 'rolling IC', points: rolling, color: 'var(--ink)' }]}
            unit="rank correlation"
            zeroLine
            height={190}
          />
        </Panel>
      ) : null}

      <Grid>
        {calibration.length ? (
          <Panel title="Calibration" subtitle="does a score mean what it says">
            <Scatter
              points={calibration.map((c) => ({ x: c.expected, y: c.actual, label: `${c.bin} (n=${c.n})` }))}
              xLabel="expected" yLabel="actual"
              title=""
              height={190}
            />
            <table className="sys-table sys-table--compact" style={{ marginTop: 'var(--d-2)' }}>
              <thead><tr><th>Bin</th><th className="num">Expected</th><th className="num">Actual</th><th className="num">Gap</th><th className="num">n</th></tr></thead>
              <tbody>
                {calibration.map((c) => (
                  <tr key={c.bin}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{c.bin}</td>
                    <td className="num"><Value value={n(c.expected)} digits={3} /></td>
                    <td className="num"><Value value={n(c.actual)} digits={3} /></td>
                    <td className="num"><Value value={n(c.actual) !== null && n(c.expected) !== null ? c.actual - c.expected : null} digits={3} signed tone /></td>
                    <td className="num"><Value value={c.n} digits={0} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              A model can rank well and be badly calibrated. Where it is, every
              threshold decision taken on its output is wrong even though the IC
              looks fine — which is why this sits beside the IC rather than under it.
            </p>
          </Panel>
        ) : null}

        {verdicts.length ? (
          <Panel title="Confusion" subtitle="what the verdicts actually did">
            <div className="sys-scroll-x">
              <table className="sys-table sys-table--compact">
                <thead><tr><th>Verdict</th><th className="num">Went up</th><th className="num">Went down</th><th className="num">Accuracy</th></tr></thead>
                <tbody>
                  {verdicts.map((v) => {
                    const row = confusion[v]
                    const total = (row.up ?? 0) + (row.down ?? 0)
                    // "Correct" depends on the direction the verdict claimed.
                    const correct = v === 'long' ? row.up : v === 'short' ? row.down : null
                    return (
                      <tr key={v}>
                        <td><Status state={v === 'long' ? 'candidate' : v === 'short' ? 'blocked' : 'recorded'} label={v} /></td>
                        <td className="num"><Value value={row.up} digits={0} /></td>
                        <td className="num"><Value value={row.down} digits={0} /></td>
                        <td className="num">
                          <Value
                            value={correct !== null && total > 0 ? correct / total : null}
                            digits={3} tone
                            title={correct === null ? 'A flat verdict makes no directional claim, so it has no accuracy' : undefined}
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              A hit rate averages this away. A model right about one direction and
              wrong about the other scores the same as one that is mediocre at
              both, and only the split separates them. A flat verdict makes no
              directional claim, so it is given no accuracy rather than a zero.
            </p>
          </Panel>
        ) : null}

        <Panel title="Population stability" state={psiState(psi)}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--d-3)' }}>
            <span className="sys-title"><Value value={psi} digits={4} /></span>
            <Status state={psiState(psi)} label={psiWord(psi)} />
          </div>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '78ch' }}>
            {data.psi_note ?? 'Whether the scores being produced now come from the same distribution the engine was validated on.'}
          </p>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            Below 0.1 is conventionally read as no material shift, 0.1 to 0.25 as
            moderate, above 0.25 as major. A model can be perfectly calibrated on a
            population it no longer sees.
          </p>
        </Panel>

        {data.score_distribution?.length ? (
          <Panel title="Score distribution">
            <BarRows
              unit="observations"
              rows={data.score_distribution.map((b) => ({ label: b.bin, value: b.count }))}
            />
          </Panel>
        ) : null}
      </Grid>

      {data.equity_curve && data.equity_curve.length > 2 ? (
        <Panel title="Strategy against buy and hold" subtitle={symbol} state="experimental">
          <TimeSeries
            series={[
              { name: 'strategy', points: data.equity_curve.map((p) => ({ x: p.date, y: p.strategy })), color: 'var(--ink)' },
              { name: 'buy and hold', points: data.equity_curve.map((p) => ({ x: p.date, y: p.buy_hold })), color: 'var(--ink-faint)', dashed: true },
            ]}
            unit="cumulative"
            method="single name, before transaction costs"
            height={210}
          />
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', marginTop: 'var(--d-3)' }}>
            <Section title="Strategy">
              <table className="sys-table sys-table--compact">
                <tbody>
                  {Object.entries(data.strategy ?? {}).map(([k, v]) => (
                    <tr key={k}><td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td><td className="num"><Value value={n(v)} digits={4} signed tone /></td></tr>
                  ))}
                </tbody>
              </table>
            </Section>
            <Section title="Buy and hold">
              <table className="sys-table sys-table--compact">
                <tbody>
                  {Object.entries(data.buy_hold ?? {}).map(([k, v]) => (
                    <tr key={k}><td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td><td className="num"><Value value={n(v)} digits={4} signed /></td></tr>
                  ))}
                </tbody>
              </table>
            </Section>
          </div>
          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '86ch' }}>
            One name, before transaction costs, with{' '}
            {n(data.time_invested_pct) !== null ? `${((data.time_invested_pct as number) * 100).toFixed(0)}% of the period invested` : 'an unrecorded time in market'}.
            A single-name curve is a diagnostic of the scoring engine, not evidence
            of a strategy — that requires the costed cross-sectional apparatus in
            Evidence.
          </p>
        </Panel>
      ) : null}

      {data.factor_diagnostics && Object.keys(data.factor_diagnostics).length ? (
        <Panel title="Factor diagnostics" subtitle="per input, on this name" flush>
          <table className="sys-table sys-table--compact">
            <thead><tr><th>Factor</th><th className="num">IC</th><th className="num">Sign stability</th><th className="num">Samples</th></tr></thead>
            <tbody>
              {Object.entries(data.factor_diagnostics)
                .sort((a, b) => (n(b[1].ic) ?? -Infinity) - (n(a[1].ic) ?? -Infinity))
                .map(([f, d]) => (
                  <tr key={f}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{f}</td>
                    <td className="num"><Value value={n(d.ic)} digits={4} signed tone /></td>
                    <td className="num"><Value value={n(d.sign_stability)} digits={3} title="How often this factor kept the same sign" /></td>
                    <td className="num"><Value value={d.samples} digits={0} /></td>
                  </tr>
                ))}
            </tbody>
          </table>
        </Panel>
      ) : null}

      {data.monthly_strategy_returns && Object.keys(data.monthly_strategy_returns).length ? (
        <Panel title="Monthly returns">
          <Histogram
            values={Object.values(data.monthly_strategy_returns)}
            unit="monthly return"
            title=""
            marks={[{ at: 0, label: '0', color: 'var(--rule-focus)' }]}
          />
        </Panel>
      ) : null}
    </>
  )
}
