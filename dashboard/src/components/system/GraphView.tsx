/**
 * Relationship graph.
 *
 * Laid out radially by hop distance from the roots, not by force simulation.
 * A physics layout looks impressive and is non-deterministic: the same graph
 * draws differently on every render, so nothing can be remembered, compared
 * across sessions, or pointed at. Hop rings mean position carries information —
 * how far a node is from what you asked about — and the same query always draws
 * the same picture.
 *
 * Within a ring, nodes are ordered by type then label, so a node keeps its place
 * when neighbours are filtered out.
 */
'use client'

import { useMemo, useState } from 'react'

export interface GraphNode {
  id: string
  type: string
  label: string
  description?: string
  route?: string
  metadata?: Record<string, unknown>
}

export interface GraphEdge {
  source_id: string
  target_id: string
  type: string
  provider?: string
  confidence?: number
  observed_at?: string
  valid_from?: string | null
  valid_to?: string | null
}

/** Stable colour per node type, assigned from a fixed palette by sorted order. */
const TYPE_TONES = [
  'var(--s-recorded)', 'var(--s-candidate)', 'var(--s-experimental)',
  'var(--s-stale)', 'var(--s-live)', 'var(--s-unavailable)', 'var(--ink-muted)',
]

export function typeTone(type: string, allTypes: string[]): string {
  const i = allTypes.indexOf(type)
  return TYPE_TONES[(i < 0 ? 0 : i) % TYPE_TONES.length]
}

interface Placed extends GraphNode {
  x: number
  y: number
  ring: number
}

