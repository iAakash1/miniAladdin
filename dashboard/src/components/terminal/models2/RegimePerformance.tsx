/**
 * Model performance broken out by market regime.
 *
 * Recorded by every experiment and rendered nowhere until now. It answers a
 * question an aggregate IC cannot: was the edge earned across conditions, or in
 * one of them.
 *
 * The regime share is shown beside every row for a reason. A regime holding 2%
 * of the sample cannot support a conclusion however good its IC looks, and a
 * table that reports the IC without the count invites exactly that reading. Rows
 * whose regime is too thin are marked rather than hidden, because their absence
 * would be its own distortion — a model that only worked in the dominant regime
 * should look like one.
 */
'use client'

import { useMemo, useState } from 'react'

import { BarRows } from '@/components/system/charts'
import { Grid, Panel, StateBlock, Status, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'

export interface RegimeRow {
  regime: string
  observations?: number
  dates?: number
  share?: number
  mean_ic?: number | null
  ic_t_stat?: number | null
  ic_hit_rate?: number | null
  directional_edge?: number | null
  spearman?: number | null
  mean_realised_return?: number | null
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Below this share of the sample a regime cannot carry a conclusion. */
const THIN_SHARE = 0.05

export default function RegimePerformance({
  byModel,
}: {
  byModel?: Record<string, RegimeRow[]> | null
}) {
  const models = useMemo(() => Object.keys(byModel ?? {}).sort(), [byModel])
  const [model, setModel] = useState<string | null>(null)
  const active = model && models.includes(model) ? model : models[0] ?? null
  const rows = active ? byModel?.[active] ?? [] : []

  const columns: DataColumn<RegimeRow>[] = useMemo(() => [
    {
      key: 'regime', header: 'Regime', width: '20%', sort: (r) => r.regime, text: (r) => r.regime,
      render: (r) => <span style={{ fontFamily: 'var(--font-mono)' }}>{r.regime.replace(/_/g, ' ')}</span>,
    },
    {
      key: 'share', header: 'Share of sample', numeric: true, sort: (r) => n(r.share),
      render: (r) => <Value value={n(r.share)} digits={4} />,
    },
    { key: 'obs', header: 'Observations', numeric: true, sort: (r) => n(r.observations), render: (r) => <Value value={n(r.observations)} digits={0} /> },
    { key: 'dates', header: 'Dates', numeric: true, sort: (r) => n(r.dates), render: (r) => <Value value={n(r.dates)} digits={0} /> },
    {
      key: 'ic', header: 'Mean IC', numeric: true, sort: (r) => n(r.mean_ic),
      render: (r) => (
        <Value
          value={n(r.mean_ic)} digits={5} signed tone
          title={r.mean_ic === null || r.mean_ic === undefined ? 'Not computed: too few dated observations in this regime' : undefined}
        />
      ),
    },
    { key: 't', header: 'IC t', numeric: true, sort: (r) => n(r.ic_t_stat), render: (r) => <Value value={n(r.ic_t_stat)} digits={3} signed /> },
    { key: 'hit', header: 'IC hit rate', numeric: true, optional: true, sort: (r) => n(r.ic_hit_rate), render: (r) => <Value value={n(r.ic_hit_rate)} digits={3} /> },
    { key: 'edge', header: 'Directional edge', numeric: true, optional: true, sort: (r) => n(r.directional_edge), render: (r) => <Value value={n(r.directional_edge)} digits={4} signed tone /> },
    {
      key: 'thin', header: 'Supportable', width: '13%',
      sort: (r) => ((n(r.share) ?? 0) >= THIN_SHARE ? 1 : 0),
      render: (r) => {
        const thin = (n(r.share) ?? 0) < THIN_SHARE
        return (
          <Status
            state={thin ? 'blocked' : 'recorded'}
            label={thin ? 'too thin' : 'yes'}
          />
        )
      },
    },
  ], [])

  if (!models.length) {
    return (
      <Panel title="Regime performance" state="unavailable">
        <StateBlock state="unavailable" title="No regime breakdown recorded" />
      </Panel>
    )
  }

  const supportable = rows.filter((r) => (n(r.share) ?? 0) >= THIN_SHARE && r.mean_ic !== null && r.mean_ic !== undefined)
  const positive = supportable.filter((r) => (r.mean_ic as number) > 0).length

  return (
    <>
      <Panel
        title="Regime performance"
        subtitle={active ?? undefined}
        flush
        actions={
          <select className="sys-input" value={active ?? ''} onChange={(e) => setModel(e.target.value)} aria-label="Model">
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        }
      >
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.regime}
          density="compact" filterPlaceholder="filter regimes"
          initialSort={{ key: 'share', direction: 'desc' }}
        />
      </Panel>

      <Grid>
        <Panel title="IC by regime" subtitle="thin regimes included, and marked">
          <BarRows
            unit="mean IC"
            rows={rows.map((r) => ({
              label: r.regime.replace(/_/g, ' '),
              value: n(r.mean_ic),
              note: `${((n(r.share) ?? 0) * 100).toFixed(1)}% of the sample, ${r.dates ?? '—'} dates`,
            }))}
          />
        </Panel>

        <Panel title="What this can support">
          <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '78ch' }}>
            {supportable.length
              ? `${positive} of ${supportable.length} regimes with enough sample show a positive IC. `
              : 'No regime here holds enough of the sample to support a conclusion. '}
            A regime with a few percent of the observations cannot carry one however
            good its coefficient looks, so the share travels with every row and the
            thin ones are marked rather than dropped — hiding them would make a
            model that only worked in the dominant regime look like one that worked
            everywhere.
          </p>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            A null IC means the regime had too few dated observations to compute
            one. It is not a zero.
          </p>
        </Panel>
      </Grid>
    </>
  )
}
