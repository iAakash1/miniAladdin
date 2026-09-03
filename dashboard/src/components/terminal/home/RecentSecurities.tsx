'use client'

/**
 * What this browser has been looking at, priced.
 *
 * Recents are the fastest way back into work already in progress, and a list
 * of bare tickers is not that — the reason to return to a name is usually that
 * it moved. So the row carries its last price and change, from the same quote
 * call the watchlist uses.
 */

import Link from 'next/link'
import { useEffect, useState, useSyncExternalStore } from 'react'

import { Panel, StateBlock, Value } from '@/components/system'
import { fetchQuotes, type Quote } from '@/lib/security'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'

export default function RecentSecurities() {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const [quotes, setQuotes] = useState<{ for: string; q: Record<string, Quote> } | null>(null)
  const key = recent.slice(0, 8).join(',')

  useEffect(() => {
    if (!key) return
    const c = new AbortController()
    fetchQuotes(key.split(','), c.signal)
      .then((q) => setQuotes({ for: key, q }))
      .catch(() => { /* the list is still useful without prices */ })
    return () => c.abort()
  }, [key])

  const q = quotes?.for === key ? quotes.q : {}

  if (!recent.length) {
    return (
      <Panel title="Recent" state="recorded">
        <StateBlock
          state="recorded"
          title="Nothing opened yet in this browser"
          detail="Search for a ticker to begin. Recent names appear here."
        />
      </Panel>
    )
  }

  return (
    <Panel title="Recent" subtitle="opened in this browser" state="live" flush>
      <table className="sys-table sys-table--compact wl">
        <thead>
          <tr><th>Symbol</th><th className="num">Last</th><th className="num">1 day</th></tr>
        </thead>
        <tbody>
          {recent.slice(0, 8).map((s) => (
            <tr key={s}>
              <td>
                <Link href={`/terminal/security?symbol=${encodeURIComponent(s)}`} className="wl__sym">{s}</Link>
              </td>
              <td className="num"><Value value={q[s]?.price ?? null} kind="currency" /></td>
              <td className="num">
                <Value value={q[s]?.change_1d ?? null} kind="percent" digits={2} signed tone />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  )
}
