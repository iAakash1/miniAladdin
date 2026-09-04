/**
 * Signal diagnostics: IC through time, fold by fold, with its geometry.
 *
 * Three things here that a plain IC number cannot say.
 *
 * The label geometry is stated first, because everything downstream depends on
 * it. A 21-session label sampled every 5 sessions overlaps four deep, which
 * sets the bootstrap block, the purge, and the Newey-West lag count — and a
 * confidence interval computed without it is too narrow in the flattering
 * direction.
 *
 * The pooled interval is drawn against zero, since whether it excludes zero is
 * the claim being made, not the point estimate.
 *
 * Fold-level IC is shown as its own series rather than averaged away. A mean IC
 * of 0.03 from eight folds that alternate sign is a different object from the
 * same mean earned consistently, and the average cannot tell them apart.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { BarRows, Histogram, TimeSeries } from '@/components/system/charts'
import { Grid, Panel, Prose, Section, StateBlock, Status, Strip, Value } from '@/components/system'
import { ChartSkeleton, StripSkeleton } from '@/components/system/composition'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { readResource } from '@/lib/resource'

interface Fold {
  fold: number
  mean_ic: number | null
  median_ic: number | null
  std_ic: number | null
  dates: number
  positive_rate: number | null
  start: string
  end: string
  observations: number
}

interface Pooled {
  point: number | null
  lower: number | null
  upper: number | null
  samples?: number
  block?: number
  confidence?: number
  excludes_zero?: boolean | null
  method?: string
  why_blocked?: string | null
  observations?: number
}

interface Geometry {
  target?: string
  horizon_sessions?: number
  step_sessions?: number
  overlapping_sessions?: number
  overlap_fraction?: number
  block_length?: number
  purge_sessions?: number
  embargo_sessions?: number
  why?: string
  observations?: number
}

interface Payload {
  status?: string
  model_id?: string
  target?: string
  folds?: Fold[]
  pooled_ic?: Pooled
  label_geometry?: Geometry
  ic_by_date?: { date: string; ic: number }[]
  note?: string
  detail?: string
}

export default function SignalDiagnostics({ experiment, model }: { experiment: string; model: string }) {
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [smooth, setSmooth] = useState(true)

  useEffect(() => {
    let alive = true
    readResource<Payload>(`/api/quant/experiments/${encodeURIComponent(experiment)}/series/${encodeURIComponent(model)}?view=folds`, 'artifact')
      .then((d) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [experiment, model])

  const ic = useMemo(() => data?.ic_by_date ?? [], [data])

  /** Trailing mean over one block length: the shortest window that does not
   *  average across observations sharing the same label window. */
  const smoothed = useMemo(() => {
    const block = data?.label_geometry?.block_length ?? 5
    if (!smooth || ic.length < block) return null
    return ic.map((p, i) => {
      if (i + 1 < block) return { x: p.date, y: null }
      const slice = ic.slice(i + 1 - block, i + 1)
      return { x: p.date, y: slice.reduce((s, v) => s + v.ic, 0) / block }
    })
  }, [ic, smooth, data])

  const foldColumns: DataColumn<Fold>[] = [
    { key: 'fold', header: 'Fold', numeric: true, sort: (f) => f.fold, render: (f) => <Value value={f.fold} kind="count" /> },
    { key: 'window', header: 'Window', width: '22%', sort: (f) => f.start, text: (f) => `${f.start} ${f.end}`, render: (f) => <span className="sys-meta sys-meta--strong">{f.start} → {f.end}</span> },
    { key: 'ic', header: 'Mean IC', unit: 'rank corr.', numeric: true, sort: (f) => f.mean_ic, render: (f) => <Value measure="mean_ic" kind="ic" value={f.mean_ic} digits={4} signed tone /> },
    { key: 'med', header: 'Median IC', unit: 'rank corr.', numeric: true, sort: (f) => f.median_ic, render: (f) => <Value measure="mean_ic" kind="ic" value={f.median_ic} digits={4} signed /> },
    { key: 'std', header: 'IC dispersion', unit: 'std of IC', numeric: true, sort: (f) => f.std_ic, render: (f) => <Value value={f.std_ic} digits={4} /> },
    { key: 'pos', header: 'Positive rate', unit: 'share', numeric: true, sort: (f) => f.positive_rate, render: (f) => <Value value={f.positive_rate} digits={3} /> },
    { key: 'dates', header: 'Dates', numeric: true, sort: (f) => f.dates, render: (f) => <Value value={f.dates} kind="count" /> },
    { key: 'obs', header: 'Observations', numeric: true, optional: true, sort: (f) => f.observations, render: (f) => <Value value={f.observations} kind="count" /> },
  ]

  if (error) return <Panel title="Diagnostics" state="unavailable"><StateBlock state="unavailable" title="The fold series could not be read" detail={error} /></Panel>
  if (!data) {
    return (
      <>
        <StripSkeleton items={7} />
        <Panel title="Information coefficient through time" state="waking"><ChartSkeleton height={230} /></Panel>
      </>
    )
  }
  if (data.status !== 'ok' || !data.folds?.length) {
    return <Panel title="Diagnostics" state="unavailable"><StateBlock state="unavailable" title="No fold results are recorded" detail={data.detail ?? data.note} /></Panel>
  }

  const g: Geometry = data.label_geometry ?? {}
  const p: Pooled = data.pooled_ic ?? { point: null, lower: null, upper: null }
  const folds = data.folds
  const signFlips = folds.filter((f, i) => i > 0 && f.mean_ic !== null && folds[i - 1].mean_ic !== null
    && Math.sign(f.mean_ic) !== Math.sign(folds[i - 1].mean_ic!)).length

  return (
    <>
      <Panel title="Label geometry" subtitle={g.target} state="recorded">
        <Strip metrics={[
          { label: 'Horizon', value: g.horizon_sessions ?? null, digits: 0, unit: 'sess' , kind: 'sessions'},
          { label: 'Step', value: g.step_sessions ?? null, digits: 0, unit: 'sess' , kind: 'sessions'},
          { label: 'Overlap', value: g.overlapping_sessions ?? null, digits: 0, kind: 'count', unit: 'sess' },
          { label: 'Overlap fraction', value: g.overlap_fraction ?? null, digits: 3 },
          { label: 'Bootstrap block', value: g.block_length ?? null, digits: 0, kind: 'count', title: 'Consecutive observations resampled together, because they share label windows' },
          { label: 'Purge', value: g.purge_sessions ?? null, digits: 0, kind: 'count', unit: 'sess' },
          { label: 'Embargo', value: g.embargo_sessions ?? null, digits: 0, kind: 'count', unit: 'sess' },
        ]} />
        {g.why ? (
          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            {g.why}
          </p>
        ) : null}
      </Panel>

      <Panel
        title="Pooled information coefficient"
        state={p.excludes_zero ? 'candidate' : 'blocked'}
      >
        <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.2fr)' }}>
          <Section title="Interval">
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>Point estimate</td><td className="num"><Value value={p.point ?? null} digits={5} signed tone /></td></tr>
                <tr><td>Lower</td><td className="num"><Value value={p.lower ?? null} digits={5} signed /></td></tr>
                <tr><td>Upper</td><td className="num"><Value value={p.upper ?? null} digits={5} signed /></td></tr>
                <tr><td>Confidence</td><td className="num"><Value value={p.confidence ?? null} digits={2} /></td></tr>
                <tr><td>Block length</td><td className="num"><Value value={p.block ?? null} kind="count" /></td></tr>
                <tr><td>Resamples</td><td className="num"><Value value={p.samples ?? null} kind="count" /></td></tr>
                <tr>
                  <td>Excludes zero</td>
                  <td className="num">
                    {p.excludes_zero === null || p.excludes_zero === undefined
                      ? <span className="sys-null">—</span>
                      : <Status state={p.excludes_zero ? 'candidate' : 'blocked'} label={String(p.excludes_zero)} />}
                  </td>
                </tr>
              </tbody>
            </table>
          </Section>
          <Section title="What the interval means">
            <Prose>
              Whether it excludes zero is the claim, not the point estimate. The
              resample is blocked at {p.block ?? '—'} consecutive observations
              because that many share a label window; resampling one at a time
              would treat dependent observations as independent and return an
              interval too narrow in the flattering direction.
            </Prose>
            {p.why_blocked ? (
              <Prose size="tight">{p.why_blocked}</Prose>
            ) : null}
          </Section>
        </div>
      </Panel>

      <Panel
        title="Information coefficient through time"
        subtitle={`${ic.length} dated observations`}
        actions={
          <button className="sys-btn" aria-pressed={smooth} onClick={() => setSmooth((v) => !v)}>
            block mean
          </button>
        }
      >
        <TimeSeries
          series={[
            { name: 'IC', points: ic.map((r) => ({ x: r.date, y: r.ic })), color: 'var(--ink-faint)' },
            ...(smoothed ? [{ name: `${g.block_length ?? 5}-block mean`, points: smoothed, color: 'var(--ink)' }] : []),
          ]}
          unit="rank correlation per date"
          method="Spearman IC between prediction and forward rank"
          zeroLine
          height={230}
        />
        <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '86ch' }}>
          The smoothing window is one block length, the shortest average that does
          not mix observations sharing a label window.
        </p>
      </Panel>

      <Grid>
        <Panel title="IC distribution">
          <Histogram
            values={ic.map((r) => r.ic)}
            unit="rank correlation"
            title=""
            marks={[
              { at: 0, label: '0', color: 'var(--rule-focus)' },
              ...(p.point !== null && p.point !== undefined ? [{ at: p.point, label: 'mean', color: 'var(--e-pos)' }] : []),
            ]}
          />
        </Panel>

        <Panel title="Fold by fold" subtitle={signFlips ? `${signFlips} sign changes between adjacent folds` : 'no sign changes'}>
          <BarRows
            unit="mean IC per fold"
            rows={folds.map((f) => ({
              label: `fold ${f.fold}`,
              value: f.mean_ic,
              note: `${f.start} → ${f.end}, ${f.dates} dates`,
            }))}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            A mean IC earned consistently and one earned by folds that alternate
            sign are different objects, and the average cannot tell them apart.
          </p>
        </Panel>
      </Grid>

      <Panel title="Folds" subtitle={`${folds.length} expanding windows`} flush>
        <DataTable
          columns={foldColumns} rows={folds} rowKey={(f) => String(f.fold)}
          density="compact" filterPlaceholder="filter folds"
          initialSort={{ key: 'fold', direction: 'asc' }}
        />
      </Panel>
    </>
  )
}
