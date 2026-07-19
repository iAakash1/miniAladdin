/* ============================================================
   Knowledge client — typed access to /api/knowledge/{ticker}.

   The backend merges SEC + Wikidata into one deduplicated graph; this
   module only types and fetches it, then adapts graph members into
   Intelligence OS entities so the ecosystem participates in ⌘K, Related
   and every future surface without page-specific logic.
   ============================================================ */

import type { Entity } from './intelligence/entities'

export interface EcosystemMember {
  id: string
  label: string
  type: string
  route: string | null
  edges: string[]
  confidence: number
  provider: string
}

export interface EcosystemGroup {
  key: string
  label: string
  members: EcosystemMember[]
}

export interface KnowledgeTimelineEvent {
  id: string
  date: string
  kind: string
  title: string
  detail: string | null
  tone: 'pos' | 'neg' | 'neutral'
  source: { provider: string; title: string; url: string | null; document_type: string | null } | null
}

export interface KnowledgeFinding {
  id: string
  label: string
  text: string
  tone: 'pos' | 'neg' | 'neutral'
  evidence: Array<{
    id: string
    excerpt: string
    doc_section: string | null
    source: { provider: string; title: string; url: string | null; published_at: string | null }
  }>
}

export interface KnowledgeClaim {
  id: string
  statement: string
  confidence: number
  evidence: Array<{
    id: string
    excerpt: string
    source: { provider: string; title: string; url: string | null }
  }>
}

export interface CompanyKnowledge {
  symbol: string
  ecosystem: EcosystemGroup[]
  claims: KnowledgeClaim[]
  timeline: KnowledgeTimelineEvent[]
  findings: KnowledgeFinding[]
  graph: { nodes: number; edges: number; providers: string[] }
}

/** Human labels for edge types — the graph's vocabulary, shown as roles. */
export const EDGE_LABELS: Record<string, string> = {
  ceo_of: 'CEO',
  founded: 'Founder',
  board_member_of: 'Board',
  parent_of: 'Subsidiary',
  subsidiary_of: 'Parent',
  owns: 'Owns',
  acquired: 'Acquired',
  competes_with: 'Competitor',
  belongs_to: 'Industry',
  headquartered_in: 'Location',
  listed_on: 'Exchange',
  produces: 'Product',
  supplies: 'Supplier',
}

export async function fetchKnowledge(ticker: string): Promise<CompanyKnowledge | null> {
  try {
    const res = await fetch(`/api/knowledge/${encodeURIComponent(ticker)}`)
    if (!res.ok) return null
    return (await res.json()) as CompanyKnowledge
  } catch {
    return null // research is always optional — analysis never depends on it
  }
}

/** Graph members → Intelligence OS entities. Only addressable members
 *  (those with a route) become navigable entities; the rest stay as
 *  context on the page rather than becoming dead-end search results. */
export function knowledgeEntities(knowledge: CompanyKnowledge): Entity[] {
  const out: Entity[] = []
  for (const group of knowledge.ecosystem) {
    for (const member of group.members) {
      if (!member.route) continue
      out.push({
        id: member.id,
        type: 'company',
        title: member.label,
        subtitle: `${group.label} · ${knowledge.symbol}`,
        route: member.route,
        keywords: [member.label.toLowerCase()],
        relationships: [`company:${knowledge.symbol}`],
      })
    }
  }
  return out
}
