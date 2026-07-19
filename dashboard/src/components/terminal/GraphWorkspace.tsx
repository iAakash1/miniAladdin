'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { computeLayout, viewBoxFor, type LayoutNode } from '@/lib/graph/layout'
import { EDGE_LABELS } from '@/lib/knowledge'

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

  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [pinned, setPinned] = useState<string[]>([])

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

  const selectedNode = data?.nodes.find((n) => n.id === selected) ?? null
  const selectedEdges = (data?.edges ?? []).filter(
    (e) => e.source_id === selected || e.target_id === selected,
  )
  const nodeById = new Map((data?.nodes ?? []).map((n) => [n.id, n]))

  const togglePin = (id: string) =>
    setPinned((current) => current.includes(id) ? current.filter((p) => p !== id) : [...current, id])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <h2 className="h-panel" style={{ fontSize: '1rem', marginBottom: 6 }}>Knowledge graph workspace</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', maxWidth: '78ch', lineHeight: 1.6 }}>
          Every entity and relationship OmniSignal knows, from SEC filings and Wikidata. Compare
          companies to see what they share, or trace how any two entities connect. Nothing here is
          inferred — every edge names the provider that asserted it and the confidence it carries.
        </p>
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
            <Skeleton height={460} />
          ) : !layout || layout.nodes.length === 0 ? (
            <EmptyState
              title="No graph for those tickers"
              description="Try a large US-listed company — the graph is built from SEC filings and Wikidata, which cover major issuers best."
            />
          ) : (
            <svg
              viewBox={viewBoxFor(layout)}
              role="application"
              aria-label={`Knowledge graph for ${symbols}`}
              style={{ width: '100%', height: 'auto', maxHeight: 520 }}
            >
              {layout.edges.map((edge, i) => {
                const active = edge.source === selected || edge.target === selected
                return (
                  <line
                    key={`${edge.source}-${edge.target}-${i}`}
                    x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2}
                    stroke={active ? 'var(--accent)' : 'var(--line)'}
                    strokeWidth={active ? 1.6 : 0.8}
                    opacity={active ? 1 : 0.55}
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
                     onClick={() => setSelected(node.id)}
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
          {data && (
            <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 8 }}>
              {data.analytics.nodes} entities · {data.analytics.edges} relationships ·
              density {data.analytics.density} · avg confidence {data.analytics.avg_confidence}
            </p>
          )}
        </section>

        {/* Inspector */}
        <section aria-label="Inspector" className="panel" style={{ padding: '18px 20px' }}>
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
                    <li key={row.id} style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
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

      {pinned.length > 0 && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
          Pinned: {pinned.map((id) => nodeById.get(id)?.label ?? id).join(' · ')}
        </p>
      )}
    </div>
  )
}
