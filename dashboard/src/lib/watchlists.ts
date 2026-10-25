'use client'

/*
 * Watchlists — cloud-synced through the FastAPI persistence layer (v3.5).
 *
 * Same reactive contract as the old localStorage store (useSyncExternalStore
 * + module-level mutations), so PortfolioView and search consumers are
 * unchanged except where creation needs the server-assigned id. Mutations are
 * optimistic: the UI updates immediately, the server call follows, and any
 * failure triggers a refetch so the store converges on the server's truth.
 */

import { useMemo, useSyncExternalStore } from 'react'
import { authFetch } from './persistence'

export interface WatchlistItem {
  ticker: string
  note: string | null
  tags: string[]
  position: number
  addedAt: string | null
}

export type SortKey = 'manual' | 'symbol' | 'change' | 'change_pct' | 'perf_1m' | 'perf_1y' | 'updated' | 'alerts'

export interface Watchlist {
  id: string
  name: string
  tickers: string[]
  /** Absent from responses of an older backend; treated as plain tickers then. */
  items?: WatchlistItem[]
  position?: number
  isDefault?: boolean
  sortKey?: SortKey
  createdAt: string
  updatedAt?: string
}

export type WatchlistsStatus = 'idle' | 'loading' | 'ready' | 'error' | 'unauthenticated'

export const SUGGESTED_LISTS: Array<{ name: string; tickers: string[] }> = [
  { name: 'Tech', tickers: ['AAPL', 'MSFT', 'GOOGL', 'META'] },
  { name: 'AI', tickers: ['NVDA', 'AMD', 'AVGO', 'SMCI'] },
  { name: 'Dividend', tickers: ['JNJ', 'PG', 'KO', 'O'] },
  { name: 'Long Term', tickers: ['SPY', 'QQQ', 'BRK-B'] },
]

const MAX_TICKERS = 200 // per list; the tracker reads quotes 25 at a time

let lists: Watchlist[] = []
let status: WatchlistsStatus = 'idle'
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((listener) => listener())
}

function setLists(next: Watchlist[]) {
  lists = next
  emit()
}

function subscribe(onChange: () => void) {
  listeners.add(onChange)
  if (status === 'idle') void refreshWatchlists()
  return () => {
    listeners.delete(onChange)
  }
}

/* Monotonic sequence: an in-flight refresh that resolves after a newer
   refresh or a local mutation must not clobber fresher state. Any mutation
   bumps the sequence, orphaning stale responses. */
let fetchSeq = 0

export async function refreshWatchlists(): Promise<void> {
  const seq = ++fetchSeq
  status = 'loading'
  emit()
  try {
    const res = await authFetch('/api/watchlists')
    if (seq !== fetchSeq) return // superseded while in flight
    if (res.status === 401) {
      status = 'unauthenticated'
      lists = []
    } else if (!res.ok) {
      status = 'error'
    } else {
      lists = ((await res.json()) as { watchlists: Watchlist[] }).watchlists
      status = 'ready'
    }
  } catch {
    if (seq !== fetchSeq) return
    status = 'error'
  }
  emit()
}

function markMutated() {
  fetchSeq += 1
  status = 'ready'
}

/** Non-reactive read of the current store state — for consumers outside
 *  React (the Intelligence OS watchlists provider). */
export function readWatchlistsSnapshot(): Watchlist[] {
  return lists
}

/* One frozen value, not a fresh one per call. React compares the server
   snapshot by identity and warns of an infinite render loop when a new object
   comes back each time; on the server there is nothing stored, and "nothing"
   is a constant. */
const SERVER_LISTS: Watchlist[] = []

export function useWatchlists(): Watchlist[] {
  return useSyncExternalStore(subscribe, () => lists, () => SERVER_LISTS)
}

export function useWatchlistsStatus(): WatchlistsStatus {
  return useSyncExternalStore(subscribe, () => status, () => 'idle' as WatchlistsStatus)
}

function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase().replace(/[^A-Z.^-]/g, '')
}

