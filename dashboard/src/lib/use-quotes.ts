'use client'

/**
 * A panel's view of the shared quote hub.
 *
 * A component states which symbols it shows and gets the rest for free: no
 * effect, no local copy of the prices, and no second request for a symbol
 * another panel already wants.
 */

import { useSyncExternalStore } from 'react'

import { quoteServerSnapshot, quoteSnapshot, subscribeQuotes } from './quote-hub'
import type { Quote } from './security'

export interface QuoteView {
  quotes: Record<string, Quote>
  /** When the last successful read completed. */
  at: string | null
  /** Why the last read failed. The previous quotes are still present. */
  error: string | null
  loading: boolean
}

/**
 * Subscribe callbacks, one per symbol set.
 *
 * useSyncExternalStore tears down and rebuilds its subscription whenever the
 * callback's identity changes, so a fresh closure each render would mean the
 * hub's reference counts churning on every paint. Keyed by the sorted symbol
 * list, the identity changes exactly when the demand does.
 */
const subscribers = new Map<string, (onChange: () => void) => () => void>()

function subscriberFor(key: string) {
  const hit = subscribers.get(key)
  if (hit) return hit

  const wanted = key ? key.split(',') : []
  const fn = (onChange: () => void) => subscribeQuotes(wanted, onChange)
  subscribers.set(key, fn)

  // A memo, not a leak: a session touches a handful of symbol sets and each
  // entry is one closure.
  if (subscribers.size > 32) {
    const oldest = subscribers.keys().next().value
    if (oldest !== undefined) subscribers.delete(oldest)
  }
  return fn
}

export function useQuotes(symbols: string[]): QuoteView {
  const key = [...new Set(symbols.map((s) => s.trim().toUpperCase()).filter(Boolean))]
    .sort()
    .join(',')

  return useSyncExternalStore(subscriberFor(key), quoteSnapshot, quoteServerSnapshot)
}
