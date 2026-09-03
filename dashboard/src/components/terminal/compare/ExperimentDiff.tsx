/**
 * Experiment difference engine.
 *
 * What changed between two experiments, and — the harder discipline — what a
 * difference does and does not license you to say.
 *
 * Two experiments differ in many ways at once: features, universe, model set,
 * window, cost assumptions. Attributing a change in IC to any one of them is
 * not something a diff can support, so nothing here is presented as a cause.
 * The panel says this out loud, because a table of before-and-after numbers is
 * an invitation to draw exactly that conclusion.
 */
'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { Panel, Prose, StateBlock, Status, Strip, Value } from '@/components/system'
import { recordVisit } from '@/lib/research/history'
import { ObjectHeader, TableSkeleton } from '@/components/system/composition'

interface Detail {
  experiment_id?: string
  void?: boolean
  void_reason?: string | null
  definition?: Record<string, unknown>
  fingerprint?: string
  generated_at?: string
  git_commit?: string
  runtime_seconds?: number
  dataset?: Record<string, unknown>
  features_used?: string[]
  dataset_sources?: { dataset_id: string }[]
  primary_target?: string
  leaderboard?: Record<string, unknown>[]
  fold_rows?: unknown[]
  trials_used_for_correction?: number
  probability_of_backtest_overfitting?: Record<string, unknown>
}

type Change = 'same' | 'changed' | 'added' | 'removed' | 'absent'

interface Row {
  label: string
  group: string
  a: string
  b: string
  change: Change
  note?: string
}

const CHANGE_STATE: Record<Change, 'recorded' | 'experimental' | 'candidate' | 'unavailable' | 'blocked'> = {
  same: 'recorded',
  changed: 'experimental',
  added: 'candidate',
  removed: 'blocked',
  absent: 'unavailable',
}

function show(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  if (typeof v === 'object') return JSON.stringify(v).slice(0, 60)
  const s = String(v)
  return s.length > 60 ? `${s.slice(0, 59)}…` : s
}

function compareValues(label: string, group: string, a: unknown, b: unknown, note?: string): Row {
  const missingA = a === null || a === undefined
  const missingB = b === null || b === undefined
  const change: Change = missingA && missingB
    ? 'absent'
    : missingA ? 'added'
      : missingB ? 'removed'
        : show(a) === show(b) ? 'same' : 'changed'
  return { label, group, a: show(a), b: show(b), change, note }
}