/** Create on the server; resolves with the created list (or null on failure). */
export async function createWatchlist(
  name: string,
  tickers: string[] = [],
): Promise<Watchlist | null> {
  try {
    const res = await authFetch('/api/watchlists', {
      method: 'POST',
      body: JSON.stringify({ name, tickers }),
    })
    if (!res.ok) return null
    const created = (await res.json()) as Watchlist
    markMutated()
    setLists([...lists, created])
    return created
  } catch {
    return null
  }
}

/** The items of a list, from the server's detail or, failing that, its tickers. */
export function itemsOf(list: Watchlist): WatchlistItem[] {
  if (list.items?.length || (list.items && !list.tickers.length)) return list.items as WatchlistItem[]
  return list.tickers.map((ticker, position) => ({ ticker, note: null, tags: [], position, addedAt: null }))
}

function patchList(id: string, body: Record<string, unknown>) {
  void authFetch(`/api/watchlists/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) })
    .then((res) => { if (!res.ok) void refreshWatchlists() })
    .catch(() => refreshWatchlists())
}

export function setDefaultWatchlist(id: string) {
  markMutated()
  setLists(lists.map((l) => ({ ...l, isDefault: l.id === id })))
  patchList(id, { is_default: true })
}

export function setSortKey(id: string, sortKey: SortKey) {
  markMutated()
  setLists(lists.map((l) => (l.id === id ? { ...l, sortKey } : l)))
  patchList(id, { sort_key: sortKey })
}

/** Move a list one place up or down. */
export function shiftWatchlist(id: string, delta: -1 | 1) {
  const index = lists.findIndex((l) => l.id === id)
  const target = index + delta
  if (index < 0 || target < 0 || target >= lists.length) return
  const next = [...lists]
  ;[next[index], next[target]] = [next[target], next[index]]
  markMutated()
  setLists(next.map((l, position) => ({ ...l, position })))
  void authFetch('/api/watchlists/order', { method: 'PUT', body: JSON.stringify({ order: next.map((l) => l.id) }) })
    .then((res) => { if (!res.ok) void refreshWatchlists() })
    .catch(() => refreshWatchlists())
}

/** Move a symbol one place up or down within its list. */
export function shiftTicker(id: string, ticker: string, delta: -1 | 1) {
  const list = lists.find((l) => l.id === id)
  if (!list) return
  const order = [...list.tickers]
  const index = order.indexOf(ticker)
  const target = index + delta
  if (index < 0 || target < 0 || target >= order.length) return
  ;[order[index], order[target]] = [order[target], order[index]]
  const byTicker = new Map(itemsOf(list).map((i) => [i.ticker, i]))
  markMutated()
  setLists(lists.map((l) => (l.id === id ? {
    ...l, tickers: order,
    items: order.map((t, position) => ({ ...(byTicker.get(t) as WatchlistItem), ticker: t, position })),
  } : l)))
  void authFetch(`/api/watchlists/${encodeURIComponent(id)}/order`, { method: 'PUT', body: JSON.stringify({ order }) })
    .then((res) => { if (!res.ok) void refreshWatchlists() })
    .catch(() => refreshWatchlists())
}

export function updateItem(id: string, ticker: string, patch: { note?: string | null; tags?: string[] }) {
  markMutated()
  setLists(lists.map((l) => (l.id === id ? {
    ...l, items: itemsOf(l).map((i) => (i.ticker === ticker ? {
      ...i, note: patch.note === undefined ? i.note : patch.note, tags: patch.tags ?? i.tags,
    } : i)),
  } : l)))
  const body: Record<string, unknown> = {}
  if (patch.note === null || patch.note === '') body.clear_note = true
  else if (patch.note !== undefined) body.note = patch.note
  if (patch.tags) body.tags = patch.tags
  void authFetch(`/api/watchlists/${encodeURIComponent(id)}/tickers/${encodeURIComponent(ticker)}`, {
    method: 'PATCH', body: JSON.stringify(body),
  }).then((res) => { if (!res.ok) void refreshWatchlists() }).catch(() => refreshWatchlists())
}

/** Move a symbol to another list; its note and tags go with it. */
export async function moveTicker(fromId: string, toId: string, ticker: string): Promise<boolean> {
  try {
    const res = await authFetch(`/api/watchlists/${encodeURIComponent(fromId)}/tickers/${encodeURIComponent(ticker)}/move`, {
      method: 'POST', body: JSON.stringify({ to_watchlist_id: toId }),
    })
    await refreshWatchlists()
    return res.ok
  } catch {
    await refreshWatchlists()
    return false
  }
}

export function renameWatchlist(id: string, name: string) {
  const clean = name.trim().slice(0, 40)
  if (!clean) return
  markMutated()
  setLists(lists.map((l) => (l.id === id ? { ...l, name: clean } : l)))
  void authFetch(`/api/watchlists/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ name: clean }),
  }).then((res) => {
    if (!res.ok) void refreshWatchlists()
  }).catch(() => refreshWatchlists())
}

