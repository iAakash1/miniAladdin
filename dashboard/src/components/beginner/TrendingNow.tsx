'use client'

/**
 * Trending Now.
 *
 * The one component most likely to be misread, so the distinction is drawn
 * explicitly on every row: trending measures movement and attention, and the
 * model signal is a separate fact printed beside it. A security collapsing on
 * heavy coverage belongs at the top of this list *and* may carry a Sell
 * signal, and a reader who sees only the first half has been misled by the
 * layout rather than by the data.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock } from '@/components/system'
import { type ExploreRow, fetchExplore, signalTone } from '@/lib/explore'

const dash = '—'

const DIRECTION: Record<string, string> = {
  trending_up: 'Trending up',
  trending_down: 'Trending down',
  high_attention: 'High attention',
}

export default function TrendingNow({ limit = 5 }: { limit?: number }) {
  const [rows, setRows] = useState<ExploreRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchExplore({ category: 'trending', limit })
        if (live) setRows(body.results)
      } catch (e) {
        if (live) setError((e as Error).message)
      } finally {
        if (live) setLoading(false)
      }
    })()
    return () => { live = false }
  }, [limit])

  return (
    <Panel title="Trending Now" subtitle="movement and attention">
      <Prose>
        Trending is not a recommendation. A security falling sharply on heavy
        news coverage belongs here, and its model signal is shown beside it.
      </Prose>

      {loading ? (
        <StateBlock state="waking" title="Reading recent activity" detail="cached snapshot" />
      ) : error ? (
        <StateBlock state="unavailable" title="Trending unavailable" detail={error} />
      ) : !rows || rows.length === 0 ? (
        <EmptyLine label="Nothing trending">
          No security cleared the eligibility policy for a trend reading.
        </EmptyLine>
      ) : (
        <ul className="bg__trend-list">
          {rows.map((row) => (
            <li key={row.symbol} className="bg__trend-row">
              <Link href={`/beginner/company/${encodeURIComponent(row.symbol)}`} className="bg__sym">
                {row.symbol}
              </Link>
              <span className="bg__trend-dir">
                {row.trend_direction ? DIRECTION[row.trend_direction] ?? row.trend_direction : dash}
              </span>
              {/* Deliberately adjacent, never substituted for the above. */}
              <span className="xp__signal" data-tone={signalTone(row.model_signal)}>
                Signal: {row.model_signal ?? dash}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
