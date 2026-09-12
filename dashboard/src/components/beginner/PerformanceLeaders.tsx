'use client'

/**
 * Performance Leaders — a different question from Top Ranked Ideas.
 *
 * Top Ranked asks what the model thinks now. This asks how a security has
 * actually done, adjusted for what it put a holder through. They disagree
 * often, and the disagreement is the useful part: a name can have compounded
 * beautifully and still carry a HOLD because it is expensive today.
 *
 * So the model signal sits on every row here, exactly as it does on the
 * trending list. A leaderboard of past performance shown without the current
 * verdict beside it is the shape that reads as a recommendation, and it is not
 * one.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock } from '@/components/system'
import { type ExploreRow, fetchRecommendations, signalTone } from '@/lib/explore'

const dash = '—'

function pct(value: number | null): string {
  return value === null || !Number.isFinite(value) ? dash : `${(value * 100).toFixed(1)}%`
}

export default function PerformanceLeaders({ limit = 5 }: { limit?: number }) {
  const [rows, setRows] = useState<ExploreRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchRecommendations(limit)
        if (live) setRows(body.performance_leaders ?? [])
      } catch (e) {
        if (live) setError((e as Error).message)
      } finally {
        if (live) setLoading(false)
      }
    })()
    return () => { live = false }
  }, [limit])

  return (
    <Panel title="Performance Leaders" subtitle="strongest risk-adjusted history">
      <Prose>
        Measured against the benchmark and adjusted for volatility, downside and
        drawdown — not ranked by raw gain. Past performance is not a forecast,
        and it is not the model&apos;s current view: the signal beside each name is.
      </Prose>

      {loading ? (
        <StateBlock state="waking" title="Reading performance history" detail="cached snapshot" />
      ) : error ? (
        <StateBlock state="unavailable" title="Performance unavailable" detail={error} />
      ) : !rows || rows.length === 0 ? (
        <EmptyLine label="No leaders">
          No security had enough history to be scored on performance.
        </EmptyLine>
      ) : (
        <ul className="bg__trend-list">
          {rows.map((row) => (
            <li key={row.symbol} className="bg__trend-row">
              <Link href={`/beginner/company/${encodeURIComponent(row.symbol)}`} className="bg__sym">
                {row.symbol}
              </Link>
              <span className="bg__trend-dir">
                {row.performance_grade ?? dash}
                <span className="bg__qual"> · 6m vs market {pct(row.excess_return_6m)}</span>
              </span>
              {/* Adjacent, never substituted for the above. */}
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
