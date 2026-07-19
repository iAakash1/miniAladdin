/* Deterministic layout: the property that makes spatial memory possible. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { computeLayout, viewBoxFor, type GraphInput } from '../src/lib/graph/layout'

const graph: GraphInput = {
  roots: ['company:NVDA'],
  nodes: [
    { id: 'company:NVDA', type: 'company', label: 'Nvidia' },
    { id: 'person:jensen', type: 'person', label: 'Jensen Huang' },
    { id: 'product:cuda', type: 'product', label: 'CUDA' },
    { id: 'country:us', type: 'country', label: 'United States' },
  ],
  edges: [
    { source_id: 'person:jensen', target_id: 'company:NVDA', type: 'ceo_of', confidence: 0.9, provider: 'wikidata' },
    { source_id: 'company:NVDA', target_id: 'product:cuda', type: 'produces', confidence: 0.9, provider: 'wikidata' },
    { source_id: 'company:NVDA', target_id: 'country:us', type: 'headquartered_in', confidence: 0.9, provider: 'wikidata' },
  ],
}

test('identical input produces identical positions — no randomness', () => {
  const a = computeLayout(graph)
  const b = computeLayout(graph)
  assert.deepEqual(a.nodes.map((n) => [n.id, n.x, n.y]), b.nodes.map((n) => [n.id, n.x, n.y]))
})

test('node order in the input does not change the layout', () => {
  const shuffled: GraphInput = { ...graph, nodes: [...graph.nodes].reverse() }
  const a = computeLayout(graph)
  const b = computeLayout(shuffled)
  const posA = new Map(a.nodes.map((n) => [n.id, `${n.x},${n.y}`]))
  const posB = new Map(b.nodes.map((n) => [n.id, `${n.x},${n.y}`]))
  for (const [id, pos] of posA) assert.equal(posB.get(id), pos, id)
})

test('single root sits at the origin', () => {
  const root = computeLayout(graph).nodes.find((n) => n.id === 'company:NVDA')!
  assert.equal(root.x, 0)
  assert.equal(root.y, 0)
  assert.equal(root.depth, 0)
})

test('multiple roots are spread apart, not stacked', () => {
  const multi: GraphInput = {
    roots: ['company:NVDA', 'company:MSFT'],
    nodes: [...graph.nodes, { id: 'company:MSFT', type: 'company', label: 'Microsoft' }],
    edges: graph.edges,
  }
  const layout = computeLayout(multi)
  const a = layout.nodes.find((n) => n.id === 'company:NVDA')!
  const b = layout.nodes.find((n) => n.id === 'company:MSFT')!
  assert.notEqual(a.x, b.x)
})

test('neighbours are placed one ring out, never on top of the root', () => {
  const layout = computeLayout(graph)
  for (const node of layout.nodes.filter((n) => n.depth === 1)) {
    const distance = Math.hypot(node.x, node.y)
    assert.ok(distance > 100, `${node.id} too close: ${distance}`)
  }
})

test('adding a node leaves existing nodes in place', () => {
  const before = computeLayout(graph)
  const after = computeLayout({
    ...graph,
    nodes: [...graph.nodes, { id: 'industry:semis', type: 'industry', label: 'Semiconductors' }],
  })
  const posBefore = new Map(before.nodes.map((n) => [n.id, `${n.x},${n.y}`]))
  const rootAfter = after.nodes.find((n) => n.id === 'company:NVDA')!
  // The root is the anchor of spatial memory — it must not move.
  assert.equal(`${rootAfter.x},${rootAfter.y}`, posBefore.get('company:NVDA'))
})

test('edges carry endpoint coordinates for rendering', () => {
  const layout = computeLayout(graph)
  assert.equal(layout.edges.length, 3)
  for (const edge of layout.edges) {
    assert.ok(Number.isFinite(edge.x1) && Number.isFinite(edge.y2))
  }
})

test('edges referencing missing nodes are dropped', () => {
  const layout = computeLayout({
    ...graph,
    edges: [...graph.edges, { source_id: 'company:NVDA', target_id: 'ghost', type: 'owns', confidence: 0.5, provider: 'x' }],
  })
  assert.equal(layout.edges.length, 3)
})

test('orphaned nodes still get a position', () => {
  const layout = computeLayout({
    roots: ['company:NVDA'],
    nodes: [...graph.nodes, { id: 'company:LONE', type: 'company', label: 'Lonely' }],
    edges: graph.edges,
  })
  const lone = layout.nodes.find((n) => n.id === 'company:LONE')!
  assert.ok(Number.isFinite(lone.x) && Number.isFinite(lone.y))
})

test('empty graph does not throw', () => {
  const layout = computeLayout({ roots: [], nodes: [], edges: [] })
  assert.deepEqual(layout.nodes, [])
  assert.equal(viewBoxFor(layout), '-400 -300 800 600')
})
