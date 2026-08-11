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

/* ── Relationship grouping ───────────────────────────────────────────────
   The layout's whole claim is that related entities sit together. A
   well-connected company has ~20 neighbours across a handful of relationship
   types; without grouping that renders as one undifferentiated starburst. */

const hub: GraphInput = {
  roots: ['company:NVDA'],
  nodes: [
    { id: 'company:NVDA', type: 'company', label: 'Nvidia' },
    ...Array.from({ length: 6 }, (_, i) => ({ id: `index:${i}`, type: 'index', label: `Index ${i}` })),
    ...Array.from({ length: 5 }, (_, i) => ({ id: `industry:${i}`, type: 'industry', label: `Industry ${i}` })),
    ...Array.from({ length: 4 }, (_, i) => ({ id: `location:${i}`, type: 'location', label: `Location ${i}` })),
    ...Array.from({ length: 3 }, (_, i) => ({ id: `exchange:${i}`, type: 'exchange', label: `Exchange ${i}` })),
  ],
  edges: [
    ...Array.from({ length: 6 }, (_, i) => ({ source_id: 'company:NVDA', target_id: `index:${i}`, type: 'member_of_index', confidence: 0.9, provider: 'wikidata' })),
    ...Array.from({ length: 5 }, (_, i) => ({ source_id: 'company:NVDA', target_id: `industry:${i}`, type: 'in_industry', confidence: 0.9, provider: 'wikidata' })),
    ...Array.from({ length: 4 }, (_, i) => ({ source_id: 'company:NVDA', target_id: `location:${i}`, type: 'headquartered_in', confidence: 0.9, provider: 'wikidata' })),
    ...Array.from({ length: 3 }, (_, i) => ({ source_id: 'company:NVDA', target_id: `exchange:${i}`, type: 'listed_on', confidence: 0.9, provider: 'wikidata' })),
  ],
}

type Ring = Array<{ id: string; angle: number }>

/** The depth-1 ring in angular order, rotated to start after the widest gap.
 *  A fan spans up to 1.9π, so a naive sort on [0, 2π) cuts one wedge at the
 *  seam and makes a perfectly grouped ring look interleaved. Rotating to the
 *  widest gap is what makes "contiguous" well defined on a circle. */
function ringInOrder(layout: ReturnType<typeof computeLayout>): Ring {
  const sorted: Ring = layout.nodes
    .filter((n) => n.depth === 1)
    .map((n) => ({ id: n.id, angle: (Math.atan2(n.y, n.x) + 2 * Math.PI) % (2 * Math.PI) }))
    .sort((a, b) => a.angle - b.angle)

  let seam = 0
  let widest = -1
  for (let i = 0; i < sorted.length; i += 1) {
    const next = sorted[(i + 1) % sorted.length]
    const gap = (next.angle - sorted[i].angle + 2 * Math.PI) % (2 * Math.PI)
    if (gap > widest) {
      widest = gap
      seam = (i + 1) % sorted.length
    }
  }
  return [...sorted.slice(seam), ...sorted.slice(0, seam)]
}

const typeOf = (id: string) => id.split(':')[0]

/** Sequence of relationship groups encountered walking the ring once. */
function groupSequence(layout: ReturnType<typeof computeLayout>): string[] {
  const runs: string[] = []
  for (const node of ringInOrder(layout)) {
    const t = typeOf(node.id)
    if (runs[runs.length - 1] !== t) runs.push(t)
  }
  return runs
}

test('each relationship type occupies one contiguous wedge', () => {
  const sequence = groupSequence(computeLayout(hub))
  assert.deepEqual(
    sequence,
    [...new Set(sequence)],
    `a type appeared in more than one run — ring order was ${sequence.join('>')}`,
  )
  assert.equal(sequence.length, 4, 'all four relationship types should be present')
})

test('the blank arc between groups is wider than the spacing inside them', () => {
  const ring = ringInOrder(computeLayout(hub))
  const within: number[] = []
  const between: number[] = []
  for (let i = 1; i < ring.length; i += 1) {
    const delta = (ring[i].angle - ring[i - 1].angle + 2 * Math.PI) % (2 * Math.PI)
    ;(typeOf(ring[i].id) === typeOf(ring[i - 1].id) ? within : between).push(delta)
  }
  assert.ok(
    Math.min(...between) > Math.max(...within),
    `boundaries (${Math.min(...between).toFixed(3)}) must exceed within-group spacing (${Math.max(...within).toFixed(3)})`,
  )
})

test('a dense fan pushes its ring outward so labels have room', () => {
  const radius = (l: ReturnType<typeof computeLayout>) => {
    const first = l.nodes.find((n) => n.depth === 1)!
    return Math.hypot(first.x, first.y)
  }
  assert.ok(
    radius(computeLayout(hub)) > radius(computeLayout(graph)),
    'an 18-neighbour hub should sit on a wider ring than a 3-neighbour one',
  )
})

test('grouping is stable — growing one group does not reorder the others', () => {
  const before = groupSequence(computeLayout(hub))
  const after = groupSequence(computeLayout({
    ...hub,
    nodes: [...hub.nodes, { id: 'index:new', type: 'index', label: 'Index new' }],
    edges: [...hub.edges, { source_id: 'company:NVDA', target_id: 'index:new', type: 'member_of_index', confidence: 0.9, provider: 'wikidata' }],
  }))
  assert.deepEqual(after, before)
})
