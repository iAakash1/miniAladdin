/**
 * Research timeline.
 *
 * Built only from timestamps that were actually recorded — registry
 * registrations and status changes, and locally written memos. Nothing is
 * inferred and no event is synthesised to fill a quiet stretch, so a sparse
 * timeline is a true statement that little was recorded rather than a gap the
 * display papered over.
 *
 * Events are grouped by day and ordered newest first, because the question a
 * timeline answers is what happened recently, not what happened first.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import { Panel, Prose, StateBlock, Status, Strip, type ResearchState } from '@/components/system'
import { ObjectHeader, StripSkeleton, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'
import { useMemos } from '@/lib/research/memos'
import { KINDS, href as objectHref, type ObjectKind } from '@/lib/research/objects'

interface Entry {
  key: string
  model_id: string
  label: string
  status: string
  created_at?: string
  updated_at?: string
  /**
   * A recorded transition, in the registry's own shape: where the model moved
   * from, where it moved to, when, and why.
   *
   * This was declared as `{ status, note }`, which no row carries. Every
   * transition rendered as "status → undefined" with no reason and the wrong
   * state colour — well-formed markup describing nothing, on the one workspace
   * whose entire job is to say what happened.
   */
  status_history?: { at?: string; from?: string; to?: string; reason?: string }[]
}

interface Event {
  at: string
  kind: ObjectKind
  id: string
  label: string
  what: string
  detail?: string
  state: ResearchState
}

function statusState(status: string): ResearchState {
  switch (status) {
    case 'production': return 'production'
    case 'production_candidate':
    case 'validated': return 'candidate'
    case 'retired': return 'unavailable'
    default: return 'experimental'
  }
}

