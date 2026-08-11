'use client'

import WorkBoot from '@/components/ui/WorkBoot'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

import PageHeader from '@/components/ui/PageHeader'
import EmptyState from '@/components/ui/EmptyState'
import { computeLayout, viewBoxFor, type LayoutNode } from '@/lib/graph/layout'
import { EDGE_LABELS } from '@/lib/knowledge'
import {
  addNote,
  captureSnapshot,
  createSession,
  emptyWorkspaceState,
  flushWorkspace,
  onSaveStateChange,
  openSession,
  recordActivity,
  updateWorkspace,
  type ResearchSession,
  type WorkspaceState,
} from '@/lib/sessions'

interface RawNode { id: string; type: string; label: string; route?: string | null; description?: string | null; metadata?: Record<string, string> }
interface RawEdge { source_id: string; target_id: string; type: string; confidence: number; provider: string; observed_at?: string }
interface Analytics {
  nodes: number; edges: number; density: number; avg_confidence: number
  node_types: Record<string, number>; edge_types: Record<string, number>
  provider_coverage: Record<string, number>
  most_connected: Array<{ id: string; label: string; type: string; degree: number }>
}
interface Workspace {
  roots: string[]; nodes: RawNode[]; edges: RawEdge[]; analytics: Analytics
  shared: Array<{ node: RawNode; connects_to: string[] }>
}

const TYPE_COLOR: Record<string, string> = {
  company: 'var(--accent)', person: 'var(--warn)', product: 'var(--pos)',
  subsidiary: 'var(--muted)', industry: 'var(--muted)', technology: 'var(--pos)',
  country: 'var(--faint)', exchange: 'var(--faint)',
}
const color = (type: string) => TYPE_COLOR[type] ?? 'var(--muted)'

/**
 * Knowledge Graph Workspace — the graph as the primary interface.
 *
 * Layout is deterministic (lib/graph/layout), so the same companies always
 * render identically and users build spatial memory. All traversal,
 * filtering and analytics happen server-side in the graph API; this
 * component renders, selects and explains. State lives in the URL, so any
 * workspace is a shareable address.
 */
