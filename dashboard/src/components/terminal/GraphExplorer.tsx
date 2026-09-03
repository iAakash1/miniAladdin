'use client'

import WorkBoot from '@/components/ui/WorkBoot'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import PageHeader from '@/components/ui/PageHeader'
import EmptyState from '@/components/ui/EmptyState'
import { EDGE_LABELS } from '@/lib/knowledge'

interface GraphNodeRef {
  id: string
  type: string
  label: string
  route: string | null
}

interface GraphEdgeRow {
  node: GraphNodeRef
  types: string[]
  group: string
  confidence: number
  provider: string
}

interface GraphSlice {
  center: GraphNodeRef
  edges: GraphEdgeRow[]
  timeline: Array<{ id: string; date: string; title: string; detail: string | null }>
  findings: Array<{ id: string; label: string; text: string; tone: 'pos' | 'neg' | 'neutral' }>
}

/* One muted hue per node type — type is structure, not decoration, so the
   palette stays within the existing token vocabulary. */
const TYPE_COLOR: Record<string, string> = {
  company: 'var(--accent)',
  person: 'var(--warn)',
  product: 'var(--pos)',
  industry: 'var(--muted)',
  country: 'var(--faint)',
  exchange: 'var(--faint)',
  subsidiary: 'var(--muted)',
  technology: 'var(--pos)',
}

const RADIUS = 148
const NODE_R = 6

function nodeColor(type: string): string {
  return TYPE_COLOR[type] ?? 'var(--muted)'
}

/**
 * Knowledge Graph Explorer — continuous traversal of the deterministic
 * graph. Every node is a valid center: selecting one re-centers the view
 * and loads its neighbours from /api/graph/expand. The layout is a
 * deterministic radial arrangement (no force simulation): identical data
 * always renders identically, which matters more than organic motion for
 * a research tool, and costs no animation frames.
 *
 * Keyboard: ↑↓ move through neighbours, ↵ recenter, ⌫ back.
 */
