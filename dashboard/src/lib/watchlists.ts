'use client'

/* Watchlists — client-persisted (localStorage), reactive via
   useSyncExternalStore, same pattern as usage/history stores. */

import { useSyncExternalStore } from 'react'

const KEY = 'omni_watchlists_v1'
const EVENT = 'omni-watchlists'
const MAX_LISTS = 20
const MAX_TICKERS = 25 // matches /api/quotes batch cap

export interface Watchlist {
  id: string
  name: string
  tickers: string[]
  createdAt: string
}

export const SUGGESTED_LISTS: Array<{ name: string; tickers: string[] }> = [
  { name: 'Tech', tickers: ['AAPL', 'MSFT', 'GOOGL', 'META'] },
  { name: 'AI', tickers: ['NVDA', 'AMD', 'AVGO', 'SMCI'] },
  { name: 'Dividend', tickers: ['JNJ', 'PG', 'KO', 'O'] },
  { name: 'Long Term', tickers: ['SPY', 'QQQ', 'BRK-B'] },
]

function read(): Watchlist[] {
  if (typeof window === 'undefined') return []
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]') as Watchlist[]
  } catch {
    return []
  }
}

function write(lists: Watchlist[]) {
  localStorage.setItem(KEY, JSON.stringify(lists.slice(0, MAX_LISTS)))
  window.dispatchEvent(new Event(EVENT))
}

let cachedRaw = ''
let cachedLists: Watchlist[] = []

function snapshot(): Watchlist[] {
  if (typeof window === 'undefined') return cachedLists
  const raw = localStorage.getItem(KEY) ?? '[]'
  if (raw !== cachedRaw) {
    cachedRaw = raw
    try {
      cachedLists = JSON.parse(raw) as Watchlist[]
    } catch {
      cachedLists = []
    }
  }
  return cachedLists
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

export function useWatchlists(): Watchlist[] {
  return useSyncExternalStore(subscribe, snapshot, () => [] as Watchlist[])
}

export function createWatchlist(name: string, tickers: string[] = []): Watchlist {
  const list: Watchlist = {
    id: `wl_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name: name.trim().slice(0, 40) || 'Untitled',
    tickers: normalizeTickers(tickers),
    createdAt: new Date().toISOString(),
  }
  write([...read(), list])
  return list
}

export function renameWatchlist(id: string, name: string) {
  write(read().map((l) => (l.id === id ? { ...l, name: name.trim().slice(0, 40) || l.name } : l)))
}

export function deleteWatchlist(id: string) {
  write(read().filter((l) => l.id !== id))
}

export function addTicker(id: string, ticker: string) {
  const symbol = ticker.trim().toUpperCase().replace(/[^A-Z.^-]/g, '')
  if (!symbol) return
  write(read().map((l) =>
    l.id === id && !l.tickers.includes(symbol)
      ? { ...l, tickers: [...l.tickers, symbol].slice(0, MAX_TICKERS) }
      : l,
  ))
}

export function removeTicker(id: string, ticker: string) {
  write(read().map((l) =>
    l.id === id ? { ...l, tickers: l.tickers.filter((t) => t !== ticker) } : l,
  ))
}

function normalizeTickers(tickers: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of tickers) {
    const symbol = raw.trim().toUpperCase().replace(/[^A-Z.^-]/g, '')
    if (symbol && !seen.has(symbol)) {
      seen.add(symbol)
      out.push(symbol)
    }
  }
  return out.slice(0, MAX_TICKERS)
}
