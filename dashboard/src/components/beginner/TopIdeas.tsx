'use client'

/**
 * Top Ranked Ideas.
 *
 * Nothing here is a list of favourites. The component asks the backend for the
 * current overall ranking and renders whatever comes back; if the ranking
 * changes, these cards change, and if nothing clears the eligibility policy
 * this renders an empty state rather than relaxing anything to fill the slots.
 *
 * Every card carries the qualifiers beside the signal — risk, confidence, data
 * coverage — because a signal shown on its own is the one presentation of this
 * data that reads as a recommendation.
 */

import Link from 'next/link'
import { useEffect, useState, useSyncExternalStore } from 'react'

import { emptySnapshot, subscribeSymbols, toggleWatch, watchSnapshot } from '@/lib/symbols'

import { EmptyLine, Panel, Prose, StateBlock } from '@/components/system'
import { DISCLAIMER } from '@/lib/beginner'
import {
  type ExploreRow, type RecommendationsResponse, fetchRecommendations, freshness, signalTone,
} from '@/lib/explore'

const dash = '—'

/** The shared local watchlist, so a name added here shows up in the terminal. */
function WatchToggle({ symbol }: { symbol: string }) {
  // Read as an external store. The server snapshot is empty because
  // localStorage does not exist during the server render, which is what keeps
  // hydration consistent.
  const watching = useSyncExternalStore(subscribeSymbols, watchSnapshot, emptySnapshot)
  const watched = watching.includes(symbol.trim().toUpperCase())

  return (
    <button
      type="button"
      className="bg__watch"
      aria-pressed={watched}
      aria-label={watched ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
      onClick={() => toggleWatch(symbol)}
    >
      {watched ? '★ Watching' : '☆ Watch'}
    </button>
  )
}


function Card({ row, rank }: { row: ExploreRow; rank: number }) {
  return (
    <article className="bg__card">
      <header className="bg__card-head">
        <span className="bg__rank" aria-label={`Rank ${rank}`}>#{rank}</span>
        <div>
          <Link href={`/beginner/company/${encodeURIComponent(row.symbol)}`} className="bg__sym">
            {row.symbol}
          </Link>
          <span className="bg__co">{row.company_name}</span>
        </div>
        <span className="bg__price">
          {row.price === null ? dash : `$${row.price.toFixed(2)}`}
        </span>
      </header>

      <div className="bg__signal-row">
        {/* Label plus tone, never tone alone — the verdict has to survive for
            a reader who cannot distinguish the colours. */}
        <span className="xp__signal" data-tone={signalTone(row.model_signal)}>
          {row.model_signal ?? dash}
        </span>
        <span className="bg__qual">Risk {row.risk_level ?? dash}</span>
        <span className="bg__qual">Confidence {row.confidence ?? dash}/100</span>
        <span className="bg__qual">
          Data {row.data_completeness === null ? dash : `${Math.round(row.data_completeness * 100)}%`}
        </span>
      </div>

      <dl className="bg__why">
        <dt>Strongest support</dt>
        <dd>{row.top_positive ?? dash}</dd>
        <dt>Main caution</dt>
        <dd>{row.top_caution ?? dash}</dd>
      </dl>

      <footer className="bg__card-foot">
        <Link href={`/beginner/company/${encodeURIComponent(row.symbol)}`} className="bg__action">
          View analysis
        </Link>
        <WatchToggle symbol={row.symbol} />
        {row.price_as_of ? <span className="bg__asof">Priced {row.price_as_of}</span> : null}
      </footer>
    </article>
  )
}

export default function TopIdeas({ limit = 4 }: { limit?: number }) {
  const [data, setData] = useState<RecommendationsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchRecommendations(limit)
        if (live) setData(body)
      } catch (e) {
        if (live) setError((e as Error).message)
      } finally {
        if (live) setLoading(false)
      }
    })()
    return () => { live = false }
  }, [limit])

  return (
    <Panel
      title="Top Ranked Ideas"
      subtitle="highest scoring under the quantitative model"
    >
      <Prose>{DISCLAIMER}</Prose>

      {loading ? (
        <StateBlock state="waking" title="Ranking the universe" detail="cached snapshot" />
      ) : error ? (
        <StateBlock state="unavailable" title="Rankings unavailable" detail={error} />
      ) : !data || data.results.length === 0 ? (
        <EmptyLine label="No ideas today">
          No security in the universe met the eligibility policy. That is the
          honest answer — the list is not padded out when nothing qualifies.
        </EmptyLine>
      ) : (
        <>
          {data.stale ? (
            <StateBlock
              state="stale"
              title="These rankings are not current"
              detail={data.stale_reason ?? 'the last refresh did not complete'}
            />
          ) : null}
          <div className="bg__cards">
            {data.results.map((row, i) => <Card key={row.symbol} row={row} rank={i + 1} />)}
          </div>
          <Prose>
            Ranked {data.eligible_count} of {data.evaluated_count} securities
            {freshness(data.generated_at) ? ` · updated ${freshness(data.generated_at)}` : ''}
            {` · universe ${data.universe_version}`}
          </Prose>
        </>
      )}
    </Panel>
  )
}