export default function ResearchTimeline() {
  const [entries, setEntries] = useState<Entry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [kinds, setKinds] = useState<Set<ObjectKind>>(new Set())
  const localMemos = useMemos()

  useEffect(() => {
    let alive = true
    fetch('/api/ml/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setEntries(d.entries ?? []) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const events = useMemo(() => {
    const out: Event[] = []

    for (const e of entries ?? []) {
      if (e.created_at) {
        out.push({
          at: e.created_at, kind: 'model', id: e.model_id, label: e.model_id,
          what: 'registered', detail: e.label, state: statusState(e.status),
        })
      }
      // A status change is only an event when it actually differs from the
      // registration; otherwise the two timestamps describe one act.
      if (e.updated_at && e.created_at && e.updated_at !== e.created_at) {
        out.push({
          at: e.updated_at, kind: 'model', id: e.model_id, label: e.model_id,
          what: `updated · ${e.status}`, detail: e.label, state: statusState(e.status),
        })
      }
      for (const h of e.status_history ?? []) {
        if (!h.at || !h.to) continue
        out.push({
          at: h.at, kind: 'model', id: e.model_id, label: e.model_id,
          // Both ends of the transition. "retired" alone does not say what it
          // was retired from, and a move out of production is a different
          // event from a move out of experimental.
          what: h.from ? `${h.from} → ${h.to}` : `→ ${h.to}`,
          detail: h.reason,
          state: statusState(h.to),
        })
      }
    }

    for (const m of localMemos) {
      out.push({
        at: new Date(m.createdAt).toISOString(), kind: 'memo', id: m.id,
        label: m.title || 'Untitled memo', what: 'memo written',
        detail: `${m.references.length} references`, state: 'recorded',
      })
    }

    return out.sort((a, b) => b.at.localeCompare(a.at))
  }, [entries, localMemos])

  const filtered = useMemo(
    () => (kinds.size === 0 ? events : events.filter((e) => kinds.has(e.kind))),
    [events, kinds],
  )

  const byDay = useMemo(() => {
    const map = new Map<string, Event[]>()
    for (const e of filtered) {
      const day = e.at.slice(0, 10)
      const list = map.get(day) ?? []
      list.push(e)
      map.set(day, list)
    }
    return [...map.entries()]
  }, [filtered])

  const present = useMemo(() => [...new Set(events.map((e) => e.kind))], [events])

  if (error) return <Panel title="Timeline" state="unavailable"><StateBlock state="unavailable" title="The registry could not be read" detail={error} /></Panel>
  if (!entries) {
    return (
      <>
        <StripSkeleton />
        <Panel title="Timeline" state="waking" flush><TableSkeleton rows={10} columns={4} /></Panel>
      </>
    )
  }

  return (
    <>
      <ObjectHeader
        glyph="│"
        name="Timeline"
        kind="what was recorded, and when"
        state="recorded"
        detail={events.length ? `${events[events.length - 1].at.slice(0, 10)} → ${events[0].at.slice(0, 10)}` : undefined}
        facts={[
          { label: 'Events', value: events.length, digits: 0 , kind: 'count'},
          { label: 'Days', value: byDay.length, digits: 0, kind: 'count' },
          { label: 'Registrations', value: events.filter((e) => e.what === 'registered').length, digits: 0, kind: 'count' },
          { label: 'Memos', value: localMemos.length, digits: 0 , kind: 'count'},
        ]}
      />

      <Strip metrics={[
        { label: 'Models registered', value: events.filter((e) => e.what === 'registered').length, digits: 0, kind: 'count' },
        { label: 'First', value: events.length ? events[events.length - 1].at.slice(0, 10) : null, digits: 0, kind: 'count' },
        { label: 'Last', value: events.length ? events[0].at.slice(0, 10) : null, digits: 0, kind: 'count' },
      ]} />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/evidence" className="sys-btn">registry</Link>
          <Link href="/terminal/experiments" className="sys-btn">experiments</Link>
          <Link href="/terminal/memos" className="sys-btn">memos</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">recorded timestamps only</span>
      </Toolbar>

      <Panel
        title="Timeline"
        subtitle={`${filtered.length} of ${events.length} events`}
        flush
        actions={
          <div style={{ display: 'flex', gap: 'var(--d-1)' }}>
            {present.map((k) => (
              <button
                key={k}
                className="sys-btn"
                aria-pressed={kinds.has(k)}
                onClick={() => setKinds((prev) => {
                  const next = new Set(prev)
                  if (next.has(k)) next.delete(k)
                  else next.add(k)
                  return next
                })}
              >
                {KINDS[k].plural}
              </button>
            ))}
            {kinds.size ? <button className="sys-btn" onClick={() => setKinds(new Set())}>all</button> : null}
          </div>
        }
      >
        {byDay.length === 0 ? (
          <StateBlock
            state="unavailable"
            title="No events"
            detail="Nothing recorded a timestamp for the selected kinds. No event is synthesised to fill the gap."
          />
        ) : (
          <div style={{ padding: 'var(--d-3)' }}>
            {byDay.map(([day, list]) => (
              <section key={day} style={{ marginBottom: 'var(--d-4)' }}>
                <div className="sys-label" style={{ marginBottom: 'var(--d-2)', position: 'sticky', top: 0, background: 'var(--p-panel)', paddingBottom: 2 }}>
                  {day} <span className="sys-meta" style={{ marginLeft: 6 }}>{list.length} events</span>
                </div>
                <ol className="lin">
                  {list.map((e, i) => (
                    <li className="lin-row" key={`${e.at}-${e.id}-${i}`}>
                      <div className="lin-spine" aria-hidden>
                        <span className="lin-dot" />
                        {i < list.length - 1 ? <span className="lin-line" /> : null}
                      </div>
                      <div className="lin-body" style={{ paddingBottom: 'var(--d-3)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--d-2)', flexWrap: 'wrap' }}>
                          <span className="sys-meta">{e.at.slice(11, 19)}</span>
                          <span className="pal-badge" aria-hidden>{KINDS[e.kind].glyph}</span>
                          <Link
                            href={objectHref({ kind: e.kind, id: e.id, label: e.label })}
                            style={{ color: 'inherit', fontFamily: 'var(--font-mono)', fontSize: 'var(--t-body)' }}
                          >
                            {e.label}
                          </Link>
                          <span className="sys-meta sys-meta--strong">{e.what}</span>
                          <Status state={e.state} />
                        </div>
                        {e.detail ? <p className="lin-detail">{e.detail}</p> : null}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="What is and is not here">
        <Prose>
          Only timestamps that were actually recorded: model registrations, status
          changes where the registry captured one, and memos written in this
          browser. Experiment runs, data ingestions and backtests do not all carry
          an event timestamp in the artifacts, so they are absent rather than
          reconstructed from file modification times — an inferred timestamp on a
          research record is a fact the record does not contain.
        </Prose>
      </Panel>
    </>
  )
}
