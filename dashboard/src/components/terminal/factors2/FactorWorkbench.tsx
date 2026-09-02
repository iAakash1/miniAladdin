/**
 * Factor workbench.
 *
 * Two columns here do work no factor page usually does.
 *
 * `overlap_inflation` shows how much the naive t-statistic overstated
 * significance before the Newey-West correction for label overlap. A factor
 * whose t falls from 4.1 to 1.8 once overlap is accounted for was never
 * significant, and showing only the corrected figure hides how close the naive
 * reading came to a false positive.
 *
 * Redundancy carries its pair coverage. Unobserved factor pairs enter the
 * eigenvalue calculation as zero correlation, which understates redundancy and
 * therefore overstates independence — the direction that flatters. Below 75%
 * coverage the independence verdict is withheld entirely, and that withholding
 * is shown rather than rendered as a confident number.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { Panel, Section, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { BarRows } from '@/components/system/charts'
import { recordVisit } from '@/lib/research/history'

interface FactorEvaluation {
  factor: string
  mean_ic: number
  std_ic: number
  t_stat: number
  naive_t_stat: number
  overlap_inflation: number
  newey_west_lags: number
  hit_rate: number
  dates: number
  names_median: number
  top_minus_bottom: number | null
  significant: boolean
  assessment: string
}

interface Redundancy {
  factors: string[]
  matrix: Array<Array<number | null>>
  effective_factors: number
  redundant_pairs: Array<{ a: string; b: string; correlation: number }>
  dates: number
  assessment: string
  measured_pairs?: number
  total_pairs?: number
  pair_coverage?: number | null
}

interface Lab {
  status?: 'ready' | 'error' | 'building'
  stage?: string
  progress_done?: number
  progress_total?: number
  elapsed_seconds?: number
  universe?: { name: string; symbols?: string[]; point_in_time_membership?: boolean }
  window?: { start: string; end: string; observation_dates: number; step_days: number; horizon_days: number }
  factors?: FactorEvaluation[]
  redundancy?: Redundancy | null
  caveats?: string[]
  degraded?: Array<{ estimator: string; reason: string }>
  build_seconds?: number
  cached?: boolean
  error?: string
}

export default function FactorWorkbench() {
  const [lab, setLab] = useState<Lab | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  // The endpoint answers with progress while a build runs, so this polls until
  // the payload settles. The loop lives entirely inside the effect: a
  // self-rescheduling callback held in a ref is the same behaviour with an
  // extra mutable handle that nothing else needs.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async () => {
      try {
        const response = await fetch('/api/factors?universe=mega30')
        if (!response.ok) throw new Error(String(response.status))
        const payload: Lab = await response.json()
        if (cancelled) return
        setLab(payload)
        if (payload.status !== 'ready' && payload.status !== 'error') {
          timer = setTimeout(tick, 2000)
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }

    void tick()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [])

  const factors = useMemo(() => lab?.factors ?? [], [lab])

  const columns: DataColumn<FactorEvaluation>[] = useMemo(() => [
    { key: 'f', header: 'Factor', width: '18%', sort: (f) => f.factor, text: (f) => f.factor, render: (f) => <span style={{ fontFamily: 'var(--font-mono)' }}>{f.factor}</span> },
    { key: 'ic', header: 'Mean IC', unit: 'rank corr.', numeric: true, sort: (f) => f.mean_ic, render: (f) => <Value value={f.mean_ic} digits={4} signed tone /> },
    { key: 't', header: 'IC t-stat', unit: 'Newey-West', numeric: true, sort: (f) => f.t_stat, render: (f) => <Value value={f.t_stat} digits={2} signed /> },
    { key: 'nt', header: 'Naive t', unit: 'uncorrected', numeric: true, sort: (f) => f.naive_t_stat, render: (f) => <Value value={f.naive_t_stat} digits={2} signed title="Before correcting for label overlap" /> },
    {
      key: 'inf', header: 'Overlap inflation', unit: '×', numeric: true, sort: (f) => f.overlap_inflation,
      render: (f) => <Value value={f.overlap_inflation} digits={2} tone title="How much the uncorrected t overstated significance" />,
    },
    { key: 'lags', header: 'Lags', numeric: true, sort: (f) => f.newey_west_lags, render: (f) => <Value value={f.newey_west_lags} digits={0} /> },
    { key: 'hr', header: 'Hit rate', numeric: true, sort: (f) => f.hit_rate, render: (f) => <Value value={f.hit_rate} digits={3} /> },
    { key: 'tmb', header: 'Top minus bottom', numeric: true, optional: true, sort: (f) => f.top_minus_bottom, render: (f) => <Value value={f.top_minus_bottom} digits={4} signed tone /> },
    { key: 'dates', header: 'Dates', numeric: true, optional: true, sort: (f) => f.dates, render: (f) => <Value value={f.dates} digits={0} /> },
    { key: 'sig', header: 'Significant', width: '11%', sort: (f) => (f.significant ? 1 : 0), render: (f) => <Status state={f.significant ? 'candidate' : 'blocked'} label={f.significant ? 'yes' : 'no'} /> },
  ], [])

  if (error) {
    return <Panel title="Factors" state="unavailable"><StateBlock state="unavailable" title="The factor lab could not be reached" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!lab) return <Panel title="Factors" state="waking"><StateBlock state="waking" title="Contacting the factor lab" /></Panel>

  if (lab.status === 'error') {
    return <Panel title="Factors" state="unavailable"><StateBlock state="unavailable" title="The build failed" detail={lab.error} /></Panel>
  }

  if (lab.status !== 'ready') {
    return (
      <Panel title="Factors" state="waking">
        <StateBlock
          state="waking"
          title={lab.stage ? `Building — ${lab.stage}` : 'Building'}
          detail={
            lab.progress_total
              ? `${lab.progress_done ?? 0} of ${lab.progress_total} steps, ${(lab.elapsed_seconds ?? 0).toFixed(0)}s elapsed. Nothing partial is shown while this runs.`
              : 'Nothing partial is shown while this runs.'
          }
        />
      </Panel>
    )
  }

  const r = lab.redundancy
  const coverageThin = r?.pair_coverage !== null && r?.pair_coverage !== undefined && r.pair_coverage < 0.75
  const sel = factors.find((f) => f.factor === selected)

  return (
    <>
      <Strip metrics={[
        { label: 'Factors', value: factors.length, digits: 0 },
        { label: 'Significant', value: factors.filter((f) => f.significant).length, digits: 0 },
        { label: 'Universe', value: lab.universe?.name ?? null, digits: 0 },
        { label: 'Observation dates', value: lab.window?.observation_dates ?? null, digits: 0 },
        { label: 'Horizon', value: lab.window?.horizon_days ?? null, digits: 0, unit: 'd' },
        { label: 'Step', value: lab.window?.step_days ?? null, digits: 0, unit: 'd' },
        { label: 'Build', value: lab.build_seconds ?? null, digits: 1, unit: 's' },
      ]} />

      {lab.degraded?.length ? (
        <Panel title="Partial results" state="stale">
          <p style={{ margin: '0 0 var(--d-2)', fontSize: 'var(--t-body)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            These estimators raised. What is shown below is real but incomplete.
          </p>
          <table className="sys-table sys-table--compact">
            <tbody>
              {lab.degraded.map((d) => (
                <tr key={d.estimator}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{d.estimator}</td>
                  <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{d.reason}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}

      <Panel title="Factor evaluations" subtitle={`${factors.length} factors`} flush>
        <DataTable
          columns={columns} rows={factors} rowKey={(f) => f.factor}
          density="compact" filterPlaceholder="filter factors"
          initialSort={{ key: 't', direction: 'desc' }}
          selectedKey={selected ?? undefined}
          onSelect={(f) => {
            setSelected(f.factor)
            recordVisit({ kind: 'factor', id: f.factor, label: f.factor, detail: f.significant ? 'significant' : 'not significant' })
          }}
        />
      </Panel>

      {sel ? (
        <Panel title="Factor" subtitle={sel.factor} state={sel.significant ? 'candidate' : 'blocked'}>
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.3fr)' }}>
            <Section title="Statistics">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Mean IC</td><td className="num"><Value value={sel.mean_ic} digits={4} signed tone /></td></tr>
                  <tr><td>IC dispersion</td><td className="num"><Value value={sel.std_ic} digits={4} /></td></tr>
                  <tr><td>Corrected t</td><td className="num"><Value value={sel.t_stat} digits={3} signed /></td></tr>
                  <tr><td>Naive t</td><td className="num"><Value value={sel.naive_t_stat} digits={3} signed /></td></tr>
                  <tr><td>Overlap inflation</td><td className="num"><Value value={sel.overlap_inflation} digits={3} unit="×" /></td></tr>
                  <tr><td>Newey-West lags</td><td className="num"><Value value={sel.newey_west_lags} digits={0} /></td></tr>
                  <tr><td>Observation dates</td><td className="num"><Value value={sel.dates} digits={0} /></td></tr>
                  <tr><td>Median names</td><td className="num"><Value value={sel.names_median} digits={0} /></td></tr>
                  <tr><td>Top minus bottom</td><td className="num"><Value value={sel.top_minus_bottom} digits={4} signed tone /></td></tr>
                </tbody>
              </table>
            </Section>
            <Section title="Reading it">
              <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                {sel.assessment}
              </p>
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                The uncorrected t-statistic was {sel.naive_t_stat.toFixed(2)}; correcting
                for {sel.newey_west_lags} lags of label overlap brings it to {sel.t_stat.toFixed(2)},
                an inflation factor of {sel.overlap_inflation.toFixed(2)}×. Overlapping
                labels share information, and a t-statistic that ignores that counts
                the same evidence more than once.
              </p>
            </Section>
          </div>
        </Panel>
      ) : null}

      <Panel title="Overlap inflation across factors" subtitle="uncorrected t over corrected t">
        <BarRows
          unit="×"
          rows={[...factors]
            .sort((a, b) => b.overlap_inflation - a.overlap_inflation)
            .map((f) => ({
              label: f.factor,
              value: f.overlap_inflation,
              note: `naive ${f.naive_t_stat.toFixed(2)} → corrected ${f.t_stat.toFixed(2)} at ${f.newey_west_lags} lags`,
            }))}
        />
        <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '86ch' }}>
          Every factor here is measured on the same overlapping label, so a large
          inflation is not a property of the factor — it is the correction the
          uncorrected statistic never applied. Reading a naive t on any of these
          would overstate significance by this multiple.
        </p>
      </Panel>

      <Panel
        title="Redundancy"
        subtitle={r ? `${r.factors.length} factors` : undefined}
        state={coverageThin ? 'unavailable' : 'recorded'}
      >
        {r ? (
          <>
            <Strip metrics={[
              { label: 'Effective factors', value: r.effective_factors, digits: 2, title: 'Counting positions overstates breadth whenever factors move together' },
              { label: 'Nominal factors', value: r.factors.length, digits: 0 },
              { label: 'Pairs observed', value: r.measured_pairs ?? null, digits: 0 },
              { label: 'Pairs total', value: r.total_pairs ?? null, digits: 0 },
              { label: 'Pair coverage', value: r.pair_coverage ?? null, digits: 3, title: 'Unobserved pairs enter as zero correlation, which overstates independence' },
              { label: 'Redundant pairs', value: r.redundant_pairs.length, digits: 0 },
            ]} />
            <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink)' }}>
              {r.assessment}
            </p>
            {coverageThin ? (
              <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '84ch' }}>
                Coverage is below the threshold at which an independence claim can be
                supported. A pair that was never observed together enters the
                eigenvalue calculation as zero correlation, which understates
                redundancy and therefore overstates independence — so no verdict is
                given rather than one computed mostly from the fill.
              </p>
            ) : null}
            {r.redundant_pairs.length ? (
              <table className="sys-table sys-table--compact" style={{ marginTop: 'var(--d-3)' }}>
                <thead><tr><th>Factor</th><th>Factor</th><th className="num">Correlation</th></tr></thead>
                <tbody>
                  {r.redundant_pairs.map((p) => (
                    <tr key={`${p.a}-${p.b}`}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{p.a}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{p.b}</td>
                      <td className="num"><Value value={p.correlation} digits={3} signed tone /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </>
        ) : <StateBlock state="unavailable" title="No redundancy analysis was produced" />}
      </Panel>

      {lab.caveats?.length ? (
        <Panel title="Caveats">
          <ul style={{ margin: 0, paddingLeft: 'var(--d-4)', fontSize: 'var(--t-body)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            {lab.caveats.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </Panel>
      ) : null}
    </>
  )
}
