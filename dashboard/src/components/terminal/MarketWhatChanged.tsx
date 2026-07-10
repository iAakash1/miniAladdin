'use client'

import { useEffect } from 'react'
import { diffMarketSnapshots, recordMarketSnapshot, useMarketHistory } from '@/lib/marketHistory'
import { timeAgo } from '@/lib/format'
import type { DashboardData } from '@/lib/dashboardInsights'

const TONE_COLOR = { pos: 'var(--pos)', neg: 'var(--neg)', warn: 'var(--warn)', neutral: 'var(--muted)' } as const

/**
 * "What changed since your last visit" — the market-level counterpart to
 * the per-ticker Verdict Timeline (lib/history.ts + diffSnapshots).
 * Snapshots the same fields the hero already reads on every successful
 * dashboard load (client-side only, localStorage — see
 * lib/marketHistory.ts) and diffs the two most recent ones. A first-ever
 * visit and a quiet, unchanged market both render an honest, specific
 * state rather than an empty gap on the page.
 */
export default function MarketWhatChanged({ data }: { data: DashboardData }) {
  useEffect(() => {
    recordMarketSnapshot(data)
  }, [data])

  const history = useMarketHistory()
  const after = history[history.length - 1]
  const before = history[history.length - 2]
  const changes = before && after ? diffMarketSnapshots(before, after) : []

  return (
    <section aria-labelledby="whatchanged-h" className="card dash-events">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
        <span id="whatchanged-h" className="h-panel" style={{ fontSize: '0.9375rem' }}>
          What changed
        </span>
        {before && (
          <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
            since {timeAgo(before.ts)}
          </span>
        )}
      </div>

      {!before || !after ? (
        <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
          This is your first snapshot of the market on this device — nothing to compare yet. Check
          back after the next update to see what moved.
        </p>
      ) : changes.length === 0 ? (
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>
          No material change in regime, breadth, or headline macro readings since your last visit.
        </p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {changes.map((change) => (
            <li key={change.id} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--text)' }}>
              <span
                aria-hidden="true"
                style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: TONE_COLOR[change.tone] }}
              />
              {change.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
