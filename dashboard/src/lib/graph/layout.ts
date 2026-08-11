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
// A group boundary is this many times wider than the spacing between two
// members of the same group. Below ~1.5 the wedges blur back into one ring;
// much above 2 and a fan with many small groups wastes most of its arc on
// blank space.
const GROUP_GAP_RATIO = 1.9
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
  // Adjacency carries the relationship type, because the type is what the
  // layout groups by. Without it every neighbour is interchangeable and a
  // well-connected company renders as one undifferentiated starburst — 22
  // identical spokes with colliding rim labels, which is what this file's
  // own header comment already claimed it did not do.
  const adjacency = new Map<string, Array<{ id: string; type: string }>>()
  const degree = new Map<string, number>()
  const link = (from: string, to: string, type: string) => {
    adjacency.set(from, [...(adjacency.get(from) ?? []), { id: to, type }])
  }
  for (const edge of edges) {
    if (!byId.has(edge.source_id) || !byId.has(edge.target_id)) continue
    link(edge.source_id, edge.target_id, edge.type)
    link(edge.target_id, edge.source_id, edge.type)
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

    const children = (adjacency.get(current.id) ?? []).filter((child) => !placed.has(child.id))
    if (children.length === 0) continue

    // Group by relationship type, then give each group its own contiguous
    // wedge. Reading the picture becomes "these six are all its indices,
    // those three are locations" instead of "here are 22 things".
    const groups = new Map<string, string[]>()
    for (const child of children) {
      if (!groups.has(child.type)) groups.set(child.type, [])
      // A node reachable by two relationship types lands in the first one
      // seen; it can only occupy one position, and the alternative is
      // drawing it twice.
      if (!groups.get(child.type)!.includes(child.id)) groups.get(child.type)!.push(child.id)
    }
    // Group order is by type name, not by size: sorting by size would move
    // an entire wedge to a different side of the graph the moment one edge
    // is added, which is precisely the spatial memory this file exists to
    // preserve.
    const groupNames = [...groups.keys()].sort()
    for (const name of groupNames) {
      // Deterministic order within a wedge: high-degree first, then stable hash.
      groups.get(name)!.sort(
        (a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || stableKey(a) - stableKey(b),
      )
    }

    const total = groupNames.reduce((sum, name) => sum + groups.get(name)!.length, 0)
    // Dense fans push outward. At 20+ neighbours a fixed radius puts labels
    // on top of each other no matter how the angles are allocated.
    const crowding = 1 + Math.max(0, total - 8) * 0.045
    const radius = RING_STEP * (parent.depth + 1) * Math.min(crowding, 2.1)
    const arc = Math.max(MIN_ARC * total, Math.PI * 0.9)
    const span = Math.min(arc, Math.PI * 1.9)

    // Solve for the spacing rather than picking a fixed gap. A wedge only
    // reads as a wedge if the blank arc *between* groups is wider than the
    // spacing *inside* them — a constant gap fails that exactly when it
    // matters most, because dense fans squeeze members closer together
    // while the gap stays put. (Measured on a real 18-neighbour company:
    // 0.38 rad between members, 0.16 rad between groups, so the grouping
    // was invisible.)
    //
    // Walking the fan costs one `spacing` per step inside a group and
    // `GROUP_GAP_RATIO × spacing` per group boundary:
    //     span = (total − groups)·spacing + (groups − 1)·ratio·spacing
    const steps = (total - groupNames.length) + (groupNames.length - 1) * GROUP_GAP_RATIO
    const spacing = steps > 0 ? span / steps : 0
    const gap = spacing * GROUP_GAP_RATIO
    let cursor = current.heading - span / 2

    for (const name of groupNames) {
      const members = groups.get(name)!
      members.forEach((childId, index) => {
        const angle = cursor + spacing * index
        placed.set(childId, {
          x: parent.x + Math.cos(angle) * radius,
          y: parent.y + Math.sin(angle) * radius,
          depth: parent.depth + 1,
        })
        queue.push({ id: childId, heading: angle })
      })
      cursor += spacing * (members.length - 1) + gap
    }
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
