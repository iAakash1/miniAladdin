/**
 * The research object model.
 *
 * Every analytical thing in the product is one of a small number of kinds, and
 * each kind knows where it lives, how it is addressed, and what it can be
 * compared against. Encoding that here rather than in each workspace is what
 * lets search, the command palette, recents, pinning and the inspector all
 * operate on objects without any of them knowing about the others.
 *
 * The graph edges are declared, not inferred. A model's neighbours are its
 * experiment, its dataset, its features and its evidence, and that is a fact
 * about the research pipeline rather than about any particular payload.
 */

export type ObjectKind =
  | 'security'
  | 'factor'
  | 'signal'
  | 'model'
  | 'experiment'
  | 'dataset'
  | 'feature'
  | 'portfolio'
  | 'risk'
  | 'provider'
  | 'memo'
  | 'evidence'
  | 'method'

export interface ResearchObject {
  kind: ObjectKind
  /** Stable within a kind. Used for addressing and for dedupe in recents. */
  id: string
  label: string
  /** Short qualifier shown after the label in lists. */
  detail?: string
  /** Research state, when the object carries one. */
  state?: string
}

export interface KindMeta {
  kind: ObjectKind
  /** Plural, for section headers in search results. */
  plural: string
  /** Single letter shown in the object badge. */
  glyph: string
  /** Workspace this kind lives in. */
  workspace: string
  /** Route for one instance. */
  href: (id: string) => string
  /** Kinds this one links to, in pipeline order. */
  neighbours: ObjectKind[]
}

export const KINDS: Record<ObjectKind, KindMeta> = {
  dataset: {
    kind: 'dataset', plural: 'Datasets', glyph: 'D', workspace: 'Data',
    href: (id) => `/terminal/data?dataset=${encodeURIComponent(id)}`,
    neighbours: ['feature', 'provider'],
  },
  feature: {
    kind: 'feature', plural: 'Features', glyph: 'F', workspace: 'Data',
    href: (id) => `/terminal/data?feature=${encodeURIComponent(id)}`,
    neighbours: ['dataset', 'signal', 'model'],
  },
  factor: {
    kind: 'factor', plural: 'Factors', glyph: 'K', workspace: 'Factors',
    href: (id) => `/terminal/factorlab?factor=${encodeURIComponent(id)}`,
    neighbours: ['feature', 'signal'],
  },
  signal: {
    kind: 'signal', plural: 'Signals', glyph: 'S', workspace: 'Signals',
    href: (id) => `/terminal/signals?config=${encodeURIComponent(id)}`,
    neighbours: ['feature', 'model', 'experiment'],
  },
  model: {
    kind: 'model', plural: 'Models', glyph: 'M', workspace: 'Models',
    href: (id) => `/terminal/lab?model=${encodeURIComponent(id)}`,
    neighbours: ['feature', 'experiment', 'evidence', 'dataset'],
  },
  experiment: {
    kind: 'experiment', plural: 'Experiments', glyph: 'X', workspace: 'Experiments',
    href: (id) => `/terminal/experiments?id=${encodeURIComponent(id)}`,
    neighbours: ['model', 'dataset', 'evidence'],
  },
  evidence: {
    kind: 'evidence', plural: 'Evidence', glyph: 'E', workspace: 'Evidence',
    href: (id) => `/terminal/evidence?entry=${encodeURIComponent(id)}`,
    neighbours: ['model', 'experiment', 'method'],
  },
  portfolio: {
    kind: 'portfolio', plural: 'Portfolios', glyph: 'P', workspace: 'Book',
    href: () => '/terminal/book',
    neighbours: ['risk', 'model'],
  },
  risk: {
    kind: 'risk', plural: 'Risk measures', glyph: 'R', workspace: 'Risk',
    href: (id) => `/terminal/risk?measure=${encodeURIComponent(id)}`,
    neighbours: ['method', 'portfolio'],
  },
  security: {
    kind: 'security', plural: 'Securities', glyph: 'T', workspace: 'Securities',
    href: (id) => `/terminal/security?symbol=${encodeURIComponent(id)}`,
    neighbours: ['factor', 'portfolio'],
  },
  provider: {
    kind: 'provider', plural: 'Providers', glyph: 'V', workspace: 'Data',
    href: (id) => `/terminal/providers?provider=${encodeURIComponent(id)}`,
    neighbours: ['dataset'],
  },
  method: {
    kind: 'method', plural: 'Methodology', glyph: 'H', workspace: 'Handbook',
    href: (id) => `/terminal/handbook?measure=${encodeURIComponent(id)}`,
    neighbours: ['risk'],
  },
  memo: {
    kind: 'memo', plural: 'Memos', glyph: 'N', workspace: 'Memos',
    href: (id) => `/terminal/memos?memo=${encodeURIComponent(id)}`,
    neighbours: ['experiment', 'model', 'security'],
  },
}

export const KIND_ORDER: ObjectKind[] = [
  'security', 'factor', 'signal', 'model', 'experiment', 'evidence',
  'portfolio', 'risk', 'dataset', 'feature', 'provider', 'method', 'memo',
]

export function href(obj: ResearchObject): string {
  return KINDS[obj.kind].href(obj.id)
}

export function objectKey(obj: ResearchObject): string {
  return `${obj.kind}:${obj.id}`
}

/** Neighbours of an object, as navigable kind references. */
export function neighbours(kind: ObjectKind): KindMeta[] {
  return KINDS[kind].neighbours.map((k) => KINDS[k])
}

/**
 * Ranking for search. Prefix beats substring, shorter beats longer, and an
 * exact match always wins — a user typing a full ticker means that ticker.
 */
export function score(query: string, candidate: string): number {
  const q = query.trim().toLowerCase()
  const c = candidate.toLowerCase()
  if (!q) return 0
  if (c === q) return 1000
  if (c.startsWith(q)) return 500 - c.length
  const at = c.indexOf(q)
  if (at >= 0) return 200 - at - c.length * 0.1
  // Subsequence: "hgb" matches "hist_gradient_boosting".
  let i = 0
  for (const ch of c) {
    if (ch === q[i]) i += 1
    if (i === q.length) return 60 - c.length * 0.1
  }
  return -1
}
