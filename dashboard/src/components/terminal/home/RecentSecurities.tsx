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
import { useSyncExternalStore } from 'react'

import { EmptyLine, Panel, Value } from '@/components/system'
import { useQuotes } from '@/lib/use-quotes'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'

export default function RecentSecurities() {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  // Shares the hub with the watchlist beside it. These lists overlap heavily,
  // and two requests for overlapping sets is two fan-outs for one set of facts
  // — and two prices for the same symbol on one screen.
  const { quotes: q } = useQuotes(recent.slice(0, 8))

  if (!recent.length) {
    return (
      <EmptyLine label="Recent">
        Nothing opened yet. Press <kbd className="sys-kbd">/</kbd> and type a ticker or a
        company name; whatever you look at appears here.
      </EmptyLine>
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
