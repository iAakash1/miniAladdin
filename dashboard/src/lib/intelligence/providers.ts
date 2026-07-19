/* ============================================================
   Intelligence OS — initial providers.

   Each provider is independent and pluggable; registering them all is one
   call (`registerDefaultProviders`) made by the first client to mount.
   Sync tier: routes, glossaries (Learn), watchlists, recents.
   Async tier: company resolver (/api/screen), vault history.
   ============================================================ */

import { FACTOR_GLOSSARY } from '../factorGlossary'
import { METRIC_GLOSSARY } from '../metricGlossary'
import { STREET_GLOSSARY, TECHNICAL_GLOSSARY } from '../technicalGlossary'
import { fetchHistory } from '../persistence'
import { readWatchlistsSnapshot } from '../watchlists'
import type { Entity } from './entities'
import { readRecents, registerProvider } from './registry'
import { answerIntent, parseIntent } from './reasoning'

/* ---------- static: routes ---------- */

const ROUTE_ENTITIES: Entity[] = [
  { id: 'route:market', type: 'route', title: 'Market', subtitle: 'Macro dashboard', route: '/terminal', keywords: ['dashboard', 'macro', 'overview', 'home'] },
  { id: 'route:analyze', type: 'route', title: 'Analyze', subtitle: 'Run new research', route: '/terminal/analyze', keywords: ['research', 'run', 'new', 'ticker'] },
  { id: 'route:portfolio', type: 'route', title: 'Portfolio', subtitle: 'Watchlists & positions', route: '/terminal/portfolio', keywords: ['watchlist', 'positions', 'holdings'] },
  { id: 'route:vault', type: 'route', title: 'Research Vault', subtitle: 'Every analysis you have run', route: '/terminal/vault', keywords: ['history', 'saved', 'reports', 'archive'] },
  { id: 'route:vault-saved', type: 'route', title: 'Saved reports', subtitle: 'Bookmarked research', route: '/terminal/vault?view=saved', keywords: ['bookmarks', 'notes', 'saved'] },
  { id: 'route:validation', type: 'route', title: 'Validation', subtitle: 'Walk-forward model evaluation', route: '/terminal/validation', keywords: ['backtest', 'ic', 'calibration', 'model health'] },
  { id: 'route:methodology', type: 'route', title: 'Methodology', subtitle: 'How OmniSignal works', route: '/terminal/methodology', keywords: ['factors', 'pipeline', 'how it works', 'docs'] },
  { id: 'route:news', type: 'route', title: 'Market news', subtitle: 'Live aggregated feed', route: '/news', keywords: ['headlines', 'feed', 'stories'] },
]

/* ---------- static: glossaries (the Learn layer) ---------- */

function glossaryEntities(): Entity[] {
  const out: Entity[] = []
  const sources: Array<[string, Record<string, { label: string; short: string }>, string]> = [
    ['technical', TECHNICAL_GLOSSARY, '/terminal/methodology'],
    ['street', STREET_GLOSSARY, '/terminal/methodology'],
    ['metric', METRIC_GLOSSARY as never, '/terminal/validation'],
    ['factor', FACTOR_GLOSSARY as never, '/terminal/methodology'],
  ]
  for (const [source, glossary, route] of sources) {
    for (const [key, entry] of Object.entries(glossary)) {
      out.push({
        id: `glossary:${source}:${key}`,
        type: 'glossary',
        title: entry.label,
        subtitle: 'Learn',
        description: entry.short,
        route,
        keywords: [key.toLowerCase(), ...entry.label.toLowerCase().split(/[\s()/,]+/).filter(Boolean)],
        metadata: { source },
      })
    }
  }
  return out
}

/* ---------- registration ---------- */

let registered = false

/** Idempotent: the first client to mount wires the default provider set. */
export function registerDefaultProviders(): void {
  if (registered) return
  registered = true

  registerProvider({ id: 'routes', tier: 'sync', entities: () => ROUTE_ENTITIES })

  const glossary = glossaryEntities()
  registerProvider({ id: 'glossary', tier: 'sync', entities: () => glossary })

  registerProvider({
    id: 'watchlists',
    tier: 'sync',
    entities: () => {
      const lists = readWatchlistsSnapshot()
      const listEntities: Entity[] = lists.map((list) => ({
        id: `watchlist:${list.id}`,
        type: 'watchlist',
        title: list.name,
        subtitle: `${list.tickers.length} tickers`,
        route: '/terminal/portfolio',
        keywords: list.tickers.map((t) => t.toLowerCase()),
      }))
      const tickerEntities: Entity[] = lists.flatMap((list) =>
        list.tickers.map((ticker) => ({
          id: `company:${ticker}`,
          type: 'company' as const,
          title: ticker,
          subtitle: `In ${list.name}`,
          route: `/company/${encodeURIComponent(ticker)}`,
          keywords: [ticker.toLowerCase()],
        })),
      )
      return [...listEntities, ...tickerEntities]
    },
  })

  registerProvider({
    id: 'recents',
    tier: 'sync',
    entities: () => readRecents(),
  })

  registerProvider({
    id: 'companies',
    tier: 'async',
    entities: async (query) => {
      if (query.trim().length < 2) return []
      const res = await fetch(`/api/screen?q=${encodeURIComponent(query.trim())}`)
      if (!res.ok) return []
      const data = (await res.json()) as {
        results?: Array<{ symbol: string; name: string }>
        suggestions?: Array<{ symbol: string; name: string }>
      }
      const rows = (data.results?.length ? data.results : data.suggestions) ?? []
      return rows.slice(0, 8).map((row) => ({
        id: `company:${row.symbol}`,
        type: 'company' as const,
        title: row.symbol,
        subtitle: row.name,
        route: `/company/${encodeURIComponent(row.symbol)}`,
        keywords: [row.symbol.toLowerCase(), ...row.name.toLowerCase().split(/\s+/)],
      }))
    },
  })

  registerProvider({
    id: 'reasoning',
    tier: 'async',
    entities: async (query) => {
      const intent = parseIntent(query)
      if (!intent) return []
      try {
        return await answerIntent(intent)
      } catch {
        return [] // signed-out or persistence down — retrieval still works
      }
    },
  })

  registerProvider({
    id: 'vault',
    tier: 'async',
    entities: async (query) => {
      if (query.trim().length < 2) return []
      try {
        const page = await fetchHistory({ q: query.trim(), page: 1, pageSize: 6, sort: 'newest' })
        return page.items.map((item) => ({
          id: `vault:${item.id}`,
          type: 'vault' as const,
          title: `${item.ticker} — ${item.verdict}`,
          subtitle: new Date(item.created_at).toLocaleDateString(),
          route: `/terminal/vault?id=${encodeURIComponent(item.id)}`,
          keywords: [item.ticker.toLowerCase(), (item.company_name ?? '').toLowerCase()].filter(Boolean),
        }))
      } catch {
        return [] // signed-out or persistence unavailable — the surface degrades quietly
      }
    },
  })
}
