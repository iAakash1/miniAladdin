/* ============================================================
   News aggregation: fetch all feeds, dedupe, classify, cache.
   - Per-feed 6s timeout; failures degrade gracefully.
   - In-memory cache (5 min TTL) with in-flight dedupe, plus
     CDN caching via response headers set in the route handler.
   ============================================================ */

import { classify } from './classify'
import { parseFeedXml } from './parse'
import { FEED_SOURCES } from './sources'
import type { NewsCategory, NewsItem, NewsResponse } from '../types'

const CACHE_TTL_MS = 5 * 60 * 1000
const FEED_TIMEOUT_MS = 6_000
const MAX_ITEMS = 400

interface Aggregated {
  items: NewsItem[]
  sources: Array<{ name: string; ok: boolean }>
  updatedAt: string
}

let cache: { data: Aggregated; expires: number } | null = null
let inflight: Promise<Aggregated> | null = null

function hashId(input: string): string {
  let h = 5381
  for (let i = 0; i < input.length; i++) h = ((h << 5) + h + input.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

/** Key used to spot the same story syndicated across feeds. */
function dedupeKey(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
}

async function fetchFeed(url: string): Promise<string> {
  const res = await fetch(url, {
    signal: AbortSignal.timeout(FEED_TIMEOUT_MS),
    headers: {
      'User-Agent': 'Mozilla/5.0 (compatible; OmniSignalNews/2.0; +https://mini-aladding.vercel.app)',
      Accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8',
    },
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.text()
}

async function aggregate(): Promise<Aggregated> {
  const results = await Promise.allSettled(
    FEED_SOURCES.map(async (source) => {
      const xml = await fetchFeed(source.url)
      return { source, items: parseFeedXml(xml) }
    }),
  )

  const seen = new Set<string>()
  const items: NewsItem[] = []
  // Track feed health per unique source name (a source is ok if any of its feeds succeeded)
  const health = new Map<string, boolean>()

  results.forEach((result, i) => {
    const name = FEED_SOURCES[i].name
    const ok = result.status === 'fulfilled' && result.value.items.length > 0
    health.set(name, (health.get(name) ?? false) || ok)
    if (result.status !== 'fulfilled') return

    for (const parsed of result.value.items) {
      const key = dedupeKey(parsed.title)
      if (!key || seen.has(key)) continue
      seen.add(key)
      items.push({
        id: hashId(parsed.url + parsed.title),
        title: parsed.title,
        summary: parsed.summary,
        url: parsed.url,
        source: result.value.source.name,
        category: classify(parsed.title, parsed.summary, result.value.source.defaultCategory),
        publishedAt: parsed.publishedAt,
        image: parsed.image,
        author: parsed.author,
      })
    }
  })

  items.sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt))

  return {
    items: items.slice(0, MAX_ITEMS),
    sources: [...health.entries()].map(([name, ok]) => ({ name, ok })),
    updatedAt: new Date().toISOString(),
  }
}

export async function getAggregatedNews(): Promise<Aggregated> {
  const now = Date.now()
  if (cache && cache.expires > now) return cache.data
  if (inflight) return inflight

  inflight = aggregate()
    .then((data) => {
      // Only cache non-empty results so a transient total failure retries soon.
      if (data.items.length > 0) cache = { data, expires: Date.now() + CACHE_TTL_MS }
      return data
    })
    .finally(() => {
      inflight = null
    })

  return inflight
}

export interface NewsQuery {
  q?: string
  category?: NewsCategory | 'all'
  page?: number
  pageSize?: number
}

export async function queryNews(query: NewsQuery): Promise<NewsResponse> {
  const { items, sources, updatedAt } = await getAggregatedNews()

  let filtered = items
  if (query.category && query.category !== 'all') {
    filtered = filtered.filter((i) => i.category === query.category)
  }
  if (query.q) {
    const q = query.q.toLowerCase().trim()
    if (q) {
      filtered = filtered.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          i.summary.toLowerCase().includes(q) ||
          i.source.toLowerCase().includes(q),
      )
    }
  }

  const pageSize = Math.min(Math.max(query.pageSize ?? 20, 1), 50)
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const page = Math.min(Math.max(query.page ?? 1, 1), totalPages)

  return {
    items: filtered.slice((page - 1) * pageSize, page * pageSize),
    total: filtered.length,
    page,
    pageSize,
    totalPages,
    updatedAt,
    sources,
  }
}

/** Latest N items for the landing-page preview (server-side). */
export async function getNewsPreview(count: number): Promise<NewsItem[]> {
  try {
    const { items } = await getAggregatedNews()
    return items.slice(0, count)
  } catch {
    return []
  }
}
