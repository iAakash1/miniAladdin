/**
 * One research request per symbol, however many panels want it.
 *
 * `/api/research/:ticker` fans out across every configured vendor and takes
 * between twenty-five and sixty-five seconds. Three panels on the security page
 * need parts of it — the company profile, the filings, the ratio surface — and
 * three independent fetches would mean three fan-outs, three sets of vendor
 * rate-limit consumption, and three different arrival times for facts about
 * one company.
 *
 * So the request is shared. The first caller starts it; the rest join the
 * promise already in flight. A completed response is held briefly, because a
 * reader who opens AAPL, goes to MSFT and comes back should not pay the
 * minute again.
 *
 * The cache is deliberately small and deliberately short-lived. This is market
 * data: holding it for an hour would mean showing an hour-old company profile
 * beside a live price, which is the kind of quiet mismatch this codebase keeps
 * finding.
 */

export interface ResearchPayload {
  profile?: Record<string, unknown>
  ratios?: Record<string, unknown>
  ownership?: Record<string, unknown>
  filings?: unknown[]
  news_stream?: Record<string, unknown>
  [k: string]: unknown
}

interface Entry {
  /** Resolved payload, or the promise still fetching it. */
  promise: Promise<ResearchPayload>
  at: number
}

const cache = new Map<string, Entry>()

/** Five minutes. Long enough to make a return visit instant, short enough that
 *  a profile never sits far behind the price beside it. */
const TTL_MS = 5 * 60_000
/** A handful of symbols. This is a browsing session, not a database. */
const MAX = 8

function evict(): void {
  const now = Date.now()
  for (const [k, v] of cache) {
    if (now - v.at > TTL_MS) cache.delete(k)
  }
  while (cache.size > MAX) {
    const oldest = [...cache.entries()].sort((a, b) => a[1].at - b[1].at)[0]
    if (!oldest) break
    cache.delete(oldest[0])
  }
}

/**
 * Fetch a symbol's research payload, sharing one request across callers.
 *
 * Note what this deliberately does not do: it does not take an AbortSignal.
 * A shared request cannot be cancelled by one of its consumers without
 * breaking the others, and a caller that has navigated away simply ignores the
 * result. The alternative — a signal per caller — is how a second panel's
 * unmount cancels the first panel's data.
 */
export function fetchResearch(symbol: string): Promise<ResearchPayload> {
  const key = symbol.trim().toUpperCase()
  evict()

  const hit = cache.get(key)
  if (hit) return hit.promise

  const promise = fetch(`/api/research/${encodeURIComponent(key)}`)
    .then((r) => {
      if (!r.ok) throw new Error(`the research request returned ${r.status}`)
      return r.json() as Promise<ResearchPayload>
    })
    .catch((e: unknown) => {
      // A failure is not cached. The next panel to ask should get a fresh
      // attempt rather than a remembered error, and a transient vendor outage
      // should not persist for five minutes after it ends.
      cache.delete(key)
      throw e
    })

  cache.set(key, { promise, at: Date.now() })
  // Evicted after insertion as well as before it: checking only on the way in
  // leaves the cache one entry over its cap until the next call, which for the
  // last symbol of a session is forever.
  evict()
  return promise
}

/** Drop everything. Used by tests; there is no UI affordance for it. */
export function clearResearchCache(): void {
  cache.clear()
}

/** How many symbols are held. Exposed for the test that asserts sharing. */
export function researchCacheSize(): number {
  return cache.size
}
