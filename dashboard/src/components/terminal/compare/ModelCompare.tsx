/**
 * Model comparison.
 *
 * Select any number of registry entries; the first becomes the baseline and
 * everything else is measured against it. Most fields carry no declared
 * direction on purpose: turnover, IC dispersion and observation counts are
 * facts about a model, not scores, and colouring them would be an opinion
 * dressed as a measurement.
 */
'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { Compare, CompareLegend, type CompareField, type CompareSubject } from '@/components/system/Compare'
import { Panel, Prose, StateBlock, Status } from '@/components/system'
import { ObjectHeader, TableSkeleton } from '@/components/system/composition'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'

interface Row {
  key: string
  model_id: string
  label: string
  status: string
  mean_ic: number | null
  ic_t_stat: number | null
  fold_ic_positive_rate: number | null
  net_sharpe: number | null
  net_cagr: number | null
  max_drawdown: number | null
  annualised_turnover: number | null
  cost_share_of_gross?: number | null
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/**
 * Each field names its semantic kind, and the kind supplies precision,
 * comparability and direction. A `direction` is stated only where the metric's
 * role here differs from what its kind implies.
 *
 * max_drawdown was declared higher-better, which is the wrong way round —
 * a drawdown closer to zero is the better outcome, and the field said the
 * opposite. Its kind carries the right answer, so the declaration is gone
 * rather than corrected: a fact stated in two places is a fact that can
 * disagree with itself.
 */
const FIELDS: CompareField[] = [
  { key: 'mean_ic', label: 'mean_ic', unit: 'rank corr.', group: 'Signal', kind: 'ic', value: (r) => n(r.mean_ic) },
  { key: 'ic_t_stat', label: 'ic_t_stat', unit: 'Newey-West', group: 'Signal', kind: 'tstat', value: (r) => n(r.ic_t_stat) },
  { key: 'fold_ic_positive_rate', label: 'fold_ic_positive_rate', group: 'Signal', kind: 'share', direction: 'higher-better', value: (r) => n(r.fold_ic_positive_rate) },
  { key: 'net_sharpe', label: 'net_sharpe', unit: 'after costs', group: 'Portfolio', kind: 'sharpe', value: (r) => n(r.net_sharpe) },
  { key: 'net_cagr', label: 'net_cagr', group: 'Portfolio', kind: 'return', value: (r) => n(r.net_cagr) },
  { key: 'max_drawdown', label: 'max_drawdown', group: 'Portfolio', kind: 'drawdown', value: (r) => n(r.max_drawdown) },
  // Turnover has no better end without knowing the strategy, and its kind
  // agrees, so nothing is declared here.
  { key: 'annualised_turnover', label: 'annualised_turnover', unit: 'one-way', group: 'Implementation', kind: 'multiple', value: (r) => n(r.annualised_turnover) },
  // A proportion has no inherent direction; in this role a smaller share of
  // gross eaten by cost is unambiguously better, so the field says so.
  { key: 'cost_share_of_gross', label: 'cost_share_of_gross', unit: '≤ 0.75 to pass', group: 'Implementation', kind: 'share', direction: 'lower-better', value: (r) => n(r.cost_share_of_gross) },
]

export default function ModelCompare() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>([])

