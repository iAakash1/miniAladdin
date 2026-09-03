/**
 * The object inspector.
 *
 * Opens over the current workspace rather than navigating away from it, so
 * following a reference does not cost the reader their place. Every kind of
 * object gets the same frame — identity, state, fields, neighbours, actions —
 * which is what makes the product feel like one system rather than eleven.
 *
 * Neighbours come from the declared object graph, not from the payload, so a
 * model always offers its experiment and its dataset even when the response
 * being inspected does not happen to mention them.
 */
'use client'

import { useEffect } from 'react'
import Link from 'next/link'

import { Status, type ResearchState } from './index'
import { recordVisit, togglePin, usePinnedObjects } from '@/lib/research/history'
import { KINDS, href as objectHref, neighbours, type ResearchObject } from '@/lib/research/objects'
import { Relations } from './Relations'

export interface InspectorField {
  label: string
  value: React.ReactNode
  /** Shown on hover: method, source, timestamp. */
  title?: string
}

export interface InspectorSection {
  title: string
  fields?: InspectorField[]
  body?: React.ReactNode
}

export default function Inspector({
  object, state, sections, onClose, actions,
}: {
  object: ResearchObject
  state?: ResearchState
  sections: InspectorSection[]
  onClose: () => void
  actions?: React.ReactNode
}) {
  const pinnedList = usePinnedObjects()

  useEffect(() => {
    recordVisit(object)
  }, [object])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const meta = KINDS[object.kind]
  const pinned = pinnedList.some((o) => o.kind === object.kind && o.id === object.id)

  return (
    <aside className="sys-drawer" role="dialog" aria-modal="false" aria-label={`${meta.plural} inspector`}>
      <header className="sys-drawer-head">
        <span className="pal-badge" aria-hidden>{meta.glyph}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="sys-lead" style={{ fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {object.label}
          </div>
          <div className="sys-meta">{meta.workspace}{object.detail ? ` · ${object.detail}` : ''}</div>
        </div>
        {state ? <Status state={state} /> : null}
        <button className="sys-btn" onClick={() => togglePin(object)} aria-pressed={pinned}>
          {pinned ? 'pinned' : 'pin'}
        </button>
        <button className="sys-btn" onClick={onClose} aria-label="Close inspector">esc</button>
      </header>

      <div className="sys-drawer-body">
        {sections.map((s) => (
          <section key={s.title}>
            <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>{s.title}</div>
            {s.fields?.length ? (
              <table className="sys-table sys-table--compact">
                <tbody>
                  {s.fields.map((f) => (
                    <tr key={f.label}>
                      <td style={{ width: '48%', color: 'var(--ink-muted)' }} title={f.title}>{f.label}</td>
                      <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal' }}>{f.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {s.body}
          </section>
        ))}

        <section>
          <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>Connected</div>
          {/* Counts from the artifacts, above the kinds from the pipeline. One
              says what this object actually touches; the other says what its
              kind can touch. Both are useful and they are not the same. */}
          <Relations object={object} />
        </section>

        <section>
          <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>Related kinds</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-1)' }}>
            {neighbours(object.kind).map((k) => (
              <Link key={k.kind} href={k.href('')} className="sys-btn" style={{ textDecoration: 'none' }}>
                {k.plural}
              </Link>
            ))}
          </div>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            Relations come from the research pipeline, not from this payload, so
            they are offered even when the response does not mention them.
          </p>
        </section>

        {actions ? (
          <section>
            <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>Actions</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-1)' }}>{actions}</div>
          </section>
        ) : null}

        <section>
          <Link href={objectHref(object)} className="sys-btn" style={{ textDecoration: 'none' }}>
            Open in {meta.workspace}
          </Link>
        </section>
      </div>
    </aside>
  )
}
