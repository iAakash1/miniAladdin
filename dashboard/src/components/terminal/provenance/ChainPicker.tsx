/**
 * Chooses which label and model to trace.
 *
 * Options come from the registry rather than a hardcoded pair, so the picker
 * offers what actually has a chain and nothing else. A selector listing
 * combinations with no recorded lineage would send the reader to an empty
 * workspace, which reads as a broken page rather than as an untraced model.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { Panel, StateBlock } from '@/components/system'

interface Row { model_id: string; label: string; status?: string }

export default function ChainPicker({ label, model }: { label: string; model: string }) {
  const router = useRouter()
  /**
   * Three states, deliberately not two.
   *
   * A registry that could not be read and a registry holding nothing are
   * different facts, and collapsing both to an empty array makes the second
   * message a lie whenever the first is what happened — or the reverse. The
   * third case is a response that arrived without a leaderboard at all, which
   * is a malformed payload rather than an empty one.
   */
  const [state, setState] = useState<
    | { status: 'reading' }
    | { status: 'ready'; rows: Row[] }
    | { status: 'malformed' }
    | { status: 'failed'; detail: string }
  >({ status: 'reading' })

  useEffect(() => {
    let alive = true
    fetch('/api/ml/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`the registry request returned ${r.status}`))))
      .then((d: { leaderboard?: Row[] }) => {
        if (!alive) return
        setState(Array.isArray(d.leaderboard)
          ? { status: 'ready', rows: d.leaderboard }
          : { status: 'malformed' })
      })
      .catch((e: Error) => { if (alive) setState({ status: 'failed', detail: e.message }) })
    return () => { alive = false }
  }, [])

  const rows = state.status === 'ready' ? state.rows : null

  const labels = useMemo(() => [...new Set((rows ?? []).map((r) => r.label))].sort(), [rows])
  const models = useMemo(
    () => [...new Set((rows ?? []).filter((r) => r.label === label).map((r) => r.model_id))].sort(),
    [rows, label],
  )

  const go = (nextLabel: string, nextModel: string) => {
    router.push(
      `/terminal/provenance?label=${encodeURIComponent(nextLabel)}&model=${encodeURIComponent(nextModel)}`,
    )
  }

  return (
    <Panel
      title="Trace"
      subtitle={`${label} · ${model}`}
      actions={
        rows?.length ? (
          <div style={{ display: 'flex', gap: 'var(--d-2)', alignItems: 'center' }}>
            <select
              className="sys-input" value={label} aria-label="Label"
              onChange={(e) => {
                const nextLabel = e.target.value
                const first = (rows ?? []).find((r) => r.label === nextLabel)?.model_id
                if (first) go(nextLabel, first)
              }}
            >
              {labels.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
            <select
              className="sys-input" value={models.includes(model) ? model : ''} aria-label="Model"
              onChange={(e) => go(label, e.target.value)}
            >
              {!models.includes(model) ? <option value="">{model}</option> : null}
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        ) : null
      }
    >
      {state.status === 'reading' ? (
        <span className="sys-meta">reading the registry…</span>
      ) : state.status === 'failed' ? (
        <StateBlock
          state="unavailable"
          title="The registry could not be read"
          detail={`${state.detail}. The chain below still loads for the address given; only the picker is unavailable.`}
        />
      ) : state.status === 'malformed' ? (
        <StateBlock
          state="unavailable"
          title="The registry responded without a leaderboard"
          detail="The response arrived but did not carry the field this picker reads. That is a different failure from an empty registry, and no list is shown in its place."
        />
      ) : rows?.length ? (
        <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '86ch' }}>
          {models.length} models are registered against {label}. The chain below is
          reconstructed from the artifact each one recorded, so a model with no
          stored lineage reports that rather than showing a partial one.
        </p>
      ) : (
        <StateBlock
          state="recorded"
          title="No models are registered"
          detail="The registry was read and holds no entries. That is a measured emptiness, not a failure to look."
        />
      )}
    </Panel>
  )
}