  useEffect(() => {
    let alive = true
    fetch('/api/ml/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setRows(d.leaderboard ?? []) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const columns: DataColumn<Row>[] = useMemo(() => [
    {
      key: 'pick', header: '', width: '36px',
      render: (r) => (
        <input
          type="checkbox"
          checked={picked.includes(r.key)}
          onChange={(e) => {
            e.stopPropagation()
            setPicked((p) => (p.includes(r.key) ? p.filter((k) => k !== r.key) : [...p, r.key]))
          }}
          onClick={(e) => e.stopPropagation()}
          aria-label={`Compare ${r.model_id}`}
        />
      ),
    },
    { key: 'model', header: 'Model', width: '24%', sort: (r) => r.model_id, text: (r) => r.model_id, render: (r) => <span className="sys-mono">{r.model_id}</span> },
    { key: 'label', header: 'Label', width: '14%', sort: (r) => r.label, text: (r) => r.label, render: (r) => <span className="sys-meta sys-meta--strong">{r.label}</span> },
    { key: 'status', header: 'Status', width: '13%', sort: (r) => r.status, text: (r) => r.status, render: (r) => <Status state={r.status === 'retired' ? 'unavailable' : 'experimental'} label={r.status} /> },
    { key: 'ic', header: 'Mean IC', unit: 'rank corr.', numeric: true, sort: (r) => n(r.mean_ic), render: (r) => <span className="sys-num">{r.mean_ic?.toFixed(4) ?? '—'}</span> },
    { key: 't', header: 'IC t', unit: 'Newey-West', numeric: true, sort: (r) => n(r.ic_t_stat), render: (r) => <span className="sys-num">{r.ic_t_stat?.toFixed(2) ?? '—'}</span> },
    { key: 'ns', header: 'Net Sharpe', unit: 'after costs', numeric: true, sort: (r) => n(r.net_sharpe), render: (r) => <span className="sys-num">{r.net_sharpe?.toFixed(3) ?? '—'}</span> },
  ], [picked])

  if (error) return <Panel title="Compare" state="unavailable"><StateBlock state="unavailable" title="The registry could not be read" detail={error} /></Panel>
  if (!rows) {
    return <Panel title="Select models" state="waking" flush><TableSkeleton rows={10} columns={7} /></Panel>
  }

  const subjects: CompareSubject[] = picked
    .map((k) => rows.find((r) => r.key === k))
    .filter((r): r is Row => Boolean(r))
    // The label is the prediction target, and it is the basis these numbers
    // are measured against. A mean IC against fwd_rank_21 and one against
    // fwd_ret_21 are both dimensionless and both called "mean_ic"; subtracting
    // one from the other gives a number with no meaning, which would still be
    // painted green whenever it came out positive.
    .map((r) => ({
      id: r.key,
      label: r.model_id,
      detail: r.label,
      basis: r.label,
      data: r as unknown as Record<string, unknown>,
    }))

  return (
    <>
      <ObjectHeader
        glyph="⇄"
        name="Compare"
        kind="model against model"
        state={subjects.length >= 2 ? 'recorded' : 'unknown'}
        detail={subjects.length >= 2 ? `${subjects[0].label} is the baseline` : 'choose two or more'}
        facts={[
          { label: 'Registered', value: rows.length, kind: 'count' },
          { label: 'Selected', value: picked.length, kind: 'count' },
          { label: 'Fields', value: FIELDS.length, kind: 'count' },
        ]}
        actions={
          <>
            <Link href="/terminal/evidence" className="sys-btn">evidence</Link>
            <Link href="/terminal/gates" className="sys-btn">gates</Link>
            <Link href="/terminal/diff" className="sys-btn">difference</Link>
          </>
        }
      />

      <Panel
        title="Select models"
        subtitle={picked.length ? `${picked.length} selected` : 'choose two or more'}
        flush
        actions={picked.length ? <button className="sys-btn" onClick={() => setPicked([])}>clear</button> : null}
      >
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.key}
          density="compact" filterPlaceholder="filter models"
          initialSort={{ key: 'ic', direction: 'desc' }}
          onSelect={(r) => {
            recordVisit({ kind: 'model', id: r.model_id, label: r.model_id, detail: r.label, state: r.status })
            setPicked((p) => (p.includes(r.key) ? p.filter((k) => k !== r.key) : [...p, r.key]))
          }}
        />
      </Panel>

      <Panel
        title="Comparison"
        subtitle={subjects.length >= 2 ? `${subjects[0].label} is the baseline` : undefined}
        flush
      >
        <Compare subjects={subjects} fields={FIELDS} />
        {subjects.length >= 2 ? <CompareLegend /> : null}
      </Panel>

      {subjects.length >= 2 ? (
        <Panel title="Reading a comparison">
          <Prose>
            A better number on one metric is not a better model. These entries were
            selected from a search whose cumulative trial count is what any
            significance claim must be corrected against, and a model that leads on
            IC while recording no deflated Sharpe has not out-argued one that
            recorded a failing value — it has recorded less.
          </Prose>
        </Panel>
      ) : null}
    </>
  )
}