export default function GraphWorkspace() {
  const router = useRouter()
  const params = useSearchParams()

  const symbols = (params.get('symbols') || 'NVDA').toUpperCase()
  const hops = Number(params.get('hops') || '2')
  const typeFilter = params.get('types') || ''
  const minConfidence = params.get('minconf') || ''
  const before = params.get('before') || ''

  const sessionId = params.get('session') || ''
  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [pinned, setPinned] = useState<string[]>([])
  const [session, setSession] = useState<ResearchSession | null>(null)
  const [state, setState] = useState<WorkspaceState>(emptyWorkspaceState())
  const [saving, setSaving] = useState(false)
  const [noteDraft, setNoteDraft] = useState('')
  /* Right-click target. The inspector already carries these actions, but it
     lives in a side panel — on a dense graph that is a round trip across the
     screen for every node you want to try. The menu puts the same actions
     (no new ones, no fabricated relationships) at the cursor. */
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null)

  useEffect(() => onSaveStateChange(setSaving), [])

  useEffect(() => {
    if (!menu) return undefined
    const close = () => setMenu(null)
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenu(null) }
    // `click` rather than `mousedown` so the menu's own buttons fire first.
    window.addEventListener('click', close)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [menu])

  /* Restore: opening a session rebuilds the exact workspace it was left in. */
  useEffect(() => {
    if (!sessionId) return
    let alive = true
    openSession(sessionId).then((loaded) => {
      if (!alive || !loaded) return
      setSession(loaded)
      setState(loaded.workspace_state)
      setPinned(loaded.workspace_state.pinned)
      setSelected(loaded.workspace_state.selected)
      // Restore the graph the session was viewing.
      const stored = loaded.workspace_state.symbols.join(',')
      if (stored && stored !== symbols) {
        const next = new URLSearchParams(params.toString())
        next.set('symbols', stored)
        next.set('hops', String(loaded.workspace_state.filters.hops))
        router.replace(`/terminal/graph?${next}`)
      }
    })
    return () => { alive = false }
    // Restore runs once per session id — later state changes are saves, not loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  /* Autosave: every workspace mutation persists, debounced. Users never save. */
  const persist = useCallback((mutate: (current: WorkspaceState) => WorkspaceState) => {
    setState((current) => {
      const next = mutate(current)
      if (sessionId) updateWorkspace(sessionId, next)
      return next
    })
  }, [sessionId])

  /* Keep the graph view in the session state as the user navigates. */
  useEffect(() => {
    if (!sessionId) return
    persist((current) => ({
      ...current,
      symbols: symbols.split(',').filter(Boolean),
      selected,
      pinned,
      filters: { ...current.filters, hops, node_types: typeFilter },
    }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, symbols, hops, typeFilter, selected, pinned])

  /* A pending save must not be lost when the tab closes. */
  useEffect(() => {
    const onLeave = () => { void flushWorkspace() }
    window.addEventListener('pagehide', onLeave)
    return () => {
      window.removeEventListener('pagehide', onLeave)
      void flushWorkspace()
    }
  }, [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    const query = new URLSearchParams({ symbols, hops: String(hops) })
    if (typeFilter) query.set('node_types', typeFilter)
    if (minConfidence) query.set('min_confidence', minConfidence)
    if (before) query.set('before', before)
    fetch(`/api/graph/workspace?${query}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((json: Workspace | null) => {
        if (!alive) return
        setData(json)
        setSelected(json?.roots[0] ?? null)
        setLoading(false)
      })
      .catch(() => alive && setLoading(false))
    return () => { alive = false }
  }, [symbols, hops, typeFilter, minConfidence, before])

  const setParam = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString())
    if (value) next.set(key, value)
    else next.delete(key)
    router.push(`/terminal/graph?${next}`)
  }, [params, router])

  const layout = useMemo(
    () => data ? computeLayout({ nodes: data.nodes, edges: data.edges, roots: data.roots }) : null,
    [data],
  )

  /* Everything the selection actually touches. Used to dim the rest — the
     graph answers "what does this connect to?" by removing the noise rather
     than by making one node bigger. Derived from real edges only, so a node
     with no recorded relationships correctly leaves everything dimmed. */
  const related = useMemo(() => {
    if (!selected || !data) return null
    const ids = new Set<string>([selected])
    for (const edge of data.edges) {
      if (edge.source_id === selected) ids.add(edge.target_id)
      else if (edge.target_id === selected) ids.add(edge.source_id)
    }
    return ids
  }, [selected, data])

  const selectedNode = data?.nodes.find((n) => n.id === selected) ?? null
  const selectedEdges = (data?.edges ?? []).filter(
    (e) => e.source_id === selected || e.target_id === selected,
  )
  const nodeById = new Map((data?.nodes ?? []).map((n) => [n.id, n]))

  const togglePin = (id: string) => {
    setPinned((current) => current.includes(id) ? current.filter((p) => p !== id) : [...current, id])
    persist((current) => recordActivity(current, 'pin', id))
  }

  const startSession = async () => {
    const created = await createSession(
      `${symbols} investigation`, undefined, [],
      { ...emptyWorkspaceState(), symbols: symbols.split(',').filter(Boolean) },
    )
    if (created) {
      const next = new URLSearchParams(params.toString())
      next.set('session', created.id)
      router.push(`/terminal/graph?${next}`)
    }
  }

  const saveNote = async () => {
    if (!sessionId || !noteDraft.trim()) return
    const refs = selected ? [{ type: 'entity', id: selected }] : []
    const note = await addNote(sessionId, noteDraft.trim(), refs)
    if (note) {
      setSession((current) => current ? { ...current, notes: [note, ...current.notes] } : current)
      setNoteDraft('')
      persist((current) => recordActivity(current, 'note', note.body.slice(0, 60)))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <PageHeader
          eyebrow="Workspace"
          title="Knowledge graph"
          lede="Every entity and relationship OmniSignal knows, from SEC filings and Wikidata. Compare companies to see what they share, or trace how any two entities connect. Nothing here is inferred — every edge names the provider that asserted it and the confidence it carries."
        />
      </div>

      {/* Session bar: the investigation this workspace belongs to */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        {session ? (
          <>
            <span className="badge badge--accent">{session.title}</span>
            <span className="u-meta">
              {saving ? 'Saving…' : 'All changes saved'}
            </span>
            <button type="button" className="btn btn--ghost btn--xs"
                    style={{ border: '1px solid var(--line)' }}
                    onClick={() => persist((current) => captureSnapshot(current, `${symbols} view`))}>
              Snapshot ({state.snapshots.length})
            </button>
            <Link href="/terminal/sessions" className="btn btn--ghost btn--xs"
                  style={{ border: '1px solid var(--line)', textDecoration: 'none' }}>
              All investigations
            </Link>
          </>
        ) : (
          <>
            <span className="u-note">
              Not in a session — pins and notes won&apos;t be saved.
            </span>
            <button type="button" className="btn btn--secondary btn--xs" onClick={startSession}>
              Start investigation
            </button>
            <Link href="/terminal/sessions" className="btn btn--ghost btn--xs"
                  style={{ border: '1px solid var(--line)', textDecoration: 'none' }}>
              Open existing
            </Link>
          </>
        )}
      </div>

      {/* Controls: symbols, depth, filters, time machine */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <label htmlFor="ws-symbols" className="visually-hidden">Tickers to compare</label>
        <input
          id="ws-symbols"
          className="input mono"
          defaultValue={symbols}
          placeholder="NVDA,MSFT"
          style={{ maxWidth: 190, height: 32, fontSize: '0.8125rem', letterSpacing: '0.05em' }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') setParam('symbols', (e.target as HTMLInputElement).value.toUpperCase())
          }}
        />
        <div className="seg" role="group" aria-label="Graph depth">
          {[1, 2, 3].map((h) => (
            <button key={h} type="button" className="seg__btn num" aria-pressed={hops === h}
                    onClick={() => setParam('hops', String(h))}>
              {h} hop{h > 1 ? 's' : ''}
            </button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Filter by entity type">
          {[['', 'All'], ['company', 'Companies'], ['person', 'People'], ['product', 'Products']].map(([value, label]) => (
            <button key={value} type="button" className="seg__btn" aria-pressed={typeFilter === value}
                    onClick={() => setParam('types', value)}>
              {label}
            </button>
          ))}
        </div>
        {/* Filters by when OmniSignal OBSERVED a relationship, not when the
            relationship began — Wikidata edges carry no start date, so this
            cannot reconstruct history. Labelled for what it actually does. */}
        <label htmlFor="ws-before" className="label" style={{ fontSize: '0.625rem' }}>Observed before</label>
        <input
          id="ws-before" type="date" className="input num" defaultValue={before}
          title="Shows only relationships OmniSignal recorded before this date. Not a historical reconstruction — providers do not supply relationship start dates."
          style={{ maxWidth: 150, height: 32, fontSize: '0.75rem' }}
          onChange={(e) => setParam('before', e.target.value)}
        />
      </div>

      <div className="terminal-grid-main">
        {/* Graph */}
        <section aria-label="Graph" className="panel" style={{ padding: 14 }}>
          {loading ? (
            <WorkBoot
              compact
              label="Building the graph"
              hint="entities and relationships from SEC filings and Wikidata"
            />
          ) : !layout || layout.nodes.length === 0 ? (
            <EmptyState
              title={`No relationships recorded for ${symbols}`}
              description="The graph is assembled from SEC filings and Wikidata, which cover large US issuers best. Nothing is inferred, so a company with no filed or catalogued relationships shows an empty graph rather than a guessed one."
              action={
                symbols !== 'NVDA' ? (
                  <button
                    type="button"
                    className="btn btn--secondary btn--sm"
                    onClick={() => {
                      const next = new URLSearchParams(params.toString())
                      next.set('symbols', 'NVDA')
                      router.replace(`/terminal/graph?${next}`)
                    }}
                  >
                    Open a populated example
                  </button>
                ) : undefined
              }
            />
          ) : (
            <svg
              viewBox={viewBoxFor(layout)}
              role="application"
              className={`gfocus${related ? ' is-focusing' : ''}`}
              aria-label={`Knowledge graph for ${symbols}`}
              style={{ width: '100%', height: 'auto', maxHeight: 520 }}
            >
              {layout.edges.map((edge, i) => {
                const active = edge.source === selected || edge.target === selected
                return (
                  <line
                    key={`${edge.source}-${edge.target}-${i}`}
                    className={`gfocus__edge${active ? ' is-related' : ''}`}
                    x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2}
                    // `--line` is the hairline token for dividers sitting
                    // against an adjacent surface; at 8% white, times a 0.55
                    // opacity, an edge crossing open canvas came out around
                    // 4% and was invisible. It only ever looked drawn because
                    // the old layout packed every neighbour into a tight
                    // starburst where the lines overlapped. Matches
                    // GraphExplorer, which already used the stronger token.
                    stroke={active ? 'var(--accent)' : 'var(--line-strong)'}
                    strokeWidth={active ? 1.8 : 1}
                    opacity={active ? 1 : 0.75}
                  />
                )
              })}
              {layout.nodes.map((node: LayoutNode) => {
                const isSelected = node.id === selected
                const isPinned = pinned.includes(node.id)
                const isRoot = data?.roots.includes(node.id)
                const radius = isRoot ? 9 : Math.min(7, 3 + node.degree * 0.35)
                return (
                  <g key={node.id} transform={`translate(${node.x},${node.y})`}
                     className={`gfocus__node${!related || related.has(node.id) ? ' is-related' : ''}`}
                     tabIndex={0}
                     role="button"
                     aria-pressed={isSelected}
                     aria-label={`${node.label} — ${node.type}`}
                     onKeyDown={(e) => {
                       if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(node.id) }
                       if (e.key === 'Escape') setSelected(null)
                     }}
                     onClick={() => setSelected(node.id)}
                     onContextMenu={(event) => {
                       event.preventDefault()
                       setSelected(node.id)
                       setMenu({ id: node.id, x: event.clientX, y: event.clientY })
                     }}
                     style={{ cursor: 'pointer' }}>
                    {isPinned && <circle r={radius + 4} fill="none" stroke="var(--warn)" strokeWidth={1.2} />}
                    <circle r={radius} fill={color(node.type)}
                            opacity={isSelected ? 1 : 0.85}
                            stroke={isSelected ? 'var(--text)' : 'none'} strokeWidth={1.5} />
                    {(isRoot || isSelected || node.degree > 3 || node.depth <= 1) && (
                      <text y={-radius - 5} textAnchor="middle"
                            style={{ fontSize: isRoot ? 11 : 9,
                                     fontWeight: isRoot || isSelected ? 600 : 400,
                                     fill: isSelected ? 'var(--text)' : 'var(--muted)' }}>
                        {node.label.length > 20 ? `${node.label.slice(0, 19)}…` : node.label}
                      </text>
                    )}
                  </g>
                )
              })}
            </svg>
                )}
          {menu && (() => {
            const node = nodeById.get(menu.id)
            if (!node) return null
            const isPinned = pinned.includes(menu.id)
            return (
              <div
                className="ctxmenu"
                role="menu"
                aria-label={`Actions for ${node.label}`}
                style={{ left: menu.x, top: menu.y }}
                onClick={(event) => event.stopPropagation()}
              >
                <p className="ctxmenu__head">{node.label}</p>
                <button type="button" role="menuitem" className="ctxmenu__item"
                        onClick={() => { togglePin(menu.id); setMenu(null) }}>
                  {isPinned ? 'Unpin' : 'Pin to workspace'}
                </button>
                {node.route && (
                  <Link role="menuitem" className="ctxmenu__item" href={node.route}
                        onClick={() => setMenu(null)}>
                    Open research
                  </Link>
                )}
                <button type="button" role="menuitem" className="ctxmenu__item"
                        onClick={() => { setParam('symbols', menu.id.split(':')[1] ?? ''); setMenu(null) }}
                        disabled={node.type !== 'company'}>
                  Centre the graph here
                </button>
              </div>
            )
          })()}
          {data && (
            <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 8 }}>
              {data.analytics.nodes} entities · {data.analytics.edges} relationships ·
              density {data.analytics.density} · avg confidence {data.analytics.avg_confidence}
            </p>
          )}
        </section>

        {/* Inspector */}
        <section aria-label="Inspector" className="panel panel--pad">
          {selectedNode ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <p className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>{selectedNode.type}</p>
                <p style={{ fontSize: '1rem', fontWeight: 600 }}>{selectedNode.label}</p>
                {selectedNode.description && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: 4 }}>{selectedNode.description}</p>
                )}
              </div>

              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn--ghost btn--xs"
                        style={{ border: '1px solid var(--line)' }}
                        onClick={() => togglePin(selectedNode.id)}>
                  {pinned.includes(selectedNode.id) ? 'Unpin' : 'Pin'}
                </button>
                {selectedNode.route?.startsWith('/company/') && (
                  <Link href={selectedNode.route} className="btn btn--ghost btn--xs"
                        style={{ border: '1px solid var(--line)', textDecoration: 'none' }}>
                    Open report
                  </Link>
                )}
              </div>

              <div>
                <p className="label" style={{ fontSize: '0.625rem', marginBottom: 6 }}>
                  Relationships ({selectedEdges.length})
                </p>
                <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 240, overflowY: 'auto' }}>
                  {selectedEdges.slice(0, 24).map((edge, i) => {
                    const otherId = edge.source_id === selected ? edge.target_id : edge.source_id
                    const other = nodeById.get(otherId)
                    if (!other) return null
                    return (
                      <li key={`${otherId}-${i}`} style={{ fontSize: '0.75rem' }}>
                        <button type="button" onClick={() => setSelected(otherId)}
                                style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', color: 'var(--text)', fontWeight: 550 }}>
                          {other.label}
                        </button>
                        <span style={{ color: 'var(--faint)' }}>
                          {' · '}{EDGE_LABELS[edge.type] ?? edge.type}
                          {' · '}{edge.provider}
                          {' · '}{edge.confidence.toFixed(2)}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </div>
          ) : (
            <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>Select a node to inspect it.</p>
          )}

          {/* Multi-select: what the compared companies share */}
          {data && data.shared.length > 0 && (
            <div className="hairline-top" style={{ marginTop: 14, paddingTop: 12 }}>
              <p className="label" style={{ fontSize: '0.625rem', marginBottom: 8 }}>
                Shared by all selected companies
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {data.shared.slice(0, 12).map((row) => (
                  <button key={row.node.id} type="button" className="btn btn--ghost btn--xs"
                          style={{ border: '1px solid var(--line)' }}
                          onClick={() => setSelected(row.node.id)}>
                    {row.node.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Analytics */}
          {data && data.analytics.most_connected.length > 0 && (
            <details className="disclosure" style={{ marginTop: 14 }}>
              <summary style={{ fontSize: '0.75rem', fontWeight: 550, color: 'var(--muted)' }}>
                Graph analytics
              </summary>
              <div style={{ marginTop: 10 }}>
                <p className="label" style={{ fontSize: '0.625rem', marginBottom: 6 }}>Most connected</p>
                <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {data.analytics.most_connected.slice(0, 6).map((row) => (
                    <li key={row.id} className="u-note">
                      <button type="button" onClick={() => setSelected(row.id)}
                              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text)' }}>
                        {row.label}
                      </button>
                      <span className="num" style={{ color: 'var(--faint)' }}> · {row.degree} links</span>
                    </li>
                  ))}
                </ul>
                <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 8 }}>
                  Providers: {Object.entries(data.analytics.provider_coverage).map(([p, n]) => `${p} ${n}`).join(' · ')}
                </p>
              </div>
            </details>
          )}
        </section>
      </div>

      {/* Notebook — belongs to the session, references what is selected */}
      {session && (
        <section aria-label="Research notebook" className="panel panel--pad">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <h3 className="h-panel" style={{ fontSize: '0.875rem' }}>Notebook</h3>
            <span className="u-meta">
              {session.notes.length} note{session.notes.length === 1 ? '' : 's'}
              {selected ? ` · will reference ${selected.split(':')[1] ?? selected}` : ''}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <label htmlFor="note-draft" className="visually-hidden">New note</label>
            <input id="note-draft" className="input" value={noteDraft}
                   placeholder="Record a finding…"
                   style={{ height: 32, fontSize: '0.8125rem' }}
                   onChange={(e) => setNoteDraft(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter') void saveNote() }} />
            <button type="button" className="btn btn--secondary btn--sm"
                    disabled={!noteDraft.trim()} onClick={() => void saveNote()}>
              Add
            </button>
          </div>
          {session.notes.length > 0 && (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {session.notes.slice(0, 8).map((note) => (
                <li key={note.id} style={{ fontSize: '0.8125rem', lineHeight: 1.5 }}>
                  <span style={{ color: 'var(--text)' }}>{note.body}</span>
                  {note.refs.length > 0 && (
 <span className="num u-meta" >
                      {' · '}{note.refs.map((r) => r.id.split(':')[1] ?? r.id).join(', ')}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {pinned.length > 0 && (
        <p className="u-meta">
          Pinned: {pinned.map((id) => nodeById.get(id)?.label ?? id).join(' · ')}
        </p>
      )}
    </div>
  )
}
