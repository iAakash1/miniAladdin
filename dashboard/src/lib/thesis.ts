'use client'

/**
 * Why you bought it.
 *
 * A paper trade with no recorded reason is an entry in a ledger. A paper
 * trade with the reason attached is the only part of this product that can
 * answer the question worth asking three months later: not "what did I buy"
 * but "what did I believe, and was I right".
 *
 * Two rules, and they are the whole design.
 *
 * Nothing is ever generated. If the reader did not write a thesis, the
 * interface says no thesis was recorded. It does not summarise the
 * fundamentals into a sentence and present that as what someone thought — a
 * fabricated intent is worse than an absent one, because an absent one is
 * obviously absent.
 *
 * The research state travelling with a thesis is a snapshot, not a link. What
 * the archive says in December is not what it said when the order was placed,
 * and a review that silently reads today's state is a review of the wrong
 * thing.
 *
 * Kept in this browser, like watchlists and recents. It does not follow you
 * to another machine, and the interface says so rather than implying an
 * account.
 */

const KEY = 'ma.paper.thesis.v1'

export interface Thesis {
  /** The broker's order id — the thing this is a thesis about. */
  orderId: string
  symbol: string
  /** What the reader wrote. Never generated, never defaulted. */
  text: string
  /** When it was written, not when the order filled. */
  at: string
  /** The research programme's state at the moment of the order. A snapshot. */
  researchState?: string | null
}

type Store = Record<string, Thesis>

function read(): Store {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) as Store : {}
  } catch {
    // A corrupt or unavailable store is an empty one. It is never a reason to
    // fail the page a reader came to for their positions.
    return {}
  }
}

function write(store: Store): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(store))
  } catch { /* private windows and full quotas are not errors worth raising */ }
  listeners.forEach((fn) => fn())
}

const listeners = new Set<() => void>()

export function subscribeTheses(onChange: () => void): () => void {
  listeners.add(onChange)
  return () => { listeners.delete(onChange) }
}

/* Snapshots are cached so useSyncExternalStore sees a stable reference
   between writes; the cache is dropped whenever the store changes. */
let cache: Store | null = null

export function thesisSnapshot(): Store {
  if (cache === null) cache = read()
  return cache
}

const EMPTY: Store = {}
export function emptyThesisSnapshot(): Store { return EMPTY }

export function recordThesis(t: Thesis): void {
  const store = { ...read(), [t.orderId]: t }
  cache = null
  write(store)
}

export function thesisFor(orderId: string): Thesis | null {
  return read()[orderId] ?? null
}

/**
 * The theses attached to any order for this symbol, newest first.
 *
 * A position is not an order — it is the residue of several — so "why do I
 * own this" is answered by every reason recorded for the name, not by one.
 */
export function thesesForSymbol(symbol: string): Thesis[] {
  const s = symbol.toUpperCase()
  return Object.values(read())
    .filter((t) => t.symbol.toUpperCase() === s)
    .sort((a, b) => (a.at < b.at ? 1 : -1))
}