export default function GraphExplorer() {
  const router = useRouter()
  const params = useSearchParams()
  const nodeId = params.get('node') || 'company:NVDA'
  const label = params.get('label') || ''

  // Tagged with the node it describes, so `loading` is derived rather than
  // held in its own state and flipped inside the effect body.
  const [settled, setSettled] = useState<{ node: string; slice: GraphSlice | null } | null>(null)
  const slice = settled?.node === nodeId ? settled.slice : null
  const loading = settled === null || settled.node !== nodeId
  const [active, setActive] = useState(0)
  const [trail, setTrail] = useState<GraphNodeRef[]>([])
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    let alive = true
    // `setLoading(true)` used to run here, synchronously inside the effect
    // body. Loading is now derived from whether the settled slice matches the
    // node being asked for, which removes the cascading render and the stale
    // response race in one move.
    fetch(`/api/graph/expand?node=${encodeURIComponent(nodeId)}&label=${encodeURIComponent(label)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: GraphSlice | null) => {
        if (!alive) return
        setSettled({ node: nodeId, slice: data })
        setActive(0)
        if (data?.center) {
          setTrail((current) =>
            current.some((n) => n.id === data.center.id)
              ? current
              : [...current, data.center].slice(-8),
          )
        }
      })
      .catch(() => { if (alive) setSettled({ node: nodeId, slice: null }) })
    return () => {
      alive = false
    }
  }, [nodeId, label])

  const recenter = useCallback(
    (node: GraphNodeRef) => {
      router.push(
        `/terminal/graph?node=${encodeURIComponent(node.id)}&label=${encodeURIComponent(node.label)}`,
      )
    },
    [router],
  )

  // Memoised so the empty-array fallback is not a fresh identity each
  // render, which would invalidate the layout memo below on every pass.
  const edges = useMemo(() => slice?.edges ?? [], [slice])

  /* Radial layout **grouped by relationship type**, each type given its own
     contiguous arc.
   *
   * The previous version claimed to group and did not: it walked `edges` in
   * arrival order, so twenty-eight semantically distinct relationships —
   * industry membership, exchange listing, ownership, location — were drawn
   * as one undifferentiated starburst. Every edge looked the same, which is
   * precisely what makes a graph read as "objects thrown onto a circle".
   *
   * The data was always semantic; only the picture was not. Grouping puts
   * every industry link in one sector, every ownership link in another, so
   * the shape itself carries the classification the sidebar was already
   * reporting. */
  const { positioned, groups } = useMemo(() => {
    const buckets = new Map<string, typeof edges>()
    for (const edge of edges) {
      const key = edge.types[0] ?? 'related'
      const bucket = buckets.get(key)
      if (bucket) bucket.push(edge)
      else buckets.set(key, [edge])
    }
    // Largest families first, so the dominant relationship reads at the top.
    const ordered = [...buckets.entries()].sort((a, b) => b[1].length - a[1].length)
    const total = edges.length || 1

    // A gap between sectors is what makes the grouping visible at a glance;
    // without it adjacent families merge back into one ring.
    const GAP = 0.16
    const usable = 2 * Math.PI - GAP * ordered.length

    const laid: Array<{ edge: (typeof edges)[number]; x: number; y: number }> = []
    const legend: Array<{ type: string; count: number; midAngle: number }> = []
    let cursor = -Math.PI / 2

    for (const [type, members] of ordered) {
      const span = (members.length / total) * usable
      members.forEach((edge, index) => {
        // Centre each member in its own slot inside the sector.
        const angle = cursor + (span * (index + 0.5)) / members.length
        const radius = RADIUS + (index % 2 === 0 ? 0 : 46)
        laid.push({ edge, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius })
      })
      legend.push({ type, count: members.length, midAngle: cursor + span / 2 })
      cursor += span + GAP
    }
    return { positioned: laid, groups: legend }
  }, [edges])

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (edges.length === 0) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      event.preventDefault()
      setActive((i) => (i + 1) % edges.length)
    } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault()
      setActive((i) => (i - 1 + edges.length) % edges.length)
    } else if (event.key === 'Enter' && edges[active]) {
      event.preventDefault()
      recenter(edges[active].node)
    } else if (event.key === 'Backspace' && trail.length > 1) {
      event.preventDefault()
      recenter(trail[trail.length - 2])
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <PageHeader
          eyebrow="Workspace"
          title="Graph explorer"
          lede="Every entity OmniSignal knows about, and how they connect. Select any node to re-center — companies, executives, products and industries are all valid starting points. Relationships come from SEC filings and Wikidata; nothing here is inferred."
        />
      </div>

      {/* Breadcrumb trail: exploration history, always reversible. */}
      {trail.length > 1 && (
        <nav aria-label="Exploration trail" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
          {trail.map((node, index) => (
            <span key={`${node.id}-${index}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              {index > 0 && <span style={{ color: 'var(--faint)', fontSize: '0.75rem' }}>›</span>}
              <button
                type="button"
                className="btn btn--ghost btn--xs"
                onClick={() => recenter(node)}
                style={{ border: index === trail.length - 1 ? '1px solid var(--line-strong)' : '1px solid var(--line)' }}
              >
                {node.label}
              </button>
            </span>
          ))}
        </nav>
      )}

      <div className="terminal-grid-main">
        {/* The graph */}
        <section aria-label="Graph view" className="panel" style={{ padding: 18 }}>
          {loading ? (
            <WorkBoot
              compact
              label="Tracing connections"
              hint="walking asserted relationships outward from this entity"
            />
          ) : edges.length === 0 ? (
            <EmptyState
              title={`No connections recorded for ${slice?.center.label ?? nodeId}`}
              description="This entity is in the graph but no provider has asserted a relationship for it yet. Open a company to explore a populated ecosystem."
              action={
                <Link href="/terminal/graph?node=company:NVDA&label=NVDA" className="btn btn--secondary btn--sm">
                  Explore NVDA
                </Link>
              }
            />
          ) : (
            <svg
              ref={svgRef}
              viewBox="-260 -230 520 460"
              role="application"
              aria-label={`Knowledge graph centered on ${slice?.center.label}`}
              tabIndex={0}
              onKeyDown={onKeyDown}
              style={{ width: '100%', height: 'auto', maxHeight: 480, outline: 'none' }}
            >
              {/* Sector labels — the grouping is only useful if it is named.
                  Placed outside the node ring at each family's mid-angle. */}
              {groups.length > 1 && groups.map((group) => {
                const r = RADIUS + 96
                const x = Math.cos(group.midAngle) * r
                const y = Math.sin(group.midAngle) * r
                return (
                  <text
                    key={`sector-${group.type}`}
                    x={x} y={y}
                    textAnchor={Math.abs(Math.cos(group.midAngle)) < 0.3
                      ? 'middle'
                      : Math.cos(group.midAngle) > 0 ? 'start' : 'end'}
                    style={{
                      fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase',
                      fill: 'var(--faint)',
                    }}
                  >
                    {EDGE_LABELS[group.type] ?? group.type} ({group.count})
                  </text>
                )
              })}

              {/* Edges first so nodes paint above them */}
              {positioned.map(({ edge, x, y }, index) => (
                <line
                  key={`line-${edge.node.id}-${index}`}
                  x1={0} y1={0} x2={x} y2={y}
                  stroke={index === active ? 'var(--accent)' : 'var(--line-strong)'}
                  strokeWidth={index === active ? 1.5 : 1}
                />
              ))}

              {/* Center */}
              <circle r={NODE_R + 3} fill={nodeColor(slice?.center.type ?? 'company')} />
              <text
                y={-16} textAnchor="middle"
                style={{ fontSize: 13, fontWeight: 600, fill: 'var(--text)' }}
              >
                {slice?.center.label}
              </text>

              {/* Neighbours */}
              {positioned.map(({ edge, x, y }, index) => {
                const isActive = index === active
                return (
                  <g
                    key={`${edge.node.id}-${index}`}
                    transform={`translate(${x}, ${y})`}
                    onClick={() => recenter(edge.node)}
                    onMouseEnter={() => setActive(index)}
                    style={{ cursor: 'pointer' }}
                    role="button"
                    aria-label={`${edge.node.label} — ${edge.types.map((t) => EDGE_LABELS[t] ?? t).join(', ')}`}
                  >
                    <circle
                      r={isActive ? NODE_R + 2 : NODE_R}
                      fill={nodeColor(edge.node.type)}
                      opacity={isActive ? 1 : 0.85}
                    />
                    <text
                      y={y > 0 ? 20 : -13}
                      textAnchor="middle"
                      style={{
                        fontSize: 10.5,
                        fill: isActive ? 'var(--text)' : 'var(--muted)',
                        fontWeight: isActive ? 600 : 400,
                      }}
                    >
                      {edge.node.label.length > 22 ? `${edge.node.label.slice(0, 21)}…` : edge.node.label}
                    </text>
                  </g>
                )
              })}
            </svg>
          )}
          <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 10 }}>
            ↑↓ move · ↵ re-center · ⌫ back · click any node to explore
          </p>
        </section>

        {/* Inspector: what the selected edge asserts, and who says so */}
        <section aria-label="Selected relationship" className="panel panel--pad">
          <h2 className="h-panel" style={{ marginBottom: 12 }}>Relationship</h2>
          {edges[active] ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <p className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>Entity</p>
                <p style={{ fontSize: '0.9375rem', fontWeight: 600 }}>{edges[active].node.label}</p>
                <p style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>{edges[active].node.type}</p>
              </div>
              <div>
                <p className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>Connection</p>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text)' }}>
                  {edges[active].types.map((t) => EDGE_LABELS[t] ?? t).join(' · ')}
                </p>
              </div>
              <div>
                <p className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>Provenance</p>
 <p className="num u-note" >
                  {edges[active].provider} · confidence {edges[active].confidence}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => recenter(edges[active].node)}>
                  Explore
                </button>
                {edges[active].node.route?.startsWith('/company/') && (
                  <Link href={edges[active].node.route!} className="btn btn--ghost btn--sm">
                    Open report
                  </Link>
                )}
              </div>
            </div>
          ) : (
            <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
              Select a node to see what connects it and which provider asserted the link.
            </p>
          )}

          {(slice?.findings.length ?? 0) > 0 && (
            <div className="hairline-top" style={{ marginTop: 16, paddingTop: 14 }}>
              <p className="label" style={{ fontSize: '0.625rem', marginBottom: 8 }}>From filings</p>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {slice!.findings.slice(0, 4).map((finding) => (
                  <li key={finding.id} className="u-note">
                    {finding.text}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
