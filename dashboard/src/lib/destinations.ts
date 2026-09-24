/**
 * Every place a reader can go, declared once.
 *
 * The rail, the command palette, the `g`-chords and the workspace tabs all
 * read this registry, so they cannot disagree about where something lives.
 *
 * The rail shows destinations only. A destination may own several views —
 * related pages that answer the same question from different angles — and
 * those appear as tabs in the workspace header rather than as more rail
 * entries. Every route stays reachable; the rail stays short.
 */

import type { IconName } from '@/components/shell/Icon'

export interface View {
  href: string
  label: string
  /** What this view answers, for the palette. */
  answers: string
}

export interface Destination {
  /** Canonical route (also the first view). */
  href: string
  label: string
  icon: IconName
  /** The letter that follows `g`. Unique across the registry. */
  key: string
  answers: string
  /** Related pages shown as tabs in the workspace header. */
  views?: View[]
}

export interface DestinationGroup {
  group: string
  items: Destination[]
}

export const DESTINATIONS: DestinationGroup[] = [
  {
    group: 'Research',
    items: [
      { href: '/terminal/command', label: 'Home', icon: 'home', key: 'h', answers: 'market state, your lists and recent research' },
      { href: '/explore', label: 'Screener', icon: 'screen', key: 's', answers: 'rank and filter the covered universe' },
      { href: '/terminal/market', label: 'Markets', icon: 'market', key: 'm', answers: 'indices, breadth, sectors and scheduled events' },
      {
        href: '/terminal/graph', label: 'Knowledge graph', icon: 'graph', key: 'k',
        answers: 'relationships between companies, people and filings',
        views: [
          { href: '/terminal/graph', label: 'Graph', answers: 'entities and relationships around one company' },
          { href: '/terminal/graph/explore', label: 'Path explorer', answers: 'how two entities connect' },
          { href: '/terminal/relationships', label: 'Research links', answers: 'how research objects relate' },
        ],
      },
      {
        href: '/terminal/vault', label: 'Research log', icon: 'log', key: 'l',
        answers: 'saved reports, sessions, memos and history',
        views: [
          { href: '/terminal/vault', label: 'Saved research', answers: 'reports you kept and past runs' },
          { href: '/terminal/sessions', label: 'Sessions', answers: 'investigations and their notes' },
          { href: '/terminal/memos', label: 'Memos', answers: 'what you concluded, and what it rests on' },
          { href: '/terminal/timeline', label: 'Timeline', answers: 'what was recorded, in order' },
        ],
      },
    ],
  },
  {
    group: 'Portfolio',
    items: [
      { href: '/terminal/portfolio', label: 'Watchlists', icon: 'list', key: 'w', answers: 'lists you follow, positions and exposure' },
      { href: '/terminal/paper', label: 'Paper trading', icon: 'paper', key: 't', answers: 'a simulated account — no real money' },
    ],
  },
  {
    group: 'Labs',
    items: [
      {
        href: '/terminal/lab', label: 'Model Lab', icon: 'model', key: 'd',
        answers: 'declared model universe, nested selection and promotion governance',
        views: [
          { href: '/terminal/lab', label: 'Model Lab', answers: 'the declared universe and outer-fold evidence' },
          { href: '/terminal/evidence', label: 'Governance', answers: 'registry, holdout and why nothing is promoted' },
          { href: '/terminal/gates', label: 'Promotion gates', answers: 'which gate blocks promotion' },
          { href: '/terminal/calibration', label: 'Calibration', answers: 'whether a score means what it says' },
        ],
      },
      {
        href: '/terminal/experiments', label: 'Quant Lab', icon: 'flask', key: 'q',
        answers: 'experiment record, signal search and portfolio research',
        views: [
          { href: '/terminal/experiments', label: 'Experiments', answers: 'the research record, including void runs' },
          { href: '/terminal/signals', label: 'Signals', answers: 'what the search found, and what it cost in significance' },
          { href: '/terminal/diff', label: 'Run diff', answers: 'what changed between two experiments' },
          { href: '/terminal/book', label: 'Book', answers: 'research portfolio holdings and costs' },
          { href: '/terminal/risk', label: 'Risk', answers: 'risk under four assumptions' },
          { href: '/terminal/covariance', label: 'Covariance', answers: 'how the estimators disagree' },
          { href: '/terminal/performance', label: 'Performance', answers: 'what the strategy did, gross and net' },
          { href: '/terminal/compare', label: 'Compare', answers: 'one object against another' },
        ],
      },
      {
        href: '/terminal/factorlab', label: 'Factor Lab', icon: 'factor', key: 'f',
        answers: 'factor evaluations, ablations and dataset contracts',
        views: [
          { href: '/terminal/factorlab', label: 'Factor Lab', answers: 'which factors survive the overlap correction' },
          { href: '/terminal/data', label: 'Datasets', answers: 'dataset and feature contracts' },
        ],
      },
    ],
  },
  {
    group: 'System',
    items: [
      { href: '/terminal/providers', label: 'Providers', icon: 'providers', key: 'p', answers: 'data vendors, capability coverage and health' },
      {
        href: '/terminal/provenance', label: 'Provenance', icon: 'provenance', key: 'v',
        answers: 'where a result came from, and where trust stopped',
        views: [
          { href: '/terminal/provenance', label: 'Lineage', answers: 'chains from data to decision' },
          { href: '/terminal/agents', label: 'Agent runs', answers: 'how one analysis executed, claim by claim' },
        ],
      },
      {
        href: '/terminal/methodology', label: 'Methodology', icon: 'book', key: 'e',
        answers: 'how every number is computed',
        views: [
          { href: '/terminal/methodology', label: 'Methodology', answers: 'how the numbers are made' },
          { href: '/terminal/handbook', label: 'Handbook', answers: 'every measure, its method and failure modes' },
          { href: '/terminal/research', label: 'Architecture', answers: 'the three accountable layers' },
        ],
      },
      {
        href: '/terminal/system', label: 'System health', icon: 'health', key: 'u',
        answers: 'what is ready, degraded, blocked or absent',
        views: [
          { href: '/terminal/system', label: 'Health', answers: 'component readiness' },
          { href: '/terminal/admin', label: 'Operations', answers: 'deployment posture and diagnostics' },
        ],
      },
    ],
  },
]

