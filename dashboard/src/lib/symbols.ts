/**
 * Symbols this browser has opened, and the watchlist it keeps.
 *
 * Deliberately keyed by ticker alone. The research history stores rich objects
 * — factors, models, experiments — which is right for research and wrong here:
 * AAPL must survive the research dataset being replaced, re-run or removed
 * entirely. A watchlist that forgets its names because an experiment was voided
 * is not a watchlist.
 *
 * Local to the browser, like the rest of this product's session state. Nothing
 * here reaches a server.
 */

const RECENT = 'ma.symbols.recent'
const WATCH = 'ma.symbols.watchlist'
const LIMIT = 12

function read(key: string): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(key)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    // A private window, or storage the browser refuses. An empty list is the
    // honest answer; it must not throw into a render.
    return []
  }
}

function write(key: string, list: string[]): void {
  if (typeof window === 'undefined') return
  try { window.localStorage.setItem(key, JSON.stringify(list)) } catch { /* see read */ }
  cache.delete(key)
  listeners.forEach((fn) => fn())
}

/* ── subscription ────────────────────────────────────────────────────────
   Read through useSyncExternalStore rather than copied into component state
   on mount. A snapshot must be referentially stable between reads or React
   re-renders forever, so parsed lists are cached and the cache is dropped only
   on write. */

const listeners = new Set<() => void>()
const cache = new Map<string, string[]>()
const EMPTY: string[] = []

function snapshot(key: string): string[] {
  const hit = cache.get(key)
  if (hit) return hit
  const list = read(key)
  cache.set(key, list)
  return list
}

export function subscribeSymbols(fn: () => void): () => void {
  listeners.add(fn)
  // Another tab writing the same key is a real change to this browser's state.
  const onStorage = (e: StorageEvent) => {
    if (e.key === RECENT || e.key === WATCH) { cache.clear(); fn() }
  }
  window.addEventListener('storage', onStorage)
  return () => { listeners.delete(fn); window.removeEventListener('storage', onStorage) }
}

export const recentSnapshot = (): string[] => snapshot(RECENT)
export const watchSnapshot = (): string[] => snapshot(WATCH)
/** Nothing is stored on the server, and the reference must not change. */
export const emptySnapshot = (): string[] => EMPTY

export function recentSymbols(): string[] {
  return read(RECENT)
}

/** Most recent first, no duplicates, capped. */
export function rememberSymbol(symbol: string): void {
  const s = symbol.trim().toUpperCase()
  if (!s) return
  write(RECENT, [s, ...read(RECENT).filter((x) => x !== s)].slice(0, LIMIT))
}

export function watchlist(): string[] {
  return read(WATCH)
}

export function isWatched(symbol: string): boolean {
  return read(WATCH).includes(symbol.trim().toUpperCase())
}

/** Add or remove, returning the list as it now stands. */
export function toggleWatch(symbol: string): string[] {
  const s = symbol.trim().toUpperCase()
  if (!s) return read(WATCH)
  const current = read(WATCH)
  const next = current.includes(s) ? current.filter((x) => x !== s) : [...current, s]
  write(WATCH, next)
  return next
}
