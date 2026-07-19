/* ============================================================
   Intelligence OS — related entities (cross-links).

   Given research context, compose the entities that naturally connect to
   it: the Learn topics for exactly the indicators this report rendered,
   the watchlists that hold the ticker, the stored runs behind it, and the
   what-changed answer when two runs exist. Pure composition over existing
   sources — no new data, no duplicated logic, no dead ends.

   The sync half is pure and unit-tested; the async half reuses the same
   persistence calls the reasoning provider uses.
   ============================================================ */

import { fetchHistory } from '../persistence'
import { STREET_GLOSSARY, TECHNICAL_GLOSSARY } from '../technicalGlossary'
import type { Watchlist } from '../watchlists'
import type { Entity } from './entities'

/** Learn topics for the indicator keys a report actually rendered —
 *  curiosity links exactly where it occurs. Pure. */
export function relatedLearnTopics(indicatorKeys: string[], hasStreet: boolean, limit = 6): Entity[] {
  const out: Entity[] = []
  for (const key of indicatorKeys) {
    const entry = TECHNICAL_GLOSSARY[key]
    if (!entry) continue
    out.push({
      id: `glossary:technical:${key}`,
      type: 'glossary',
      title: entry.label,
      subtitle: 'Learn',
      description: entry.short,
      route: '/terminal/methodology',
      keywords: [key],
    })
  }
  if (hasStreet) {
    for (const [key, entry] of Object.entries(STREET_GLOSSARY)) {
      out.push({
        id: `glossary:street:${key}`,
        type: 'glossary',
        title: entry.label,
        subtitle: 'Learn',
        description: entry.short,
        route: '/terminal/methodology',
        keywords: [key],
      })
    }
  }
  return out.slice(0, limit)
}

/** Watchlists that already hold the ticker. Pure. */
export function relatedWatchlists(ticker: string, lists: Watchlist[]): Entity[] {
  const symbol = ticker.toUpperCase()
  return lists
    .filter((list) => list.tickers.includes(symbol))
    .map((list) => ({
      id: `watchlist:${list.id}`,
      type: 'watchlist' as const,
      title: list.name,
      subtitle: `Holds ${symbol}`,
      route: '/terminal/portfolio',
      keywords: [],
    }))
}

/** Stored research behind this ticker: recent vault runs, plus the
 *  what-changed comparison when two runs exist. Same pipelines the
 *  reasoning provider composes — one logic, two clients. */
export async function relatedResearch(ticker: string): Promise<Entity[]> {
  try {
    const page = await fetchHistory({ ticker, page: 1, pageSize: 3, sort: 'newest' })
    const runs: Entity[] = page.items.map((item) => ({
      id: `vault:${item.id}`,
      type: 'vault' as const,
      title: `${item.ticker} — ${item.verdict}`,
      subtitle: new Date(item.created_at).toLocaleDateString(),
      route: `/terminal/vault?id=${encodeURIComponent(item.id)}`,
      keywords: [],
    }))
    if (page.items.length >= 2) {
      runs.unshift({
        id: `answer:changed:${ticker}`,
        type: 'answer',
        title: `What changed for ${ticker}`,
        subtitle: 'Factor deltas between your last two runs',
        route: `/terminal/vault?compare=${encodeURIComponent(page.items[1].id)},${encodeURIComponent(page.items[0].id)}`,
        keywords: [],
      })
    }
    return runs
  } catch {
    return [] // signed-out or persistence unavailable — the section hides
  }
}