export default function ExperimentDiff() {
  const [ids, setIds] = useState<string[]>([])
  const [left, setLeft] = useState('EXP-006')
  const [right, setRight] = useState('EXP-007')
  // Each side is tagged with the id it was fetched for, so a stale response is
  // filtered at render rather than cleared inside the effect. The clear-then-
  // refetch shape drops a frame showing neither the old value nor the new.
  const [aRaw, setA] = useState<{ id: string; data: Detail } | null>(null)
  const [bRaw, setB] = useState<{ id: string; data: Detail } | null>(null)
  const [errors, setErrors] = useState<string[]>([])

  useEffect(() => {
    let alive = true
    fetch('/api/quant/experiments')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setIds((d.experiments ?? []).map((e: { experiment_id: string }) => e.experiment_id)) })
      .catch((e: Error) => { if (alive) setErrors((p) => [...p, `list: ${e.message}`]) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    const load = (id: string, set: (d: { id: string; data: Detail }) => void) => {
      fetch(`/api/quant/experiments/${encodeURIComponent(id)}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((d: Detail) => { if (alive) set({ id, data: d }) })
        .catch((e: Error) => { if (alive) setErrors((p) => [...p, `${id}: ${e.message}`]) })
    }
    load(left, setA)
    load(right, setB)
    recordVisit({ kind: 'experiment', id: left, label: left })
    recordVisit({ kind: 'experiment', id: right, label: right })
    return () => { alive = false }
  }, [left, right])

  const a = aRaw?.id === left ? aRaw.data : null
  const b = bRaw?.id === right ? bRaw.data : null

  const rows = useMemo((): Row[] => {
    if (!a || !b) return []
    const featuresA = new Set(a.features_used ?? [])
    const featuresB = new Set(b.features_used ?? [])
    const sourcesA = new Set((a.dataset_sources ?? []).map((s) => s.dataset_id))
    const sourcesB = new Set((b.dataset_sources ?? []).map((s) => s.dataset_id))

    const featureAdds = [...featuresB].filter((f) => !featuresA.has(f))
    const featureDrops = [...featuresA].filter((f) => !featuresB.has(f))
    const sourceAdds = [...sourcesB].filter((s) => !sourcesA.has(s))
    const sourceDrops = [...sourcesA].filter((s) => !sourcesB.has(s))

    return [
      compareValues('experiment', 'Identity', a.experiment_id, b.experiment_id),
      compareValues('void', 'Identity', String(a.void ?? false), String(b.void ?? false)),
      compareValues('generated', 'Identity', a.generated_at?.slice(0, 19), b.generated_at?.slice(0, 19)),
      compareValues('commit', 'Identity', a.git_commit?.slice(0, 10), b.git_commit?.slice(0, 10)),
      compareValues('fingerprint', 'Identity', a.fingerprint?.slice(0, 14), b.fingerprint?.slice(0, 14)),

      compareValues('primary target', 'Design', a.primary_target, b.primary_target),
      compareValues('features used', 'Design', a.features_used?.length, b.features_used?.length),
      {
        label: 'features added', group: 'Design',
        a: '—', b: featureAdds.length ? featureAdds.join(', ') : '—',
        change: featureAdds.length ? 'added' : 'same',
      },
      {
        label: 'features removed', group: 'Design',
        a: featureDrops.length ? featureDrops.join(', ') : '—', b: '—',
        change: featureDrops.length ? 'removed' : 'same',
      },
      compareValues('dataset sources', 'Design', sourcesA.size, sourcesB.size),
      {
        label: 'sources added', group: 'Design',
        a: '—', b: sourceAdds.length ? sourceAdds.join(', ') : '—',
        change: sourceAdds.length ? 'added' : 'same',
      },
      {
        label: 'sources removed', group: 'Design',
        a: sourceDrops.length ? sourceDrops.join(', ') : '—', b: '—',
        change: sourceDrops.length ? 'removed' : 'same',
      },

      compareValues('models evaluated', 'Scale', a.leaderboard?.length, b.leaderboard?.length),
      compareValues('folds', 'Scale', a.fold_rows?.length, b.fold_rows?.length),
      compareValues(
        'trials for correction', 'Scale', a.trials_used_for_correction, b.trials_used_for_correction,
        'The count every significance claim is corrected against. A larger search needs a larger t to mean the same thing.',
      ),
      compareValues('runtime', 'Scale', a.runtime_seconds, b.runtime_seconds),
    ]
  }, [a, b])

  const counts = useMemo(() => {
    const out: Record<Change, number> = { same: 0, changed: 0, added: 0, removed: 0, absent: 0 }
    for (const r of rows) out[r.change] += 1
    return out
  }, [rows])

  return (
    <>
      <ObjectHeader
        glyph="Δ"
        name="Difference"
        kind="experiment against experiment"
        state={a && b ? 'recorded' : 'waking'}
        detail={`${left} → ${right}`}
        facts={[
          { label: 'Fields', value: rows.length || null, kind: 'count' },
          { label: 'Changed', value: counts.changed || null, kind: 'count' },
          { label: 'Added', value: counts.added || null, kind: 'count' },
          { label: 'Removed', value: counts.removed || null, kind: 'count' },
        ]}
        actions={
          <>
            <Link href="/terminal/experiments" className="sys-btn">experiments</Link>
            <Link href="/terminal/compare" className="sys-btn">compare models</Link>
          </>
        }
      />

      <Panel
        title="Select"
        actions={
          <div style={{ display: 'flex', gap: 'var(--d-2)', alignItems: 'center' }}>
            <select className="sys-input" value={left} onChange={(e) => setLeft(e.target.value)} aria-label="Left experiment">
              {ids.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
            <span className="sys-meta">against</span>
            <select className="sys-input" value={right} onChange={(e) => setRight(e.target.value)} aria-label="Right experiment">
              {ids.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </div>
        }
      >
        <Prose>
          Two experiments differ in many ways at once. Nothing below is presented
          as a cause: attributing a change in a result to any single difference is
          not something a diff can support, and a table of before-and-after
          numbers is an invitation to do exactly that.
        </Prose>
      </Panel>

      {errors.length ? (
        <Panel title="Unavailable" state="unavailable">
          <StateBlock
            state="unavailable"
            title="One or both experiments could not be read"
            detail={`${[...new Set(errors)].join('; ')}. A diff needs both sides; nothing is compared against a placeholder.`}
          />
        </Panel>
      ) : null}

      {!a || !b ? (
        <Panel title="Difference" state="waking" flush><TableSkeleton rows={12} columns={4} /></Panel>
      ) : (
        <>
          <Strip metrics={[
            { label: 'Fields compared', value: rows.length, digits: 0, kind: 'count' },
            { label: 'Same', value: counts.same, digits: 0, kind: 'count' },
            { label: 'Changed', value: counts.changed, digits: 0, kind: 'count' },
            { label: 'Added', value: counts.added, digits: 0, kind: 'count' },
            { label: 'Removed', value: counts.removed, digits: 0, kind: 'count' },
            { label: 'Not recorded either side', value: counts.absent, digits: 0, kind: 'count' },
          ]} />

          <Panel title="Difference" subtitle={`${left} → ${right}`} flush>
            <div className="sys-scroll-x">
              <table className="sys-table sys-table--compact">
                <thead>
                  <tr>
                    <th style={{ minWidth: 170 }}>Field</th>
                    <th className="num" style={{ minWidth: 160 }}>{left}</th>
                    <th className="num" style={{ minWidth: 160 }}>{right}</th>
                    <th style={{ minWidth: 100 }}>Change</th>
                  </tr>
                </thead>
                <tbody>
                  {[...new Set(rows.map((r) => r.group))].map((group) => (
                    <>
                      <tr key={`g-${group}`}>
                        <td colSpan={4} className="sys-label" style={{ background: 'var(--p-sunken)', fontSize: 'var(--t-micro)', height: 'var(--row-compact)' }}>
                          {group}
                        </td>
                      </tr>
                      {rows.filter((r) => r.group === group).map((r) => (
                        <tr key={r.label}>
                          <td style={{ fontFamily: 'var(--font-mono)' }} title={r.note}>{r.label}</td>
                          <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal' }}>{r.a}</td>
                          <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal' }}>{r.b}</td>
                          <td><Status state={CHANGE_STATE[r.change]} label={r.change} /></td>
                        </tr>
                      ))}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="What a difference does not tell you">
            <Prose>
              If the trial count grew between these two, every significance claim
              in the later one is measured against a higher bar — the best of a
              larger search reaches a larger statistic by chance alone. A result
              that looks similar across the pair may therefore be weaker in the
              later experiment even where the number is unchanged.
            </Prose>
            <table className="sys-table sys-table--compact" style={{ marginTop: 'var(--d-2)' }}>
              <tbody>
                <tr>
                  <td>Trials for correction</td>
                  <td className="num"><Value value={a.trials_used_for_correction ?? null} kind="count" /></td>
                  <td className="num"><Value value={b.trials_used_for_correction ?? null} kind="count" /></td>
                </tr>
              </tbody>
            </table>
          </Panel>
        </>
      )}
    </>
  )
}
