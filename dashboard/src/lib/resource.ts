/**
 * One request per resource, shared by every component that wants it.
 *
 * Six components read the model registry. Eight read an experiment artifact.
 * Two read the market dashboard, which takes twenty seconds. Each was calling
 * `fetch` directly, so opening a workspace could issue the same request three
 * times and hold three copies of the answer, arriving at three moments.
 *
 * This is the general form of the research cache: a keyed, in-flight-shared,
 * TTL-bounded read. Fincept routes everything through a topic-keyed hub with a
 * per-topic refresh policy; that policy idea is the important half, because
 * the right lifetime for a quote and for a methodology handbook differ by
 * three orders of magnitude.
 *
 * What it deliberately is not: a state manager. There is no store, no
 * selectors, no devtools. Components still own their own view state. This
 * solves one problem — the same bytes fetched more than once — and stops.
 */

/** How long an answer may be reused, by the kind of thing it is. */
export const POLICY = {
  /** Prices. Never cached across a refresh; the quote hub owns liveness. */
  live: 0,
  /** Market snapshots. Expensive to build, and a minute old is still useful. */
  snapshot: 60_000,
  /** Registries and artifacts. They change when someone runs an experiment. */
  artifact: 5 * 60_000,
  /** Generated documentation. Changes when the engine changes. */
  reference: 15 * 60_000,
} as const

export type Policy = keyof typeof POLICY

interface Entry {
  promise: Promise<unknown>
  at: number
  ttl: number
}

export interface ResourceOptions {
  /** Request implementation. Public resources keep the browser's fetch. */
  fetcher?: (url: string, init?: RequestInit) => Promise<Response>
  /**
   * Cache identity. `undefined` keeps the historical URL key; `null` disables
   * caching. Private callers must supply a session-scoped key rather than
   * allowing an authenticated response to live under a public URL-only key.
   */
  cacheKey?: string | null
}

const cache = new Map<string, Entry>()
const MAX = 24

function evict(): void {
  const now = Date.now()
  for (const [k, v] of cache) {
    if (now - v.at > v.ttl) cache.delete(k)
  }
  while (cache.size > MAX) {
    const oldest = [...cache.entries()].sort((a, b) => a[1].at - b[1].at)[0]
    if (!oldest) break
    cache.delete(oldest[0])
  }
}

/**
 * Read a JSON resource, sharing one request across concurrent callers.
 *
 * A failure is never cached: a transient vendor outage must not persist for
 * the policy's lifetime after it has ended.
 */
export function readResource<T>(
  url: string,
  policy: Policy = 'artifact',
  options: ResourceOptions = {},
): Promise<T> {
  evict()
  const ttl = POLICY[policy]
  const key = options.cacheKey === undefined ? url : options.cacheKey
  const fetcher = options.fetcher ?? fetch

  if (ttl > 0 && key !== null) {
    const hit = cache.get(key)
    if (hit) return hit.promise as Promise<T>
  }

  const promise = fetcher(url)
    .then(async (r) => {
      if (!r.ok) {
        let detail: string | undefined
        try {
          const body = await r.json() as { detail?: unknown }
          if (typeof body.detail === 'string') detail = body.detail
        } catch { /* an HTML/text error still has a useful status */ }
        throw new ResourceError(url, r.status, detail)
      }
      return r.json() as Promise<T>
    })
    .catch((e: unknown) => {
      if (key !== null) cache.delete(key)
      throw e
    })

  if (ttl > 0 && key !== null) {
    cache.set(key, { promise, at: Date.now(), ttl })
    evict()
  }
  return promise
}

export class ResourceError extends Error {
  constructor(
    public readonly url: string,
    public readonly status: number,
    detail?: string,
  ) {
    super(detail ?? `${url} returned ${status}`)
    this.name = 'ResourceError'
  }
}

export function clearResourceCache(): void {
  cache.clear()
}

/** Remove one cache namespace without flushing unrelated public resources. */
export function clearResourceCachePrefix(prefix: string): void {
  for (const key of cache.keys()) {
    if (key.startsWith(prefix)) cache.delete(key)
  }
}

export function resourceCacheSize(): number {
  return cache.size
}
