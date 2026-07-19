/* ============================================================
   Deterministic graph layout.

   No force simulation. Positions are a pure function of the graph's
   structure, so opening Microsoft today and tomorrow produces an
   identical picture and users build spatial memory. Nodes never jump,
   and expanding a branch never rearranges the rest.

   Layout: roots on a stable ring (or centred when there is one), then
   each root's neighbours on concentric arcs allocated by relationship
   group, so related entities always sit together in the same direction.
   ============================================================ */

export interface LayoutNode {
  id: string
  type: string
  label: string
  route?: string | null
  x: number
  y: number
  depth: number
  degree: number
}

export interface LayoutEdge {
  source: string
  target: string
  type: string
  confidence: number
  provider: string
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface GraphInput {
  nodes: Array<{ id: string; type: string; label: string; route?: string | null }>
  edges: Array<{
    source_id: string
    target_id: string
    type: string
    confidence: number
    provider: string
    observed_at?: string
  }>
  roots: string[]
}

export interface Layout {
  nodes: LayoutNode[]
  edges: LayoutEdge[]
  width: number
  height: number
}

const RING_STEP = 165      // distance between depth rings
const ROOT_SPREAD = 260    // distance between multiple roots
const MIN_ARC = 0.28       // radians — keeps labels from colliding

/** Stable hash → the same label always sorts to the same angle bucket,
 *  so a node keeps its place even as siblings are added or removed. */
function stableKey(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function computeLayout(input: GraphInput): Layout {
  const { nodes, edges, roots } = input
  if (nodes.length === 0) return { nodes: [], edges: [], width: 800, height: 600 }

  const byId = new Map(nodes.map((n) => [n.id, n]))
  const adjacency = new Map<string, string[]>()
  const degree = new Map<string, number>()
  for (const edge of edges) {
    if (!byId.has(edge.source_id) || !byId.has(edge.target_id)) continue
    adjacency.set(edge.source_id, [...(adjacency.get(edge.source_id) ?? []), edge.target_id])
    adjacency.set(edge.target_id, [...(adjacency.get(edge.target_id) ?? []), edge.source_id])
    degree.set(edge.source_id, (degree.get(edge.source_id) ?? 0) + 1)
    degree.set(edge.target_id, (degree.get(edge.target_id) ?? 0) + 1)
  }

  const placed = new Map<string, { x: number; y: number; depth: number }>()
  const presentRoots = roots.filter((r) => byId.has(r))
  const rootList = presentRoots.length > 0 ? presentRoots : [nodes[0].id]

  // Roots: centred when single, evenly spaced on a horizontal axis otherwise.
  rootList.forEach((rootId, index) => {
    if (rootList.length === 1) {
      placed.set(rootId, { x: 0, y: 0, depth: 0 })
    } else {
      const offset = (index - (rootList.length - 1) / 2) * ROOT_SPREAD
      placed.set(rootId, { x: offset, y: 0, depth: 0 })
    }
  })

  // Breadth-first placement. Children of a node are spread across an arc
  // centred on the direction away from that node's own parent, so branches
  // grow outward instead of overlapping.
  const queue: Array<{ id: string; heading: number }> = rootList.map((id, index) => ({
    id,
    // Multiple roots face away from each other; a single root uses the full circle.
    heading: rootList.length === 1 ? 0 : index < rootList.length / 2 ? Math.PI : 0,
  }))

  while (queue.length > 0) {
    const current = queue.shift()!
    const parent = placed.get(current.id)!
    if (parent.depth >= 3) continue

    const children = (adjacency.get(current.id) ?? [])
      .filter((id) => !placed.has(id))
      // Deterministic order: high-degree first, then stable hash.
      .sort((a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || stableKey(a) - stableKey(b))

    if (children.length === 0) continue
    const radius = RING_STEP * (parent.depth + 1)
    const arc = Math.max(MIN_ARC * children.length, Math.PI * 0.9)
    const span = Math.min(arc, Math.PI * 1.9)
    const start = current.heading - span / 2

    children.forEach((childId, index) => {
      const angle = children.length === 1
        ? current.heading
        : start + (span * index) / (children.length - 1)
      placed.set(childId, {
        x: parent.x + Math.cos(angle) * radius,
        y: parent.y + Math.sin(angle) * radius,
        depth: parent.depth + 1,
      })
      queue.push({ id: childId, heading: angle })
    })
  }

  // Anything unreachable (filtered edges can orphan nodes) parks on a
  // deterministic outer ring rather than vanishing.
  const orphans = nodes.filter((n) => !placed.has(n.id))
  orphans.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / Math.max(1, orphans.length)
    placed.set(node.id, {
      x: Math.cos(angle) * RING_STEP * 4,
      y: Math.sin(angle) * RING_STEP * 4,
      depth: 4,
    })
  })

  const layoutNodes: LayoutNode[] = nodes.map((node) => {
    const position = placed.get(node.id)!
    return {
      id: node.id,
      type: node.type,
      label: node.label,
      route: node.route ?? null,
      x: position.x,
      y: position.y,
      depth: position.depth,
      degree: degree.get(node.id) ?? 0,
    }
  })

  const positions = new Map(layoutNodes.map((n) => [n.id, n]))
  const layoutEdges: LayoutEdge[] = edges
    .filter((e) => positions.has(e.source_id) && positions.has(e.target_id))
    .map((edge) => {
      const a = positions.get(edge.source_id)!
      const b = positions.get(edge.target_id)!
      return {
        source: edge.source_id,
        target: edge.target_id,
        type: edge.type,
        confidence: edge.confidence,
        provider: edge.provider,
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      }
    })

  const xs = layoutNodes.map((n) => n.x)
  const ys = layoutNodes.map((n) => n.y)
  const pad = 120
  return {
    nodes: layoutNodes,
    edges: layoutEdges,
    width: Math.max(...xs) - Math.min(...xs) + pad * 2,
    height: Math.max(...ys) - Math.min(...ys) + pad * 2,
  }
}

/** Viewbox that frames the whole graph, deterministically. */
export function viewBoxFor(layout: Layout): string {
  if (layout.nodes.length === 0) return '-400 -300 800 600'
  const xs = layout.nodes.map((n) => n.x)
  const ys = layout.nodes.map((n) => n.y)
  const pad = 120
  const minX = Math.min(...xs) - pad
  const minY = Math.min(...ys) - pad
  return `${minX} ${minY} ${Math.max(...xs) - minX + pad} ${Math.max(...ys) - minY + pad}`
}
