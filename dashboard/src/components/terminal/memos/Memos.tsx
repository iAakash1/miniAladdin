/**
 * Research notebook.
 *
 * Four fields, in the order a claim has to be made: thesis, evidence, risks,
 * conclusion. Evidence before conclusion is the whole structure — a memo that
 * states its conclusion first is an opinion looking for support.
 *
 * References are attached from the object catalogue, so a claim points at the
 * experiment or gate it rests on rather than naming it in prose that no later
 * reader can follow back.
 *
 * Nothing here is generated. Every word is the reader's.
 */
'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'

import { Panel, Prose, StateBlock, Strip } from '@/components/system'
import { ObjectHeader, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'
import { addReference, createMemo, deleteMemo, removeReference, updateMemo, useMemos, type Memo } from '@/lib/research/memos'
import { usePinnedObjects, useRecentObjects } from '@/lib/research/history'
import { KINDS, href as objectHref, type ResearchObject } from '@/lib/research/objects'

const FIELDS: { key: keyof Pick<Memo, 'thesis' | 'evidence' | 'risks' | 'conclusion'>; label: string; hint: string; rows: number }[] = [
  { key: 'thesis', label: 'Thesis', hint: 'What you think is true, stated so it could be wrong.', rows: 3 },
  { key: 'evidence', label: 'Evidence', hint: 'What supports it, and how strong that support is.', rows: 5 },
  { key: 'risks', label: 'Risks', hint: 'What would make this wrong. A memo with none has not been examined.', rows: 4 },
  { key: 'conclusion', label: 'Conclusion', hint: 'What follows, and what would change it.', rows: 3 },
]

export default function Memos({ initialId }: { initialId?: string }) {
  const all = useMemos()
  const recent = useRecentObjects()
  const pinned = usePinnedObjects()
  const [selectedId, setSelectedId] = useState<string | null>(initialId ?? null)
  const [editing, setEditing] = useState(false)

  const selected = useMemo(
    () => all.find((m) => m.id === selectedId) ?? all[0] ?? null,
    [all, selectedId],
  )

  const attachable = useMemo(() => {
    const seen = new Set<string>()
    const out: ResearchObject[] = []
    for (const o of [...pinned, ...recent]) {
      const k = `${o.kind}:${o.id}`
      if (seen.has(k)) continue
      seen.add(k)
      out.push(o)
    }
    return out.slice(0, 12)
  }, [pinned, recent])

  return (
    <>
      <ObjectHeader
        glyph="N"
        name="Memos"
        kind="what you concluded, and what it rests on"
        state="recorded"
        detail="stored in this browser only"
        facts={[
          { label: 'Memos', value: all.length, digits: 0 , kind: 'count'},
          { label: 'Drafts', value: all.filter((m) => m.status === 'draft').length, digits: 0 },
          { label: 'Open', value: all.filter((m) => m.status === 'open').length, digits: 0 },
          { label: 'Resolved', value: all.filter((m) => m.status === 'resolved').length, digits: 0 },
          { label: 'References', value: all.reduce((s, m) => s + m.references.length, 0), digits: 0 },
        ]}
      />

      <Strip metrics={[
        { label: 'Memos', value: all.length, digits: 0 , kind: 'count'},
        { label: 'Drafts', value: all.filter((m) => m.status === 'draft').length, digits: 0 },
        { label: 'Open', value: all.filter((m) => m.status === 'open').length, digits: 0 },
        { label: 'Resolved', value: all.filter((m) => m.status === 'resolved').length, digits: 0 },
        { label: 'References', value: all.reduce((s, m) => s + m.references.length, 0), digits: 0 },
      ]} />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/evidence" className="sys-btn" style={{ textDecoration: 'none' }}>evidence</Link>
          <Link href="/terminal/experiments" className="sys-btn" style={{ textDecoration: 'none' }}>experiments</Link>
          <Link href="/terminal/timeline" className="sys-btn" style={{ textDecoration: 'none' }}>timeline</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">stored in this browser only</span>
      </Toolbar>

      <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(220px, 300px) minmax(0, 1fr)', alignItems: 'start' }}>
        <Panel
          title="Notebook"
          subtitle={`${all.length} memos`}
          flush
          actions={
            <button
              className="sys-btn"
              onClick={() => { const m = createMemo(); setSelectedId(m.id); setEditing(true) }}
            >
              new
            </button>
          }
        >
          {all.length === 0 ? (
            <StateBlock
              state="unknown"
              title="No memos yet"
              detail="A memo records a claim and what it rests on, so a later reader can check whether the evidence still says the same thing."
            />
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {all.map((m) => (
                <li key={m.id}>
                  <button
                    className={`pal-row${selected?.id === m.id ? ' is-active' : ''}`}
                    style={{ height: 'auto', padding: 'var(--d-2) var(--d-3)', alignItems: 'flex-start', flexDirection: 'column', gap: 2 }}
                    onClick={() => { setSelectedId(m.id); setEditing(false) }}
                  >
                    <span style={{ fontSize: 'var(--t-body)', color: 'var(--ink)' }}>{m.title || 'Untitled'}</span>
                    <span className="sys-meta">
                      {m.status} · {m.references.length} refs · {new Date(m.updatedAt).toISOString().slice(0, 10)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {selected ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--d-4)', minWidth: 0 }}>
            <Panel
              title="Memo"
              subtitle={new Date(selected.updatedAt).toISOString().slice(0, 16).replace('T', ' ')}
              state={selected.status === 'resolved' ? 'recorded' : selected.status === 'open' ? 'experimental' : 'unknown'}
              actions={
                <div style={{ display: 'flex', gap: 'var(--d-1)' }}>
                  <div className="sys-seg">
                    {(['draft', 'open', 'resolved'] as const).map((s) => (
                      <button key={s} className="sys-btn" aria-pressed={selected.status === s} onClick={() => updateMemo(selected.id, { status: s })}>{s}</button>
                    ))}
                  </div>
                  <button className="sys-btn" aria-pressed={editing} onClick={() => setEditing((v) => !v)}>{editing ? 'read' : 'edit'}</button>
                  <button className="sys-btn" onClick={() => { deleteMemo(selected.id); setSelectedId(null) }}>delete</button>
                </div>
              }
            >
              {editing ? (
                <input
                  className="sys-input"
                  style={{ width: '100%', fontSize: 'var(--t-lead)', fontFamily: 'var(--font-sans)', marginBottom: 'var(--d-3)' }}
                  value={selected.title}
                  onChange={(e) => updateMemo(selected.id, { title: e.target.value })}
                  placeholder="Title"
                  aria-label="Memo title"
                />
              ) : (
                <h2 className="sys-lead" style={{ margin: '0 0 var(--d-3)' }}>{selected.title || 'Untitled'}</h2>
              )}

              {FIELDS.map((f) => (
                <section key={f.key} style={{ marginBottom: 'var(--d-4)' }}>
                  <div className="sys-label" style={{ marginBottom: 'var(--d-1)' }}>{f.label}</div>
                  {editing ? (
                    <>
                      <textarea
                        className="sys-input"
                        style={{ width: '100%', resize: 'vertical', fontFamily: 'var(--font-sans)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)' }}
                        rows={f.rows}
                        value={selected[f.key]}
                        onChange={(e) => updateMemo(selected.id, { [f.key]: e.target.value })}
                        placeholder={f.hint}
                        aria-label={f.label}
                      />
                      <p style={{ margin: '2px 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)' }}>{f.hint}</p>
                    </>
                  ) : selected[f.key] ? (
                    <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink)', whiteSpace: 'pre-wrap', maxWidth: '78ch' }}>
                      {selected[f.key]}
                    </p>
                  ) : (
                    <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-faint)' }}>—</p>
                  )}
                </section>
              ))}
            </Panel>

            <Panel title="References" subtitle={`${selected.references.length} attached`}>
              {selected.references.length ? (
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {selected.references.map((r) => (
                      <tr key={`${r.kind}:${r.id}`}>
                        <td style={{ width: 28 }}><span className="pal-badge">{KINDS[r.kind].glyph}</span></td>
                        <td>
                          <Link href={objectHref(r)} style={{ color: 'inherit', fontFamily: 'var(--font-mono)' }}>{r.label}</Link>
                        </td>
                        <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{KINDS[r.kind].workspace}</span></td>
                        <td className="num">
                          <button className="sys-btn" onClick={() => removeReference(selected.id, r)}>remove</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '78ch' }}>
                  Nothing attached. A claim that names its evidence in prose cannot be
                  followed back; a claim that points at the experiment can.
                </p>
              )}

              {attachable.length ? (
                <div style={{ marginTop: 'var(--d-3)' }}>
                  <div className="sys-label" style={{ marginBottom: 'var(--d-1)' }}>Attach from recent and pinned</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-1)' }}>
                    {attachable.map((o) => (
                      <button
                        key={`${o.kind}:${o.id}`}
                        className="sys-btn"
                        onClick={() => addReference(selected.id, o)}
                        title={`${KINDS[o.kind].plural} · ${o.detail ?? ''}`}
                      >
                        {KINDS[o.kind].glyph} {o.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)' }}>
                  Open an object anywhere in the product and it becomes attachable here.
                </p>
              )}
            </Panel>

            <Panel title="Where these are stored">
              <Prose size="tight">
                In this browser only. There is no memo backend, and presenting a
                local notebook as shared storage would be a claim the product
                cannot honour. Clearing site data clears these.
              </Prose>
            </Panel>
          </div>
        ) : (
          <Panel title="Memo">
            <StateBlock state="unknown" title="No memo selected" detail="Create one, or choose from the notebook." />
          </Panel>
        )}
      </div>
    </>
  )
}