export function deleteWatchlist(id: string) {
  markMutated()
  setLists(lists.filter((l) => l.id !== id))
  void authFetch(`/api/watchlists/${encodeURIComponent(id)}`, { method: 'DELETE' })
    .then((res) => {
      if (!res.ok) void refreshWatchlists()
    })
    .catch(() => refreshWatchlists())
}

export function addTicker(id: string, ticker: string) {
  const symbol = normalizeTicker(ticker)
  if (!symbol) return
  markMutated()
  setLists(lists.map((l) =>
    l.id === id && !l.tickers.includes(symbol)
      ? {
        ...l,
        tickers: [...l.tickers, symbol].slice(0, MAX_TICKERS),
        items: [...itemsOf(l), { ticker: symbol, note: null, tags: [], position: l.tickers.length, addedAt: new Date().toISOString() }].slice(0, MAX_TICKERS),
      }
      : l,
  ))
  void authFetch(`/api/watchlists/${encodeURIComponent(id)}/tickers`, {
    method: 'POST',
    body: JSON.stringify({ ticker: symbol }),
  }).then((res) => {
    if (!res.ok) void refreshWatchlists()
  }).catch(() => refreshWatchlists())
}

export function removeTicker(id: string, ticker: string) {
  const symbol = normalizeTicker(ticker)
  markMutated()
  setLists(lists.map((l) =>
    l.id === id ? { ...l, tickers: l.tickers.filter((t) => t !== symbol), items: itemsOf(l).filter((i) => i.ticker !== symbol) } : l,
  ))
  void authFetch(
    `/api/watchlists/${encodeURIComponent(id)}/tickers/${encodeURIComponent(symbol)}`,
    { method: 'DELETE' },
  ).then((res) => {
    if (!res.ok) void refreshWatchlists()
  }).catch(() => refreshWatchlists())
}

/* ── one watch concept across the product ────────────────────────────────
   "Watch" anywhere (company header, palette, idea lists) means membership in
   the account's lists. With no list yet, the first watch creates one. */

export const DEFAULT_LIST_NAME = 'Watchlist'

/** Every symbol on any list, in list order, without duplicates. */
export function watchedSymbols(from: Watchlist[] = lists): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const l of from) {
    for (const t of l.tickers) {
      if (!seen.has(t)) { seen.add(t); out.push(t) }
    }
  }
  return out
}

export function listsContaining(symbol: string, from: Watchlist[] = lists): Watchlist[] {
  const s = normalizeTicker(symbol)
  return from.filter((l) => l.tickers.includes(s))
}

/** Add to a list — the named one, the default, or the first, creating one if none exists. */
export async function watchSymbol(symbol: string, listId?: string): Promise<boolean> {
  const s = normalizeTicker(symbol)
  if (!s) return false
  const target = listId ? lists.find((l) => l.id === listId) : (lists.find((l) => l.isDefault) ?? lists[0])
  if (target) {
    addTicker(target.id, s)
    return true
  }
  return (await createWatchlist(DEFAULT_LIST_NAME, [s])) !== null
}

/** Remove from every list that holds it. */
export function unwatchSymbol(symbol: string): void {
  for (const l of listsContaining(symbol)) removeTicker(l.id, symbol)
}

export function useWatchedSymbols(): string[] {
  const current = useWatchlists()
  return useMemo(() => watchedSymbols(current), [current])
}
