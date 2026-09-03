/**
 * Relationship workspace.
 *
 * The legacy graph explorer had a real graph behind it — typed nodes, typed
 * edges, per-edge provider and confidence, and temporal validity — presented as
 * a canvas. Rebuilt so the graph is one view of the data and the tables are
 * another, because a relationship list is often the faster read.
 *
 * Confidence and provider travel with every edge. A relationship asserted at
 * 0.5 by one vendor is a different claim from one asserted at 0.95 by three,
 * and a graph that draws both as a line has thrown that away.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import { GraphView, typeTone, type GraphEdge, type GraphNode } from '@/components/system/GraphView'
import { Grid, Panel, Section, StateBlock, Strip, Value } from '@/components/system'
import { ChartSkeleton, StripSkeleton } from '@/components/system/composition'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'

interface Analytics {
  nodes?: number
  edges?: number
  density?: number
  avg_confidence?: number
  node_types?: Record<string, number>
  edge_types?: Record<string, number>
  provider_coverage?: Record<string, number>
  most_connected?: { id?: string; label?: string; degree?: number }[]
}

interface Workspace {
  roots?: string[]
  nodes?: GraphNode[]
  edges?: GraphEdge[]
  analytics?: Analytics
  shared?: unknown[]
  detail?: string
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

export default function Relationships({ initialSymbol = 'AAPL' }: { initialSymbol?: string }) {
  const [symbol, setSymbol] = useState(initialSymbol)
  const [query, setQuery] = useState(initialSymbol)
  const [hops, setHops] = useState(2)
  const [minConfidence, setMinConfidence] = useState(0)
  // Tagged with the query it answers, so a stale response is filtered at render
  // rather than cleared inside the effect.
  const [result, setResult] = useState<{ key: string; data: Workspace } | null>(null)
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [edgeTypes, setEdgeTypes] = useState<Set<string>>(new Set())

  useEffect(() => {
    let alive = true
    const key = `${symbol}|${hops}`
    const params = new URLSearchParams({ symbols: symbol, hops: String(hops) })
    fetch(`/api/graph/workspace?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Workspace) => { if (alive) setResult({ key, data: d }) })
      .catch((e: Error) => { if (alive) setFailure({ key, message: e.message }) })
    return () => { alive = false }
  }, [symbol, hops])

  const queryKey = `${symbol}|${hops}`
  const data = result?.key === queryKey ? result.data : null
  const error = failure?.key === queryKey ? failure.message : null

  const allEdges = useMemo(() => data?.edges ?? [], [data])
  const allNodes = useMemo(() => data?.nodes ?? [], [data])

  const edges = useMemo(() => allEdges.filter((e) => {
    if (edgeTypes.size && !edgeTypes.has(e.type)) return false
    return (e.confidence ?? 1) >= minConfidence
  }), [allEdges, edgeTypes, minConfidence])

  /** Nodes still reachable through the surviving edges, plus the roots. */
  const nodes = useMemo(() => {
    if (!edgeTypes.size && minConfidence === 0) return allNodes
    const keep = new Set<string>(data?.roots ?? [])
    for (const e of edges) { keep.add(e.source_id); keep.add(e.target_id) }
    return allNodes.filter((x) => keep.has(x.id))
  }, [allNodes, edges, edgeTypes, minConfidence, data])

  const nodeTypes = useMemo(() => [...new Set(allNodes.map((x) => x.type))].sort(), [allNodes])
  const availableEdgeTypes = useMemo(() => [...new Set(allEdges.map((e) => e.type))].sort(), [allEdges])

  const degree = useMemo(() => {
    const d = new Map<string, number>()
    for (const e of edges) {
      d.set(e.source_id, (d.get(e.source_id) ?? 0) + 1)
      d.set(e.target_id, (d.get(e.target_id) ?? 0) + 1)
    }
    return d
  }, [edges])

  const nodeColumns: DataColumn<GraphNode>[] = useMemo(() => [
    {
      key: 'label', header: 'Node', width: '30%', sort: (x) => x.label, text: (x) => `${x.label} ${x.description ?? ''}`,
      render: (x) => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 7, height: 7, background: typeTone(x.type, nodeTypes), flex: 'none' }} />
          <span style={{ fontFamily: 'var(--font-mono)' }}>{x.label}</span>
        </span>
      ),
    },
    { key: 'type', header: 'Type', width: '16%', sort: (x) => x.type, text: (x) => x.type, render: (x) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{x.type}</span> },
    { key: 'deg', header: 'Connections', numeric: true, sort: (x) => degree.get(x.id) ?? 0, render: (x) => <Value value={degree.get(x.id) ?? 0} digits={0} /> },
    { key: 'desc', header: 'Description', text: (x) => x.description ?? '', render: (x) => <span style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>{x.description ?? '—'}</span> },
  ], [nodeTypes, degree])

  const edgeColumns: DataColumn<GraphEdge>[] = useMemo(() => {
    const label = (id: string) => allNodes.find((x) => x.id === id)?.label ?? id
    return [
      { key: 'src', header: 'From', width: '22%', sort: (e) => label(e.source_id), text: (e) => label(e.source_id), render: (e) => <span style={{ fontFamily: 'var(--font-mono)' }}>{label(e.source_id)}</span> },
      { key: 'type', header: 'Relationship', width: '18%', sort: (e) => e.type, text: (e) => e.type, render: (e) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{e.type}</span> },
      { key: 'tgt', header: 'To', width: '22%', sort: (e) => label(e.target_id), text: (e) => label(e.target_id), render: (e) => <span style={{ fontFamily: 'var(--font-mono)' }}>{label(e.target_id)}</span> },
      {
        key: 'conf', header: 'Confidence', unit: '0 to 1', numeric: true, sort: (e) => n(e.confidence),
        render: (e) => <Value value={n(e.confidence)} digits={2} title="How strongly the provider asserts this relationship" />,
      },
      { key: 'prov', header: 'Provider', width: '14%', sort: (e) => e.provider ?? null, text: (e) => e.provider ?? '', render: (e) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{e.provider ?? '—'}</span> },
      { key: 'from', header: 'Valid from', optional: true, sort: (e) => e.valid_from ?? null, render: (e) => <span className="sys-meta">{e.valid_from ?? '—'}</span> },
      { key: 'to', header: 'Valid to', optional: true, sort: (e) => e.valid_to ?? null, render: (e) => <span className="sys-meta">{e.valid_to ?? 'open'}</span> },
      { key: 'obs', header: 'Observed', optional: true, sort: (e) => e.observed_at ?? null, render: (e) => <span className="sys-meta">{e.observed_at ?? '—'}</span> },
    ]
  }, [allNodes])

  const selectedEdges = useMemo(
    () => (selected ? edges.filter((e) => e.source_id === selected.id || e.target_id === selected.id) : []),
    [selected, edges],
  )

  const a = data?.analytics ?? {}

  return (
    <>
      <Panel
        title="Query"
        actions={
          <div style={{ display: 'flex', gap: 'var(--d-2)', alignItems: 'center', flexWrap: 'wrap' }}>
            <form
              onSubmit={(e) => { e.preventDefault(); setSymbol(query.trim().toUpperCase()); setSelected(null) }}
              style={{ display: 'flex', gap: 'var(--d-1)' }}
            >
              <input
                className="sys-input" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="symbol" aria-label="Root symbol" style={{ width: 96 }}
              />
              <button className="sys-btn" type="submit">load</button>
            </form>
            <div className="sys-seg">
              {[1, 2, 3].map((h) => (
                <button key={h} className="sys-btn" aria-pressed={hops === h} onClick={() => setHops(h)}>{h} hop</button>
              ))}
            </div>
            <div className="sys-seg">
              {[0, 0.5, 0.8, 0.9].map((c) => (
                <button key={c} className="sys-btn" aria-pressed={minConfidence === c} onClick={() => setMinConfidence(c)}>
                  {c === 0 ? 'all' : `≥${c}`}
                </button>
              ))}
            </div>
          </div>
        }
      >
        <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '86ch' }}>
          Relationships are asserted by providers with a confidence and a validity
          window. A claim at 0.5 from one source is not the same as one at 0.95
          from three, so both travel with every edge and the confidence filter is
          part of the query rather than a display option.
        </p>
      </Panel>

      {error ? (
        <Panel title="Graph" state="unavailable">
          <StateBlock state="unavailable" title={`No graph for ${symbol}`} detail={`Request failed: ${error}. Nothing is drawn in its place.`} />
        </Panel>
      ) : !data ? (
        <>
          <StripSkeleton items={7} />
          <Panel title="Graph" state="waking"><ChartSkeleton height={340} /></Panel>
        </>
      ) : !allNodes.length ? (
        <Panel title="Graph" state="unavailable">
          <StateBlock state="unavailable" title={`No relationships recorded for ${symbol}`} detail={data.detail} />
        </Panel>
      ) : (
        <>
          <Strip metrics={[
            { label: 'Nodes', value: nodes.length, digits: 0 },
            { label: 'Edges', value: edges.length, digits: 0 },
            { label: 'Of total edges', value: allEdges.length, digits: 0 },
            { label: 'Density', value: n(a.density), digits: 4, title: 'Edges present over edges possible' },
            { label: 'Mean confidence', value: n(a.avg_confidence), digits: 3 },
            { label: 'Node types', value: nodeTypes.length, digits: 0 },
            { label: 'Relationship types', value: availableEdgeTypes.length, digits: 0 },
          ]} />

          <Panel
            title="Graph"
            subtitle={`${symbol} · ${hops} hop${hops > 1 ? 's' : ''}`}
            flush
            actions={
              <div style={{ display: 'flex', gap: 'var(--d-1)', flexWrap: 'wrap', maxWidth: 520, justifyContent: 'flex-end' }}>
                {availableEdgeTypes.slice(0, 8).map((t) => (
                  <button
                    key={t}
                    className="sys-btn"
                    aria-pressed={edgeTypes.has(t)}
                    onClick={() => setEdgeTypes((prev) => {
                      const next = new Set(prev)
                      if (next.has(t)) next.delete(t)
                      else next.add(t)
                      return next
                    })}
                  >{t}</button>
                ))}
                {edgeTypes.size ? <button className="sys-btn" onClick={() => setEdgeTypes(new Set())}>all</button> : null}
              </div>
            }
          >
            <GraphView
              nodes={nodes}
              edges={edges}
              roots={data.roots ?? []}
              selectedId={selected?.id}
              onSelect={(node) => {
                setSelected(node)
                if (node.type === 'company') {
                  const ticker = node.id.split(':')[1]
                  if (ticker) recordVisit({ kind: 'security', id: ticker, label: node.label, detail: node.type })
                }
              }}
            />
          </Panel>

          {selected ? (
            <Panel
              title="Node"
              subtitle={selected.type}
              state="recorded"
              actions={
                selected.type === 'company' ? (
                  <Link
                    href={`/terminal/security?symbol=${encodeURIComponent(selected.id.split(':')[1] ?? '')}`}
                    className="sys-btn" style={{ textDecoration: 'none' }}
                  >
                    open security
                  </Link>
                ) : null
              }
            >
              <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.5fr)' }}>
                <Section title="Identity">
                  <table className="sys-table sys-table--compact">
                    <tbody>
                      <tr><td>Label</td><td className="num" style={{ textAlign: 'left' }}>{selected.label}</td></tr>
                      <tr><td>Type</td><td className="num" style={{ textAlign: 'left' }}>{selected.type}</td></tr>
                      <tr><td>Id</td><td className="num" style={{ textAlign: 'left', fontSize: 'var(--t-micro)', wordBreak: 'break-all' }}>{selected.id}</td></tr>
                      <tr><td>Connections</td><td className="num"><Value value={degree.get(selected.id) ?? 0} digits={0} /></td></tr>
                    </tbody>
                  </table>
                </Section>
                <Section title="Description">
                  <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                    {selected.description ?? 'No description recorded.'}
                  </p>
                </Section>
              </div>

              {selectedEdges.length ? (
                <div style={{ marginTop: 'var(--d-3)' }}>
                  <div className="sys-label" style={{ marginBottom: 'var(--d-1)' }}>Relationships</div>
                  <table className="sys-table sys-table--compact">
                    <tbody>
                      {selectedEdges.map((e, i) => {
                        const other = e.source_id === selected.id ? e.target_id : e.source_id
                        const node = allNodes.find((x) => x.id === other)
                        const outgoing = e.source_id === selected.id
                        return (
                          <tr key={`${e.source_id}-${e.target_id}-${i}`}>
                            <td className="sys-meta" style={{ width: 22 }}>{outgoing ? '→' : '←'}</td>
                            <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{e.type}</span></td>
                            <td>
                              <button
                                className="sys-btn"
                                style={{ textTransform: 'none', letterSpacing: 0, fontFamily: 'var(--font-mono)' }}
                                onClick={() => node && setSelected(node)}
                              >
                                {node?.label ?? other}
                              </button>
                            </td>
                            <td className="num"><Value value={n(e.confidence)} digits={2} /></td>
                            <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{e.provider ?? '—'}</span></td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </Panel>
          ) : (
            <Panel title="Node">
              <StateBlock state="unknown" title="No node selected" detail="Choose a node in the graph or a row below to see what it connects to." />
            </Panel>
          )}

          <Panel title="Nodes" subtitle={`${nodes.length} in view`} flush>
            <DataTable
              columns={nodeColumns} rows={nodes} rowKey={(x) => x.id}
              density="compact" filterPlaceholder="filter nodes"
              initialSort={{ key: 'deg', direction: 'desc' }}
              selectedKey={selected?.id}
              onSelect={(x) => setSelected(x)}
            />
          </Panel>

          <Panel title="Relationships" subtitle={`${edges.length} in view`} flush>
            <DataTable
              columns={edgeColumns} rows={edges}
              rowKey={(e) => `${e.source_id}|${e.target_id}|${e.type}`}
              density="compact" filterPlaceholder="filter relationships"
              initialSort={{ key: 'conf', direction: 'desc' }}
            />
          </Panel>

          <Grid variant="halves">
            {a.node_types ? (
              <Panel title="Node types">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {Object.entries(a.node_types).sort((x, y) => y[1] - x[1]).map(([t, c]) => (
                      <tr key={t}>
                        <td>
                          <span style={{ display: 'inline-block', width: 7, height: 7, background: typeTone(t, nodeTypes), marginRight: 6 }} />
                          {t}
                        </td>
                        <td className="num"><Value value={c} digits={0} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            ) : null}
            {a.edge_types ? (
              <Panel title="Relationship types">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {Object.entries(a.edge_types).sort((x, y) => y[1] - x[1]).map(([t, c]) => (
                      <tr key={t}><td>{t}</td><td className="num"><Value value={c} digits={0} /></td></tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            ) : null}
            {a.provider_coverage ? (
              <Panel title="Provider coverage" subtitle="who asserted what">
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {Object.entries(a.provider_coverage).sort((x, y) => y[1] - x[1]).map(([t, c]) => (
                      <tr key={t}><td>{t}</td><td className="num"><Value value={c} digits={0} /></td></tr>
                    ))}
                  </tbody>
                </table>
                <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
                  Every relationship here is a provider&apos;s assertion, not a
                  measurement. The provider is named on each edge for that reason.
                </p>
              </Panel>
            ) : null}
          </Grid>
        </>
      )}
    </>
  )
}
