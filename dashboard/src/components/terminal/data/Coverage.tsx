/**
 * Dataset coverage.
 *
 * Which source spans which period, drawn on one shared axis. A catalogue lists
 * datasets; this shows where they overlap — and the overlap is what actually
 * bounds an experiment, because a panel can only start once every source it
 * needs has begun.
 *
 * The usable window is computed as the intersection and marked, since that is
 * the constraint no individual row reveals.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { Panel, Prose, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { StripSkeleton, TableSkeleton } from '@/components/system/composition'

interface Source {
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

function pitState(status?: string): ResearchState {
  const v = (status ?? '').toLowerCase()
  if (v.includes('point_in_time')) return 'recorded'
  if (v.includes('unknown') || !v) return 'unknown'
  return 'stale'
}

const DAY = 86_400_000

export default function Coverage() {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/latest')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setSources(d.dataset_sources ?? []) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const dated = useMemo(
    () => (sources ?? []).filter((s) => s.min_date && s.max_date),
    [sources],
  )

  const bounds = useMemo(() => {
    if (!dated.length) return null
    const starts = dated.map((s) => Date.parse(s.min_date!))
    const ends = dated.map((s) => Date.parse(s.max_date!))
    return {
      first: Math.min(...starts),
      last: Math.max(...ends),
      // The panel can only begin once every source has, and must end when the
      // first one stops. That intersection is the real usable window.
      usableFrom: Math.max(...starts),
      usableTo: Math.min(...ends),
    }
  }, [dated])

  if (error) {
    return <Panel title="Coverage" state="unavailable"><StateBlock state="unavailable" title="Sources could not be read" detail={error} /></Panel>
  }
  if (!sources) {
    return (
      <>
        <StripSkeleton />
        <Panel title="Coverage" state="waking" flush><TableSkeleton rows={9} columns={5} /></Panel>
      </>
    )
  }
  if (!dated.length) {
    return <Panel title="Coverage" state="unavailable"><StateBlock state="unavailable" title="No source carries a date range" detail="Nothing is drawn where a range was not recorded." /></Panel>
  }

  const span = Math.max(1, bounds!.last - bounds!.first)
  const pos = (t: number) => ((t - bounds!.first) / span) * 100
  const usableDays = Math.max(0, Math.round((bounds!.usableTo - bounds!.usableFrom) / DAY))
  const totalDays = Math.round(span / DAY)
  const undated = (sources.length - dated.length)

  return (
    <>
      <Strip metrics={[
        { label: 'Sources', value: sources.length, digits: 0 },
        { label: 'With a range', value: dated.length, digits: 0 },
        { label: 'Earliest', value: new Date(bounds!.first).toISOString().slice(0, 10), digits: 0 },
        { label: 'Latest', value: new Date(bounds!.last).toISOString().slice(0, 10), digits: 0 },
        { label: 'Union', value: totalDays, digits: 0, unit: 'd' },
        { label: 'Usable intersection', value: usableDays, digits: 0, unit: 'd', title: 'A panel can only start once every source has, and must end when the first one stops' },
      ]} />

      <Panel
        title="Usable window"
        state={usableDays > 0 ? 'recorded' : 'blocked'}
      >
        <Prose>
          The sources together span {totalDays} days, but only{' '}
          <strong style={{ color: 'var(--ink)' }}>{usableDays} days</strong> are covered by all of
          them at once — {new Date(bounds!.usableFrom).toISOString().slice(0, 10)} to{' '}
          {new Date(bounds!.usableTo).toISOString().slice(0, 10)}. That intersection, not the
          union, bounds any experiment needing every source, and it is the figure no
          individual row shows.
        </Prose>
      </Panel>

      <Panel title="Coverage" subtitle={`${dated.length} dated sources`} flush>
        <div style={{ padding: 'var(--d-3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--d-2)' }}>
            <span className="sys-meta">{new Date(bounds!.first).toISOString().slice(0, 10)}</span>
            <span className="sys-meta">{new Date(bounds!.last).toISOString().slice(0, 10)}</span>
          </div>

          {dated.map((s) => {
            const from = Date.parse(s.min_date!)
            const to = Date.parse(s.max_date!)
            return (
              <div
                key={`${s.dataset_id}-${s.role ?? ''}`}
                style={{ display: 'grid', gridTemplateColumns: '190px 1fr 96px', gap: 'var(--d-2)', alignItems: 'center', height: 'var(--row-compact)' }}
              >
                <span
                  className="sys-meta"
                  style={{ color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  title={`${s.dataset_id}${s.role ? ` · ${s.role}` : ''}`}
                >
                  {s.dataset_id}
                </span>
                <div style={{ position: 'relative', height: 9, background: 'var(--p-sunken)', border: '1px solid var(--rule)' }}>
                  {/* The usable intersection, so each bar is read against it. */}
                  <span
                    style={{
                      position: 'absolute', top: 0, bottom: 0,
                      left: `${pos(bounds!.usableFrom)}%`,
                      width: `${Math.max(0, pos(bounds!.usableTo) - pos(bounds!.usableFrom))}%`,
                      background: 'var(--ink-faint)', opacity: 0.14,
                    }}
                  />
                  <span
                    title={`${s.min_date} → ${s.max_date}, ${s.rows?.toLocaleString() ?? '—'} rows`}
                    style={{
                      position: 'absolute', top: 0, bottom: 0,
                      left: `${pos(from)}%`,
                      width: `${Math.max(0.6, pos(to) - pos(from))}%`,
                      background: pitState(s.point_in_time_status) === 'recorded' ? 'var(--s-recorded)' : 'var(--s-stale)',
                      opacity: 0.7,
                    }}
                  />
                </div>
                <span className="sys-num" style={{ fontSize: 'var(--t-micro)' }}>
                  {s.rows ? s.rows.toLocaleString() : '—'}
                </span>
              </div>
            )
          })}

          <div style={{ display: 'flex', gap: 'var(--d-4)', marginTop: 'var(--d-3)', flexWrap: 'wrap' }}>
            <span className="sys-meta"><span style={{ display: 'inline-block', width: 10, height: 6, background: 'var(--s-recorded)', opacity: 0.7, marginRight: 4 }} />point in time</span>
            <span className="sys-meta"><span style={{ display: 'inline-block', width: 10, height: 6, background: 'var(--s-stale)', opacity: 0.7, marginRight: 4 }} />not point in time</span>
            <span className="sys-meta"><span style={{ display: 'inline-block', width: 10, height: 6, background: 'var(--ink-faint)', opacity: 0.2, marginRight: 4 }} />usable intersection</span>
          </div>
        </div>
      </Panel>

      <Panel title="Sources" subtitle={undated ? `${undated} without a recorded range` : undefined} flush>
        <div className="sys-scroll-x">
          <table className="sys-table sys-table--compact">
            <thead>
              <tr>
                <th>Dataset</th><th>Role</th><th className="num">Rows</th><th className="num">Partitions</th>
                <th>From</th><th>To</th><th>Point in time</th><th>Survivorship</th><th>Retrieved</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={`${s.dataset_id}-${s.role ?? ''}`}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{s.dataset_id}</td>
                  <td>{s.role ?? '—'}</td>
                  <td className="num"><Value value={s.rows ?? null} digits={0} /></td>
                  <td className="num"><Value value={s.partitions ?? null} digits={0} /></td>
                  <td className="num">{s.min_date ?? <span className="sys-null">—</span>}</td>
                  <td className="num">{s.max_date ?? <span className="sys-null">—</span>}</td>
                  <td><Status state={pitState(s.point_in_time_status)} label={s.point_in_time_status ?? 'unknown'} /></td>
                  <td><span className="sys-meta sys-meta--strong">{s.survivorship_status ?? '—'}</span></td>
                  <td><span className="sys-meta sys-meta--strong">{s.retrieved_at?.slice(0, 10) ?? '—'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  )
}
