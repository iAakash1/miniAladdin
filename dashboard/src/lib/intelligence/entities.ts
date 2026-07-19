/* ============================================================
   Intelligence OS — the universal entity model.

   Every addressable thing in OmniSignal (a company, a route, a glossary
   topic, a vault entry, a watchlist…) is expressed as one Entity shape.
   Surfaces (⌘K palette, header search, cross-links, future clients)
   consume entities; they never know which provider produced one.

   This module is pure types + pure functions — no React, no I/O — so the
   ranking core is unit-testable in node and reusable by any client.
   ============================================================ */

export type EntityType =
  | 'company'
  | 'route'
  | 'glossary'
  | 'vault'
  | 'watchlist'
  | 'holding'
  | 'indicator'
  | 'metric'
  | 'macro'
  | 'news'

export interface Entity {
  /** Stable, unique across the registry: `${type}:${key}`. */
  id: string
  type: EntityType
  title: string
  subtitle?: string
  description?: string
  /** Where Enter takes you. Every entity is addressable. */
  route: string
  /** Lowercased match terms beyond the title (aliases, tags, tickers). */
  keywords: string[]
  /** ids of related entities (cross-link surfaces read these). */
  relationships?: string[]
  /** Extra verbs beyond "open" — future clients (context menus) read these. */
  actions?: Array<{ label: string; route: string }>
  metadata?: Record<string, string | number | null>
}

/** Human labels for grouped result headers, in display order. */
export const TYPE_LABELS: Record<EntityType, string> = {
  company: 'Companies',
  route: 'Go to',
  vault: 'Research Vault',
  watchlist: 'Watchlists',
  holding: 'Portfolio',
  glossary: 'Learn',
  indicator: 'Indicators',
  metric: 'Metrics',
  macro: 'Macro',
  news: 'News',
}

export const TYPE_ORDER: EntityType[] = [
  'company', 'route', 'vault', 'watchlist', 'holding',
  'glossary', 'indicator', 'metric', 'macro', 'news',
]

/* ---------- ranking (pure, deterministic) ---------- */

const TYPE_WEIGHT: Partial<Record<EntityType, number>> = {
  company: 30,
  route: 24,
  watchlist: 18,
  holding: 18,
  vault: 14,
  glossary: 10,
}

/** Subsequence fuzzy match: every query char appears in order. */
export function fuzzyIncludes(haystack: string, needle: string): boolean {
  let i = 0
  for (const ch of haystack) {
    if (ch === needle[i]) i++
    if (i === needle.length) return true
  }
  return needle.length === 0
}

export interface Scored {
  entity: Entity
  score: number
}

/**
 * Deterministic relevance: exact-ticker/title > title prefix > word-start >
 * substring > keyword > fuzzy subsequence, weighted by entity type and a
 * caller-supplied recency boost. Returns [] for empty queries — providers
 * decide their own empty-state suggestions.
 */
export function rankEntities(
  query: string,
  entities: Entity[],
  recentIds: string[] = [],
  limit = 40,
): Scored[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const out: Scored[] = []
  for (const entity of entities) {
    const title = entity.title.toLowerCase()
    let score = 0
    if (title === q) score = 100
    else if (entity.keywords.includes(q)) score = 90
    else if (title.startsWith(q)) score = 80
    else if (title.split(/\s+/).some((w) => w.startsWith(q))) score = 60
    else if (title.includes(q)) score = 45
    else if (entity.keywords.some((k) => k.startsWith(q))) score = 40
    else if (entity.keywords.some((k) => k.includes(q))) score = 30
    else if (q.length >= 3 && fuzzyIncludes(title, q)) score = 15
    if (score === 0) continue
    score += TYPE_WEIGHT[entity.type] ?? 0
    const recentIndex = recentIds.indexOf(entity.id)
    if (recentIndex >= 0) score += Math.max(0, 12 - recentIndex * 2)
    out.push({ entity, score })
  }
  out.sort(
    (a, b) => b.score - a.score || a.entity.title.localeCompare(b.entity.title),
  )
  return out.slice(0, limit)
}

/** Stable grouping for display: TYPE_ORDER first, score order within type. */
export function groupByType(scored: Scored[]): Array<{ type: EntityType; label: string; items: Entity[] }> {
  const buckets = new Map<EntityType, Entity[]>()
  for (const { entity } of scored) {
    const bucket = buckets.get(entity.type) ?? []
    bucket.push(entity)
    buckets.set(entity.type, bucket)
  }
  return TYPE_ORDER.filter((t) => buckets.has(t)).map((t) => ({
    type: t,
    label: TYPE_LABELS[t],
    items: buckets.get(t)!,
  }))
}
