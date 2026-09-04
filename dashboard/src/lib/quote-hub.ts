/**
 * One quote per symbol, however many panels are showing it.
 *
 * The home screen had two panels asking for overlapping symbol sets — the
 * watchlist wanted AAPL, MSFT, NVDA, TSLA and the recents list wanted MSFT,
 * AAPL, NVDA — as two independent requests on independent timers. That is two
 * fan-outs across the vendor layer for one set of facts, and worse: the same
 * symbol could hold two different prices on one screen, because the two
 * requests landed at different moments and neither knew about the other.
 *
 * Both Fincept and OpenBB converge on the same answer from different
 * directions — one fetch per topic with subscribers fanning out free, and a
 * single standard model behind many providers. This is that idea at the size
 * this product needs it.
 *
 * A panel subscribes to the symbols it displays. The hub unions every
 * subscription into one request, refreshes on one timer, and pushes the result
 * to everyone. Unsubscribing narrows the union again.
 *
 * What it deliberately does not do is dedupe across *time*: a quote is a live
 * figure, and holding one for minutes to save a request would put a stale
 * price under a LIVE badge. The cache exists to collapse concurrent readers,
 * not to avoid refreshing.
 */

import type { Quote } from './security'

type Listener = () => void

interface State {
  quotes: Record<string, Quote>
  /** When the last successful read completed. Null before the first. */
  at: string | null
  /** Why the last read failed, if it did. Cleared by the next success. */
  error: string | null
  loading: boolean
}

const listeners = new Set<Listener>()
/** symbol → how many panels are currently showing it. */
const demand = new Map<string, number>()

let state: State = { quotes: {}, at: null, error: null, loading: false }
let timer: ReturnType<typeof setInterval> | null = null
let inFlight: AbortController | null = null

/** Thirty seconds. Fast enough that a price is never minutes behind without
 *  saying so, slow enough to be polite to a rate-limited vendor. */
const REFRESH_MS = 30_000

function emit(): void {
  listeners.forEach((fn) => fn())
}

function symbols(): string[] {
  return [...demand.keys()].sort()
}

async function read(): Promise<void> {
  const wanted = symbols()
  if (!wanted.length) return

  // One request at a time. A refresh that fires while the previous is still
  // running would produce exactly the overlap this hub exists to remove.
  inFlight?.abort()
  const controller = new AbortController()
  inFlight = controller

  state = { ...state, loading: true }
  emit()

  try {
    const r = await fetch(
      `/api/quotes?symbols=${encodeURIComponent(wanted.join(','))}`,
      { signal: controller.signal },
    )
    if (!r.ok) throw new Error(`the quote request returned ${r.status}`)
    const d: { quotes?: Record<string, Quote> } = await r.json()
    state = {
      quotes: d.quotes ?? {},
      at: new Date().toISOString(),
      error: null,
      loading: false,
    }
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    // The previous quotes are kept rather than blanked. A panel that showed a
    // price a moment ago should not empty itself because one refresh failed —
    // but the error travels with them, so the surface can say the figures are
    // no longer current.
    state = { ...state, error: (e as Error).message, loading: false }
  } finally {
    if (inFlight === controller) inFlight = null
  }
  emit()
}

function start(): void {
  if (timer !== null) return
  // Plain setInterval rather than window.setInterval: this module is imported
  // during server render and by tests, and neither has a window. The refresh
  // is meaningless in both, but the import must not throw.
  timer = setInterval(() => { void read() }, REFRESH_MS)
}

function stop(): void {
  if (timer === null) return
  clearInterval(timer)
  timer = null
  inFlight?.abort()
  inFlight = null
}

/**
 * Register interest in a set of symbols. Returns the unsubscribe.
 *
 * Reference-counted: two panels showing AAPL keep one entry, and the symbol
 * only leaves the request when the last of them goes.
 */
export function subscribeQuotes(wanted: string[], onChange: Listener): () => void {
  const clean = [...new Set(wanted.map((s) => s.trim().toUpperCase()).filter(Boolean))]
  let added = false

  for (const s of clean) {
    const n = demand.get(s) ?? 0
    demand.set(s, n + 1)
    if (n === 0) added = true
  }
  listeners.add(onChange)
  start()

  /* A newly demanded symbol needs a read, which widens and replaces any read
     already running. A symbol already covered does not: it either has a value
     on screen or is arriving in the request currently in flight.

     Checking only `state.at === null` was not enough. Two panels mounting
     together both see a null timestamp — the first read has not landed — and
     the second fires an identical duplicate of the request already running,
     which is the exact overlap this hub exists to remove. */
  if (added || (state.at === null && inFlight === null)) void read()

  return () => {
    listeners.delete(onChange)
    for (const s of clean) {
      const n = demand.get(s) ?? 0
      if (n <= 1) demand.delete(s)
      else demand.set(s, n - 1)
    }
    if (!listeners.size) stop()
  }
}

/** The current snapshot. Stable between emissions, as useSyncExternalStore needs. */
export function quoteSnapshot(): State {
  return state
}

/** Nothing is fetched on the server. */
const SERVER: State = { quotes: {}, at: null, error: null, loading: false }
export function quoteServerSnapshot(): State {
  return SERVER
}

/** Test seam. */
export function resetQuoteHub(): void {
  stop()
  demand.clear()
  listeners.clear()
  state = { quotes: {}, at: null, error: null, loading: false }
}

/** How many symbols the next request will ask for. Exposed for tests. */
export function demandedSymbols(): string[] {
  return symbols()
}
