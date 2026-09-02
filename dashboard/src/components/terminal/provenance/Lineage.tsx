/**
 * Provenance lineage.
 *
 * `/api/ml/provenance/{label}/{model}` has been serving a complete chain —
 * source, point-in-time returns, features, universe, model, backtest,
 * attribution — with per-stage evidence, and nothing had ever rendered it.
 *
 * The chain is drawn vertically with each stage's `kind` carried as a badge,
 * because the distinction between OBSERVED, DERIVED and MODEL_PREDICTED is the
 * whole point: it says which links in the chain are measurements and which are
 * this system's own inferences. A lineage that renders all stages identically
 * hides exactly the thing a reviewer is looking for.
 */
'use client'

import { useEffect, useState } from 'react'

import { Panel, StateBlock, Status, Value, type ResearchState } from '@/components/system'

interface SourceRow {
  dataset_id: string
  role?: string
  rows?: number
  min_date?: string
  max_date?: string
  point_in_time_status?: string
  survivorship_status?: string
  retrieved_at?: string
  partitions?: number
}

interface Stage {
  stage: string
  kind: string
  detail?: string
  evidence?: SourceRow[] | Record<string, unknown> | null
}

interface Chain {
  status?: string
  chain?: Stage[]
  dataset_version?: string
  content_hash?: string
  git_commit?: string
  message?: string
}

/** OBSERVED is a measurement; DERIVED and MODEL_PREDICTED are this system's own. */
function kindState(kind: string): ResearchState {
  switch (kind) {
    case 'OBSERVED': return 'recorded'
    case 'MODEL_PREDICTED': return 'experimental'
    case 'DERIVED': return 'candidate'
    default: return 'unknown'
  }
}

function isSourceRows(e: Stage['evidence']): e is SourceRow[] {
  return Array.isArray(e)
}

export default function Lineage({ label, model }: { label: string; model: string }) {
  const [chain, setChain] = useState<Chain | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`/api/ml/provenance/${encodeURIComponent(label)}/${encodeURIComponent(model)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Chain) => { if (alive) setChain(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [label, model])

  if (error) {
    return (
      <Panel title="Lineage" state="unavailable">
        <StateBlock state="unavailable" title="The chain could not be read" detail={`Request failed: ${error}. No lineage is shown in its place.`} />
      </Panel>
    )
  }
  if (!chain) return <Panel title="Lineage" state="waking"><StateBlock state="waking" title="Reading the chain" /></Panel>
  if (chain.status !== 'available' || !chain.chain?.length) {
    return (
      <Panel title="Lineage" state="unavailable">
        <StateBlock state="unavailable" title="No chain is recorded for this pair" detail={chain.message} />
      </Panel>
    )
  }

  return (
    <>
      <Panel title="Artifact" subtitle={`${label} · ${model}`} state="recorded">
        <table className="sys-table sys-table--compact">
          <tbody>
            <tr><td>Dataset version</td><td className="num" style={{ fontFamily: 'var(--font-mono)' }}>{chain.dataset_version ?? '—'}</td></tr>
            <tr><td>Content hash</td><td className="num" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>{chain.content_hash ?? '—'}</td></tr>
            <tr><td>Commit</td><td className="num" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>{chain.git_commit ?? '—'}</td></tr>
          </tbody>
        </table>
      </Panel>

      <Panel title="Chain" subtitle={`${chain.chain.length} stages`} flush>
        <ol className="lin">
          {chain.chain.map((s, i) => {
            const expanded = open === s.stage
            const rows = isSourceRows(s.evidence) ? s.evidence : null
            const fields = !rows && s.evidence && typeof s.evidence === 'object'
              ? Object.entries(s.evidence as Record<string, unknown>)
              : []
            const count = rows ? rows.length : fields.length
            return (
              <li key={s.stage} className="lin-row">
                <div className="lin-spine" aria-hidden>
                  <span className="lin-dot" data-kind={s.kind} />
                  {i < chain.chain!.length - 1 ? <span className="lin-line" /> : null}
                </div>
                <div className="lin-body">
                  <button
                    className="lin-head sys-focusable"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : s.stage)}
                  >
                    <span className="lin-stage">{s.stage}</span>
                    <Status state={kindState(s.kind)} label={s.kind.toLowerCase().replace(/_/g, ' ')} />
                    <span className="sys-meta">{count} {rows ? 'sources' : 'fields'}</span>
                    <span className="lin-caret" aria-hidden>{expanded ? '−' : '+'}</span>
                  </button>
                  {s.detail ? <p className="lin-detail">{s.detail}</p> : null}

                  {expanded && rows ? (
                    <div className="sys-scroll-x" style={{ marginTop: 'var(--d-2)' }}>
                      <table className="sys-table sys-table--compact">
                        <thead>
                          <tr>
                            <th>Dataset</th><th>Role</th><th className="num">Rows</th>
                            <th>From</th><th>To</th><th>PIT</th><th>Survivorship</th>
                            <th className="num">Parts</th><th>Retrieved</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r) => (
                            <tr key={`${r.dataset_id}-${r.role ?? ''}`}>
                              <td style={{ fontFamily: 'var(--font-mono)' }}>{r.dataset_id}</td>
                              <td>{r.role ?? '—'}</td>
                              <td className="num"><Value value={r.rows ?? null} digits={0} /></td>
                              <td className="num">{r.min_date ?? '—'}</td>
                              <td className="num">{r.max_date ?? '—'}</td>
                              <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.point_in_time_status ?? '—'}</span></td>
                              <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.survivorship_status ?? '—'}</span></td>
                              <td className="num"><Value value={r.partitions ?? null} digits={0} /></td>
                              <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.retrieved_at?.slice(0, 19) ?? '—'}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}

                  {expanded && fields.length ? (
                    <table className="sys-table sys-table--compact" style={{ marginTop: 'var(--d-2)' }}>
                      <tbody>
                        {fields.map(([k, v]) => (
                          <tr key={k}>
                            <td style={{ fontFamily: 'var(--font-mono)', width: '46%' }}>{k}</td>
                            <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal' }}>
                              {typeof v === 'number'
                                ? <Value value={v} digits={4} />
                                : v === null || v === undefined
                                  ? <span className="sys-null">—</span>
                                  : <span className="sys-meta" style={{ color: 'var(--ink)' }}>
                                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                    </span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>
      </Panel>
    </>
  )
}
