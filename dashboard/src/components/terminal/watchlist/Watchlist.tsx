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
import { useSyncExternalStore } from 'react'

import { EmptyLine, Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { useQuotes } from '@/lib/use-quotes'
import {
  emptySnapshot, subscribeSymbols, toggleWatch, watchSnapshot,
} from '@/lib/symbols'

export default function Watchlist() {
  const symbols = useSyncExternalStore(subscribeSymbols, watchSnapshot, emptySnapshot)
  // The hub unions this panel's symbols with every other panel's, issues one
  // request, and refreshes on one timer. Two panels showing AAPL cannot show
  // two different prices for it.
  const { quotes, error, at } = useQuotes(symbols)

  if (!symbols.length) {
    return (
      <EmptyLine label="Watchlist">
        Nothing tracked yet. Open a security and press <kbd className="sys-kbd">watch</kbd> to
        add it — the list lives in this browser, not in an account.
      </EmptyLine>
    )
  }

  return (
    <Panel
      title="Watchlist"
      subtitle={`${symbols.length} ${symbols.length === 1 ? 'security' : 'securities'}`}
      state={error ? 'stale' : at ? 'live' : 'waking'}
      flush
    >
      {error ? (
        <StateBlock
          state="stale"
          title="The last quote refresh failed"
          detail={`${error}. Any prices below are from the previous successful read${at ? ` at ${at.slice(11, 19)}` : ''}, not from now.`}
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
                      <Status state={error || q.stale ? 'stale' : 'live'} label={q.source ?? 'unknown'} />
                    ) : at ? (
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
