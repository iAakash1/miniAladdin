/**
 * Gate matrix: every registered model against every production threshold.
 *
 * A per-model gate list answers "why is this one blocked". The matrix answers
 * the more useful question — which gate blocks everything. When one column is
 * uniformly unmet across 103 entries, the constraint is structural rather than
 * a property of any model, and no amount of further search will move it.
 *
 * "Not recorded" is drawn distinctly from a numeric failure, because they call
 * for different work: one needs a measurement, the other needs a better model.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { Panel, StateBlock, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'

interface Entry {
  key: string
  model_id: string
  label: string
  status: string
  thresholds_not_met?: Record<string, unknown>
  candidate_thresholds_not_met?: Record<string, unknown>
  eligible_for?: string[]
}

interface Registry {
  entries?: Entry[]
  summary?: { entries: number }
  promotion_gates?: Record<string, string[]>
}

type Cell = 'met' | 'unrecorded' | 'failed'

function cellFor(entry: Entry, gate: string, scope: 'production' | 'candidate'): Cell {
  const map = scope === 'production' ? entry.thresholds_not_met : entry.candidate_thresholds_not_met
  if (!map || !(gate in map)) return 'met'
  return map[gate] === 'not recorded' ? 'unrecorded' : 'failed'
}

export default function GateMatrix() {
  const [registry, setRegistry] = useState<Registry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scope, setScope] = useState<'production' | 'candidate'>('production')

  useEffect(() => {
    let alive = true
    fetch('/api/ml/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Registry) => { if (alive) setRegistry(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const entries = useMemo(() => registry?.entries ?? [], [registry])

  const gates = useMemo(() => {
    const seen = new Set<string>()
    for (const e of entries) {
      const map = scope === 'production' ? e.thresholds_not_met : e.candidate_thresholds_not_met
      for (const g of Object.keys(map ?? {})) seen.add(g)
    }
    return [...seen].sort()
  }, [entries, scope])

  /** Per-gate tally. The column totals are the point of the surface. */
  const tally = useMemo(() => {
    return gates.map((g) => {
      let unrecorded = 0
      let failed = 0
      for (const e of entries) {
        const c = cellFor(e, g, scope)
        if (c === 'unrecorded') unrecorded += 1
        else if (c === 'failed') failed += 1
      }
      return { gate: g, unrecorded, failed, met: entries.length - unrecorded - failed }
    })
  }, [gates, entries, scope])

  const columns: DataColumn<{ gate: string; unrecorded: number; failed: number; met: number }>[] = [
    { key: 'gate', header: 'Gate', width: '30%', sort: (r) => r.gate, text: (r) => r.gate, render: (r) => <span style={{ fontFamily: 'var(--font-mono)' }}>{r.gate}</span> },
    { key: 'met', header: 'Met', numeric: true, sort: (r) => r.met, render: (r) => <span className="sys-num sys-pos">{r.met}</span> },
    { key: 'failed', header: 'Failed', unit: 'a number missed it', numeric: true, sort: (r) => r.failed, render: (r) => <span className="sys-num sys-neg">{r.failed}</span> },
    { key: 'unrec', header: 'Not recorded', unit: 'never measured', numeric: true, sort: (r) => r.unrecorded, render: (r) => <span className="sys-num sys-null">{r.unrecorded}</span> },
    {
      key: 'bar', header: 'Share met',
      render: (r) => {
        const total = Math.max(1, entries.length)
        return (
          <span style={{ display: 'inline-flex', width: 120, height: 8, border: '1px solid var(--rule)' }} title={`${r.met} of ${total} met`}>
            <span style={{ width: `${(r.met / total) * 100}%`, background: 'var(--e-pos)', opacity: 0.6 }} />
            <span style={{ width: `${(r.failed / total) * 100}%`, background: 'var(--e-neg)', opacity: 0.6 }} />
            <span style={{ width: `${(r.unrecorded / total) * 100}%`, background: 'var(--ink-faint)', opacity: 0.35 }} />
          </span>
        )
      },
    },
  ]

  if (error) return <Panel title="Gate matrix" state="unavailable"><StateBlock state="unavailable" title="The registry could not be read" detail={error} /></Panel>
  if (!registry) return <Panel title="Gate matrix" state="waking"><StateBlock state="waking" title="Reading the registry" /></Panel>
  if (!gates.length) return <Panel title="Gate matrix" state="unavailable"><StateBlock state="unavailable" title="No gate outcomes are recorded" /></Panel>

  const universal = tally.filter((t) => t.met === 0)
  const eligible = entries.filter((e) => (e.eligible_for ?? []).length > 0).length

  return (
    <>
      <Strip metrics={[
        { label: 'Entries', value: entries.length, digits: 0 },
        { label: 'Gates', value: gates.length, digits: 0 },
        { label: 'Cleared by none', value: universal.length, digits: 0, title: 'Gates no registered model has met — a structural constraint, not a model property' },
        { label: 'Eligible for something', value: eligible, digits: 0 },
      ]} />

      {universal.length ? (
        <Panel title="Blocked for everyone" state="blocked">
          <p style={{ margin: '0 0 var(--d-2)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            No registered model has met {universal.length === 1 ? 'this gate' : 'these gates'}.
            That is a statement about the research programme rather than about any
            model in it: more search will not move a threshold that nothing has
            ever cleared.
          </p>
          <table className="sys-table sys-table--compact">
            <tbody>
              {universal.map((u) => (
                <tr key={u.gate}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{u.gate}</td>
                  <td className="num sys-neg"><Value value={u.failed} digits={0} /> failed</td>
                  <td className="num sys-null"><Value value={u.unrecorded} digits={0} /> never measured</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}

      <Panel
        title="Gates"
        subtitle={`${scope} thresholds`}
        flush
        actions={
          <div className="sys-seg">
            {(['production', 'candidate'] as const).map((s) => (
              <button key={s} className="sys-btn" aria-pressed={scope === s} onClick={() => setScope(s)}>{s}</button>
            ))}
          </div>
        }
      >
        <DataTable
          columns={columns} rows={tally} rowKey={(r) => r.gate}
          density="normal" filterPlaceholder="filter gates"
          initialSort={{ key: 'met', direction: 'asc' }}
        />
      </Panel>

      <Panel title="Matrix" subtitle={`${entries.length} entries × ${gates.length} gates`} flush>
        <div className="sys-scroll-x" style={{ maxHeight: 420, overflowY: 'auto' }}>
          <table className="sys-table sys-table--compact">
            <thead>
              <tr>
                <th style={{ position: 'sticky', left: 0, zIndex: 3, background: 'var(--p-sunken)', minWidth: 190 }}>Model</th>
                {gates.map((g) => (
                  <th key={g} className="num" style={{ minWidth: 74 }} title={g}>
                    {g.length > 12 ? `${g.slice(0, 11)}…` : g}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.key}>
                  <td style={{ position: 'sticky', left: 0, zIndex: 1, background: 'var(--p-panel)', fontFamily: 'var(--font-mono)' }} title={e.key}>
                    {e.model_id.length > 24 ? `${e.model_id.slice(0, 23)}…` : e.model_id}
                  </td>
                  {gates.map((g) => {
                    const c = cellFor(e, g, scope)
                    return (
                      <td key={g} className="num" title={`${e.model_id} · ${g}: ${c === 'met' ? 'met' : c === 'unrecorded' ? 'never measured' : 'failed on a recorded value'}`}>
                        {c === 'met'
                          ? <span className="sys-pos">✓</span>
                          : c === 'failed'
                            ? <span className="sys-neg">✕</span>
                            : <span className="sys-null">·</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', gap: 'var(--d-4)', padding: 'var(--d-2) var(--d-3)', borderTop: '1px solid var(--rule)', flexWrap: 'wrap' }}>
          <span className="sys-meta"><span className="sys-pos">✓</span> met</span>
          <span className="sys-meta"><span className="sys-neg">✕</span> a recorded value missed the threshold</span>
          <span className="sys-meta"><span className="sys-null">·</span> never measured — unmet, and needing a measurement rather than a better model</span>
        </div>
      </Panel>
    </>
  )
}