/** Flat view, in navigation order. */
export const ALL_DESTINATIONS: Destination[] = DESTINATIONS.flatMap((g) => g.items)

/** Every view of every destination, for the palette. */
export const ALL_VIEWS: Array<View & { destination: Destination }> = ALL_DESTINATIONS.flatMap(
  (d) => (d.views ?? [{ href: d.href, label: d.label, answers: d.answers }]).map((v) => ({ ...v, destination: d })),
)

/** The `g`-chord map, derived rather than restated. */
export const GOTO: Record<string, string> = Object.fromEntries(
  ALL_DESTINATIONS.map((d) => [d.key, d.href]),
)

function matches(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`)
}

/**
 * The destination a route belongs to. Views are checked before the canonical
 * routes so that `/terminal/graph/explore` resolves to its view rather than
 * to whichever destination has the shortest matching prefix.
 */
export function destinationAt(pathname: string): Destination | undefined {
  let best: { d: Destination; len: number } | undefined
  for (const d of ALL_DESTINATIONS) {
    for (const href of [d.href, ...(d.views ?? []).map((v) => v.href)]) {
      if (matches(pathname, href) && (!best || href.length > best.len)) best = { d, len: href.length }
    }
  }
  return best?.d
}

/** The view a route is on, within its destination. */
export function viewAt(pathname: string): View | undefined {
  const d = destinationAt(pathname)
  if (!d?.views) return undefined
  let best: View | undefined
  for (const v of d.views) {
    if (matches(pathname, v.href) && (!best || v.href.length > best.href.length)) best = v
  }
  return best
}

/** The group a route belongs to, or null for a route outside the registry. */
export function groupOf(pathname: string): string | null {
  const d = destinationAt(pathname)
  if (!d) return null
  return DESTINATIONS.find((g) => g.items.includes(d))?.group ?? null
}

/** One destination by its chord letter. */
export function destinationFor(key: string): Destination | undefined {
  return ALL_DESTINATIONS.find((d) => d.key === key)
}
