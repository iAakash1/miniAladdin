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

import { useSyncExternalStore } from 'react'
import { authFetch } from './persistence'

export interface Watchlist {
  id: string
  name: string
  tickers: string[]
  createdAt: string
}

export type WatchlistsStatus = 'idle' | 'loading' | 'ready' | 'error' | 'unauthenticated'

export const SUGGESTED_LISTS: Array<{ name: string; tickers: string[] }> = [
  { name: 'Tech', tickers: ['AAPL', 'MSFT', 'GOOGL', 'META'] },
  { name: 'AI', tickers: ['NVDA', 'AMD', 'AVGO', 'SMCI'] },
  { name: 'Dividend', tickers: ['JNJ', 'PG', 'KO', 'O'] },
  { name: 'Long Term', tickers: ['SPY', 'QQQ', 'BRK-B'] },
]

const MAX_TICKERS = 25 // matches /api/quotes batch cap

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

export function useWatchlists(): Watchlist[] {
  return useSyncExternalStore(subscribe, () => lists, () => [] as Watchlist[])
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
      ? { ...l, tickers: [...l.tickers, symbol].slice(0, MAX_TICKERS) }
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
    l.id === id ? { ...l, tickers: l.tickers.filter((t) => t !== symbol) } : l,
  ))
  void authFetch(
    `/api/watchlists/${encodeURIComponent(id)}/tickers/${encodeURIComponent(symbol)}`,
    { method: 'DELETE' },
  ).then((res) => {
    if (!res.ok) void refreshWatchlists()
  }).catch(() => refreshWatchlists())
}