export function GraphView({
  nodes, edges, roots, selectedId, onSelect, height = 520,
}: {
  nodes: GraphNode[]
  edges: GraphEdge[]
  roots: string[]
  selectedId?: string | null
  onSelect?: (node: GraphNode) => void
  height?: number
}) {
  const [hovered, setHovered] = useState<string | null>(null)

  const types = useMemo(() => [...new Set(nodes.map((n) => n.type))].sort(), [nodes])

  /** Breadth-first hop distance from the roots. Unreachable nodes get the last ring. */
  const placed = useMemo((): Placed[] => {
    if (!nodes.length) return []
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const adjacency = new Map<string, string[]>()
    for (const e of edges) {
      if (!adjacency.has(e.source_id)) adjacency.set(e.source_id, [])
      if (!adjacency.has(e.target_id)) adjacency.set(e.target_id, [])
      adjacency.get(e.source_id)!.push(e.target_id)
      adjacency.get(e.target_id)!.push(e.source_id)
    }

    const ring = new Map<string, number>()
    const queue: string[] = []
    for (const r of roots) {
      if (byId.has(r)) { ring.set(r, 0); queue.push(r) }
    }
    if (!queue.length && nodes.length) { ring.set(nodes[0].id, 0); queue.push(nodes[0].id) }

    while (queue.length) {
      const id = queue.shift()!
      const d = ring.get(id)!
      for (const next of adjacency.get(id) ?? []) {
        if (!ring.has(next) && byId.has(next)) { ring.set(next, d + 1); queue.push(next) }
      }
    }

    const maxRing = Math.max(1, ...[...ring.values()])
    for (const n of nodes) if (!ring.has(n.id)) ring.set(n.id, maxRing + 1)

    const rings = new Map<number, GraphNode[]>()
    for (const n of nodes) {
      const d = ring.get(n.id)!
      const list = rings.get(d) ?? []
      list.push(n)
      rings.set(d, list)
    }

    const cx = 500
    const cy = height / 2
    const maxDepth = Math.max(...rings.keys())
    const step = maxDepth > 0 ? (Math.min(cx, cy) - 40) / maxDepth : 0

    const out: Placed[] = []
    for (const [depth, group] of [...rings.entries()].sort((a, b) => a[0] - b[0])) {
      // Order within a ring is stable, so filtering a neighbour does not move
      // everything else.
      const ordered = [...group].sort((a, b) => (a.type + a.label).localeCompare(b.type + b.label))
      if (depth === 0) {
        ordered.forEach((n, i) => {
          const spread = ordered.length > 1 ? (i - (ordered.length - 1) / 2) * 60 : 0
          out.push({ ...n, x: cx + spread, y: cy, ring: 0 })
        })
        continue
      }
      const radius = step * depth
      ordered.forEach((n, i) => {
        const angle = (i / ordered.length) * Math.PI * 2 - Math.PI / 2
        out.push({ ...n, x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) * 0.62, ring: depth })
      })
    }
    return out
  }, [nodes, edges, roots, height])

  const position = useMemo(() => new Map(placed.map((p) => [p.id, p])), [placed])

  const active = hovered ?? selectedId ?? null
  const connected = useMemo(() => {
    if (!active) return null
    const set = new Set<string>([active])
    for (const e of edges) {
      if (e.source_id === active) set.add(e.target_id)
      if (e.target_id === active) set.add(e.source_id)
    }
    return set
  }, [active, edges])

  if (!placed.length) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed var(--rule)', color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)', fontSize: 'var(--t-meta)' }}>
        no nodes
      </div>
    )
  }

  const maxRing = Math.max(...placed.map((p) => p.ring))

  return (
    <div className="sys-scroll-x">
      <svg
        viewBox={`0 0 1000 ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label="relationship graph"
        style={{ display: 'block', minWidth: 620 }}
        onMouseLeave={() => setHovered(null)}
      >
        {/* Hop rings, so distance from the query is legible as geometry. */}
        {Array.from({ length: maxRing }, (_, i) => i + 1).map((r) => {
          const step = maxRing > 0 ? (Math.min(500, height / 2) - 40) / maxRing : 0
          return (
            <ellipse
              key={r}
              cx={500} cy={height / 2}
              rx={step * r} ry={step * r * 0.62}
              fill="none" stroke="var(--rule)" strokeDasharray="2 4"
            />
          )
        })}

        {edges.map((e, i) => {
          const a = position.get(e.source_id)
          const b = position.get(e.target_id)
          if (!a || !b) return null
          const dim = connected ? !(connected.has(e.source_id) && connected.has(e.target_id)) : false
          const confidence = typeof e.confidence === 'number' ? e.confidence : 0.5
          return (
            <line
              key={`${e.source_id}-${e.target_id}-${e.type}-${i}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="var(--ink-faint)"
              strokeWidth={0.4 + confidence * 1.1}
              opacity={dim ? 0.06 : 0.3 + confidence * 0.3}
            >
              <title>{`${e.type} · ${e.provider ?? 'unknown provider'} · confidence ${confidence.toFixed(2)}`}</title>
            </line>
          )
        })}

        {placed.map((p) => {
          const dim = connected ? !connected.has(p.id) : false
          const isRoot = p.ring === 0
          const isSelected = selectedId === p.id
          return (
            <g
              key={p.id}
              transform={`translate(${p.x} ${p.y})`}
              opacity={dim ? 0.2 : 1}
              style={{ cursor: onSelect ? 'pointer' : 'default' }}
              onMouseEnter={() => setHovered(p.id)}
              onClick={() => onSelect?.(p)}
              tabIndex={onSelect ? 0 : undefined}
              onKeyDown={(e) => { if (e.key === 'Enter') onSelect?.(p) }}
            >
              <rect
                x={-4} y={-4} width={8} height={8}
                fill={typeTone(p.type, types)}
                stroke={isSelected ? 'var(--ink)' : 'transparent'}
                strokeWidth={isSelected ? 2 : 0}
                transform={isRoot ? 'scale(1.5)' : undefined}
              />
              <text
                x={0} y={isRoot ? 18 : 14}
                textAnchor="middle"
                fontSize={isRoot ? 10 : 8.5}
                fontFamily="var(--font-mono)"
                fill={isSelected || isRoot ? 'var(--ink)' : 'var(--ink-muted)'}
              >
                {p.label.length > 18 ? `${p.label.slice(0, 17)}…` : p.label}
              </text>
              <title>{`${p.label}\n${p.type}\nhop ${p.ring}${p.description ? `\n${p.description}` : ''}`}</title>
            </g>
          )
        })}
      </svg>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-3)', padding: 'var(--d-2) var(--d-3)', borderTop: '1px solid var(--rule)' }}>
        {types.map((t) => (
          <span key={t} className="sys-meta" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 7, height: 7, background: typeTone(t, types) }} />
            {t}
          </span>
        ))}
        <span className="sys-meta" style={{ marginLeft: 'auto' }}>
          rings are hop distance from the query · edge weight is confidence
        </span>
      </div>
    </div>
  )
}
