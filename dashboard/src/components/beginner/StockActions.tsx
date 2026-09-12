'use client'

/**
 * The two things a reader wants after reading an analysis: keep it, or go
 * deeper.
 *
 * "Advanced analysis" is the same security and the same evidence snapshot at
 * full density — it is not a second opinion, and the copy says so, because a
 * reader who thinks the other page might disagree has been given a reason to
 * distrust both.
 *
 * The watchlist is the existing local symbol store, shared with the terminal,
 * so a name added here appears there.
 */

import Link from 'next/link'
import { useSyncExternalStore } from 'react'

import { emptySnapshot, subscribeSymbols, toggleWatch, watchSnapshot } from '@/lib/symbols'

export default function StockActions({ symbol }: { symbol: string }) {
  // The store is external to React, so it is read as one. The third argument
  // is the server snapshot: localStorage does not exist during the server
  // render, and an empty list there is what prevents a hydration mismatch.
  const watching = useSyncExternalStore(subscribeSymbols, watchSnapshot, emptySnapshot)
  const watched = watching.includes(symbol.trim().toUpperCase())

  return (
    <div className="bg__actions">
      <button
        type="button"
        className="bg__switch"
        aria-pressed={watched}
        onClick={() => toggleWatch(symbol)}
      >
        {watched ? '★ On your watchlist' : '☆ Add to watchlist'}
      </button>

      <Link href={`/terminal/security?symbol=${encodeURIComponent(symbol)}`} className="bg__switch">
        See advanced analysis →
      </Link>
    </div>
  )
}
