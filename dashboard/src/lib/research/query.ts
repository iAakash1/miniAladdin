/**
 * Reading a search box as a research question.
 *
 * "HGB" is a name. "blocked models" is a question, and answering it with a
 * fuzzy match on the string "blocked models" finds nothing, because no object
 * is called that.
 *
 * Two vocabularies are already carried by every object in the product — its
 * kind and its research state — so a query naming either can be answered
 * exactly. What is left over is matched against names as before.
 *
 * The line this does not cross: nothing here invents a filter the objects
 * cannot support. There is no metric filtering, no threshold parsing, no
 * "experiments with high PBO", because an object in this index carries a kind,
 * an id, a label, a short detail and a state, and that is all. A search box
 * that appears to understand more than the index holds is worse than one that
 * plainly matches names — it fails silently and specifically, on the queries a
 * researcher would most want to trust.
 */

import { KINDS, type ObjectKind, type ResearchObject } from './objects'

/**
 * The states the interface itself can render.
 *
 * Recognised even when no object currently holds one: a query for "blocked
 * models" when nothing is blocked should return nothing, which is an answer.
 * Falling through to a name match on the word "blocked" would return an
 * arbitrary set of models and look like an answer, which is worse.
 */
const UI_STATES = [
  'live', 'recorded', 'stale', 'waking', 'unavailable',
  'blocked', 'experimental', 'candidate', 'production', 'unknown',
] as const

export type StateWord = string

export interface ParsedQuery {
  /** Kinds named in the query, by their singular or plural word. */
  kinds: ObjectKind[]
  /** Research states named in the query. */
  states: StateWord[]
  /** Everything else, for name matching. */
  text: string
  /** True when the query named a kind or a state and nothing else. */
  structural: boolean
}

/** Singular and plural word for each kind, lowercased. */
function kindWords(): Map<string, ObjectKind> {
  const map = new Map<string, ObjectKind>()
  for (const [kind, meta] of Object.entries(KINDS) as [ObjectKind, { plural: string }][]) {
    const plural = meta.plural.toLowerCase()
    map.set(plural, kind)
    map.set(kind.toLowerCase(), kind)
    // "Risk measures" → also match "measures".
    const last = plural.split(' ').pop()
    if (last && last !== plural) map.set(last, kind)
    if (plural.endsWith('s')) map.set(plural.slice(0, -1), kind)
  }
  return map
}

/**
 * Parse a query against the vocabulary that is actually in play.
 *
 * `present` is the set of states the current objects carry — which is the
 * registry's own vocabulary, not the interface's. Models arrive as
 * `experimental` and `retired`; neither word appears in the render states, and
 * a hardcoded list would have silently failed to understand either. Deriving
 * it is the same lesson as the destination registry: do not keep a second copy
 * of a vocabulary that already exists somewhere.
 */
export function parseQuery(raw: string, present: Iterable<string> = []): ParsedQuery {
  const words = raw.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const kw = kindWords()
  const vocabulary = new Set<string>([
    ...UI_STATES,
    ...[...present].map((s) => s.toLowerCase()),
  ])

  const kinds: ObjectKind[] = []
  const states: StateWord[] = []
  const rest: string[] = []

  for (const w of words) {
    const kind = kw.get(w)
    if (kind && !kinds.includes(kind)) { kinds.push(kind); continue }
    if (vocabulary.has(w) && !states.includes(w)) { states.push(w); continue }
    rest.push(w)
  }

  return {
    kinds,
    states,
    text: rest.join(' '),
    structural: (kinds.length > 0 || states.length > 0) && rest.length === 0,
  }
}

/**
 * Whether an object satisfies the structural half of a query.
 *
 * Kinds and states are each disjunctive within themselves and conjunctive
 * against each other: "blocked stale models" means a model that is either
 * blocked or stale, which is what a reader typing two states means.
 */
export function matchesStructure(o: ResearchObject, q: ParsedQuery): boolean {
  if (q.kinds.length && !q.kinds.includes(o.kind)) return false
  if (q.states.length) {
    const state = (o.state ?? '').toLowerCase()
    if (!q.states.some((s) => state === s)) return false
  }
  return true
}

/** How the palette should describe what it filtered on, for the result header. */
export function describeQuery(q: ParsedQuery): string | null {
  const parts: string[] = []
  if (q.states.length) parts.push(q.states.join(' or '))
  if (q.kinds.length) parts.push(q.kinds.map((k) => KINDS[k].plural.toLowerCase()).join(' and '))
  if (!parts.length) return null
  return parts.join(' ')
}
