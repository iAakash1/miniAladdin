'use client'

/**
 * The names you are following, priced.
 *
 * A table, not a grid of cards. Watching a list is a scanning task: the eye
 * runs down one column looking for the row that moved, and that only works
 * when the numbers share an edge. Sixteen cards is sixteen separate reads.
 *
 * Quotes are fetched for the whole list in one request and refreshed on an
 * interval. A quote the provider itself flags as stale says so rather than
 * sitting in the same column as a live one.
 *
 * The list is keyed on ticker alone and lives in this browser. AAPL is AAPL
 * whether or not any research dataset knows about it, which is the entire
 * reason this is not built on the research object store.
 */

import Link from 'next/link'
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

import { Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { fetchQuotes, type Quote } from '@/lib/security'
import {
  emptySnapshot, subscribeSymbols, toggleWatch, watchSnapshot,
} from '@/lib/symbols'

/** Tagged with the symbol set it answers, so a stale reply cannot land late. */
interface Settled { for: string; quotes?: Record<string, Quote>; error?: string }

export default function Watchlist() {
  const symbols = useSyncExternalStore(subscribeSymbols, watchSnapshot, emptySnapshot)
  const [settled, setSettled] = useState<Settled | null>(null)
  const key = symbols.join(',')

  const load = useCallback((signal?: AbortSignal) => {
    if (!key) return
    fetchQuotes(key.split(','), signal)
      .then((q) => setSettled({ for: key, quotes: q }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setSettled({ for: key, error: e.message }) })
  }, [key])

  useEffect(() => {
    const c = new AbortController()
    load(c.signal)
    // Refreshed rather than left to go quietly stale on screen. Thirty seconds
    // is polite to the provider and fast enough that no row sits minutes
    // behind without saying so.
    const timer = window.setInterval(() => load(), 30_000)
    return () => { c.abort(); window.clearInterval(timer) }
  }, [load])

  const current = settled?.for === key ? settled : null
  const quotes = current?.quotes ?? {}

  if (!symbols.length) {
    return (
      <Panel title="Watchlist" state="recorded">
        <StateBlock
          state="recorded"
          title="No securities on the watchlist yet"
          detail="Search for a security and add it from its page. The list is kept in this browser."
        />
      </Panel>
    )
  }

  return (
    <Panel
      title="Watchlist"
      subtitle={`${symbols.length} ${symbols.length === 1 ? 'security' : 'securities'}`}
      state={current?.error ? 'unavailable' : current ? 'live' : 'waking'}
      flush
    >
      {current?.error ? (
        <StateBlock
          state="unavailable"
          title="Quotes could not be read"
          detail={`${current.error}. The list is unchanged; only the prices are missing, and no last price is shown in their place.`}
        />
      ) : null}

      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact wl">
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="num">Last</th>
              <th className="num">1 day</th>
              <th className="num">1 week</th>
              <th>Source</th>
              <th><span className="sys-sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((s) => {
              const q = quotes[s]
              return (
                <tr key={s}>
                  <td>
                    <Link href={`/terminal/security?symbol=${encodeURIComponent(s)}`} className="wl__sym">
                      {s}
                    </Link>
                  </td>
                  <td className="num"><Value value={q?.price ?? null} kind="currency" /></td>
                  <td className="num">
                    <Value value={q?.change_1d ?? null} kind="percent" digits={2} signed tone />
                  </td>
                  <td className="num">
                    <Value value={q?.change_1w ?? null} kind="percent" digits={2} signed tone />
                  </td>
                  <td>
                    {q ? (
                      <Status state={q.stale ? 'stale' : 'live'} label={q.source ?? 'unknown'} />
                    ) : current ? (
                      <Status state="unavailable" label="no quote" />
                    ) : (
                      <Status state="waking" label="reading" />
                    )}
                  </td>
                  <td className="num">
                    <button
                      type="button"
                      className="sys-btn sys-btn--micro"
                      onClick={() => toggleWatch(s)}
                      aria-label={`Remove ${s} from the watchlist`}
                    >
                      remove
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <Prose size="fine">
        Kept in this browser, keyed on the ticker. It does not follow you to
        another machine, and it survives the research dataset entirely.
      </Prose>
    </Panel>
  )
}
