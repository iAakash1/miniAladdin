/**
 * The validation ladder.
 *
 * Promotion is a sequence of states, and the registry publishes both what each
 * model has reached and what it is `eligible_for` next. Drawn as a ladder, the
 * distribution says something no per-model view can: where the programme is
 * stuck.
 *
 * The rungs are the registry's own promotion gates, in order, with the
 * requirements it lists for each. Nothing here is invented — an empty rung is
 * an empty rung, and a ladder whose top three are empty is the honest picture.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { Panel, StateBlock, Status, type ResearchState } from '@/components/system'
import { TableSkeleton } from '@/components/system/composition'

interface Entry {
  key: string
  model_id: string
  label: string
  status: string
  eligible_for?: string[]
}

interface Registry {
  entries?: Entry[]
  promotion_gates?: Record<string, string[]>
}

/** The rungs, in the order a model climbs them. */
const LADDER: { id: string; label: string; blurb: string; state: ResearchState }[] = [
  { id: 'experimental', label: 'Experimental', blurb: 'Measured. Not promotable.', state: 'experimental' },
  { id: 'validated', label: 'Validated', blurb: 'Walk-forward results, a written methodology, a baseline comparison.', state: 'candidate' },
  { id: 'production_candidate', label: 'Candidate', blurb: 'Cleared the development gates. The holdout has not been spent.', state: 'candidate' },
  { id: 'production', label: 'Production', blurb: 'Armed and serving.', state: 'production' },
]

export default function ValidationLadder() {
  const [registry, setRegistry] = useState<Registry | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/ml/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Registry) => { if (alive) setRegistry(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const entries = useMemo(() => registry?.entries ?? [], [registry])

  const rungs = useMemo(() => LADDER.map((rung) => {
    const at = entries.filter((e) => e.status === rung.id)
    const eligible = entries.filter(
      (e) => e.status !== rung.id && (e.eligible_for ?? []).includes(rung.id),
    )
    return { ...rung, at, eligible, requirements: registry?.promotion_gates?.[rung.id] ?? [] }
  }), [entries, registry])

  const retired = entries.filter((e) => e.status === 'retired').length
  const highest = [...rungs].reverse().find((r) => r.at.length)

  if (error) return <Panel title="Ladder" state="unavailable"><StateBlock state="unavailable" title="The registry could not be read" detail={error} /></Panel>
  if (!registry) {
    return <Panel title="Validation ladder" state="waking" flush><TableSkeleton rows={4} columns={3} /></Panel>
  }

  return (
    <>
      <Panel
        title="Validation ladder"
        subtitle={highest ? `nothing has climbed past ${highest.label.toLowerCase()}` : undefined}
        state={rungs[3].at.length ? 'production' : 'blocked'}
        flush
      >
        <div style={{ padding: 'var(--d-3)' }}>
          {rungs.map((rung, i) => {
            const total = Math.max(1, entries.length)
            return (
              <div key={rung.id} style={{ display: 'grid', gridTemplateColumns: '16px 1fr', gap: 'var(--d-3)' }}>
                <div className="lin-spine" aria-hidden>
                  <span
                    className="lin-dot"
                    style={{
                      color: rung.at.length ? 'var(--ink)' : 'var(--ink-faint)',
                      background: rung.at.length ? 'currentColor' : 'transparent',
                    }}
                  />
                  {i < rungs.length - 1 ? <span className="lin-line" /> : null}
                </div>
                <div style={{ paddingBottom: 'var(--d-4)', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--d-2)', flexWrap: 'wrap' }}>
                    <span className="sys-lead">{rung.label}</span>
                    <Status state={rung.at.length ? rung.state : 'unavailable'} label={`${rung.at.length} models`} />
                    {rung.eligible.length ? (
                      <span className="sys-meta">{rung.eligible.length} eligible to enter</span>
                    ) : null}
                  </div>
                  <p className="lin-detail">{rung.blurb}</p>

                  <div style={{ display: 'flex', height: 8, border: '1px solid var(--rule)', marginTop: 'var(--d-2)', maxWidth: 420 }}>
                    <span style={{ width: `${(rung.at.length / total) * 100}%`, background: 'var(--e-pos)', opacity: 0.6 }} />
                    <span style={{ width: `${(rung.eligible.length / total) * 100}%`, background: 'var(--s-candidate)', opacity: 0.4 }} />
                  </div>

                  {rung.requirements.length ? (
                    <ul style={{ margin: 'var(--d-2) 0 0', paddingLeft: 'var(--d-4)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                      {rung.requirements.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  ) : null}

                  {rung.eligible.length ? (
                    <div style={{ marginTop: 'var(--d-2)' }}>
                      <div className="sys-label" style={{ fontSize: 'var(--t-micro)', marginBottom: 'var(--d-1)' }}>
                        Eligible but not there
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-1)' }}>
                        {rung.eligible.slice(0, 12).map((e) => (
                          <span key={e.key} className="sys-btn" style={{ cursor: 'default' }} title={`${e.model_id} · ${e.label}`}>
                            {e.model_id.length > 22 ? `${e.model_id.slice(0, 21)}…` : e.model_id}
                          </span>
                        ))}
                        {rung.eligible.length > 12 ? <span className="sys-meta">+{rung.eligible.length - 12} more</span> : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      </Panel>

      <Panel title="What the shape says">
        <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
          {entries.length} models are registered and{' '}
          {rungs[0].at.length} sit on the first rung, with {retired} retired.
          {rungs[1].at.length + rungs[2].at.length + rungs[3].at.length === 0
            ? ' Nothing has been promoted past experimental. That is not a display problem — it is the state of the research, and the gate matrix shows which threshold is holding.'
            : ''}
        </p>
        <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
          An empty rung is drawn empty. A ladder that filled itself to look
          healthy would be the exact failure this product exists to avoid.
        </p>
      </Panel>
    </>
  )
}
