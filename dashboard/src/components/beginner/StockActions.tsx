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
import { useEffect, useState, useSyncExternalStore } from 'react'
import { useSearchParams } from 'next/navigation'

import OrderTicket from '@/components/terminal/paper/OrderTicket'
import { fetchPaperStatus, type PaperStatus } from '@/lib/paper'
import {
  emptySnapshot, recentSnapshot, subscribeSymbols, toggleWatch, watchSnapshot,
} from '@/lib/symbols'

export default function StockActions({
  symbol,
  mode = 'beginner',
}: {
  symbol: string
  mode?: 'beginner' | 'intermediate'
}) {
  // The store is external to React, so it is read as one. The third argument
  // is the server snapshot: localStorage does not exist during the server
  // render, and an empty list there is what prevents a hydration mismatch.
  const watching = useSyncExternalStore(subscribeSymbols, watchSnapshot, emptySnapshot)
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const watched = watching.includes(symbol.trim().toUpperCase())
  const against = recent.find((candidate) => candidate !== symbol.trim().toUpperCase()) ?? null
  const params = useSearchParams()
  const [paper, setPaper] = useState<PaperStatus | null>(null)
  const [ticketOpen, setTicketOpen] = useState(params.get('paper') === '1')

  useEffect(() => {
    let live = true
    fetchPaperStatus()
      .then((status) => { if (live) setPaper(status) })
      .catch(() => { /* an unavailable status does not expose a dead action */ })
    return () => { live = false }
  }, [])

  return (
    <>
      <div className="bg__actions">
        <button
          type="button"
          className="bg__switch"
          aria-pressed={watched}
          onClick={() => toggleWatch(symbol)}
        >
          {watched ? '★ On your watchlist' : '☆ Add to watchlist'}
        </button>

        {against ? (
          <Link
            href={`/${mode}/compare?a=${encodeURIComponent(symbol)}&b=${encodeURIComponent(against)}`}
            className="bg__switch"
          >
            Compare with {against}
          </Link>
        ) : (
          <Link href={`/${mode}/compare?a=${encodeURIComponent(symbol)}`} className="bg__switch">
            Compare
          </Link>
        )}

        {paper?.configured ? (
          <button
            type="button"
            className="bg__switch"
            aria-expanded={ticketOpen}
            onClick={() => setTicketOpen((open) => !open)}
          >
            {ticketOpen ? 'Close paper ticket' : 'Paper trade'}
          </button>
        ) : null}

        <Link href={`/company/${encodeURIComponent(symbol)}`} className="bg__switch">
          Open Advanced mode →
        </Link>
      </div>

      {ticketOpen && paper?.configured ? (
        <OrderTicket symbol={symbol} onClose={() => setTicketOpen(false)} />
      ) : null}
    </>
  )
}
