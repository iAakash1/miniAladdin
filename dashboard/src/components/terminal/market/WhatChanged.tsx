'use client'

/**
 * What changed since you last looked.
 *
 * The market-level counterpart to the per-security verdict timeline. It
 * snapshots the same headline readings the workspace already loaded, keeps them
 * in this browser, and diffs the two most recent.
 *
 * The value is in the two states that are not a list of changes. A first visit
 * says it is a first visit, and a genuinely quiet market says the market was
 * quiet — neither renders as an empty gap, because an empty panel reads as a
 * broken one and a reader who cannot tell "nothing changed" from "this did not
 * load" will eventually trust neither.
 *
 * Snapshots live in localStorage. They are per-browser and per-device by
 * construction, and the panel says so rather than implying a server-side
 * history it does not have.
 *
 * The payload arrives with every field optional, because the dashboard endpoint
 * can serve a partial response when a vendor is down. `snapshotFromDashboard`
 * reaches into `macro.cards` and `breadth.indexes` without guarding, so a
 * partial payload must be refused here rather than cast into the shape the
 * snapshot wants. A snapshot taken from half a payload would sit in the history
 * and be diffed against a full one later, reporting movement that never
 * happened.
 */

import { useEffect } from 'react'

import { Panel, Prose } from '@/components/system'
import { diffMarketSnapshots, recordMarketSnapshot, useMarketHistory } from '@/lib/marketHistory'
import type { DashboardData } from '@/lib/dashboardInsights'
import { timeAgo } from '@/lib/format'

/** What the workspace holds: every field optional, because the endpoint can
 *  serve a partial response when a vendor is unavailable. */
interface Loose {
  macro?: unknown
  breadth?: unknown
  generated_at?: string
}

/** True only when the fields the snapshot dereferences are actually there. */
function complete(data: Loose | null): data is DashboardData & Loose {
  if (!data?.generated_at) return false
  const macro = data.macro as { cards?: unknown; regime?: unknown } | undefined
  const breadth = data.breadth as { indexes?: unknown } | undefined
  return Array.isArray(macro?.cards)
    && macro?.regime !== undefined && macro?.regime !== null
    && Array.isArray(breadth?.indexes)
}

const TONE = {
  pos: 'var(--e-pos)',
  neg: 'var(--e-neg)',
  warn: 'var(--s-stale)',
  neutral: 'var(--rule-strong)',
} as const

export default function WhatChanged({ data }: { data: Loose | null }) {
  const usable = complete(data) ? data : null

  useEffect(() => {
    if (usable) recordMarketSnapshot(usable)
  }, [usable])

  const history = useMarketHistory()
  const after = history[history.length - 1]
  const before = history[history.length - 2]
  const changes = before && after ? diffMarketSnapshots(before, after) : []

  return (
    <Panel
      title="What changed"
      subtitle={before ? `since ${timeAgo(before.ts)}` : undefined}
      state="live"
    >
      {data && !usable ? (
        <Prose>
          This update arrived without the macro or breadth readings the
          comparison is built from, so it was not recorded. Nothing is diffed
          against a partial snapshot — doing so would report movement that never
          happened the next time a complete one arrives.
        </Prose>
      ) : !before || !after ? (
        <Prose>
          This is the first snapshot of the market taken on this device, so
          there is nothing to compare it against yet. The next update will have
          something to diff.
        </Prose>
      ) : changes.length === 0 ? (
        <Prose>
          No material change in regime, breadth or the headline macro readings
          since the last snapshot. This is a measured result, not an empty panel.
        </Prose>
      ) : (
        <ul className="sys-reasons">
          {changes.map((change) => (
            <li key={change.id} style={{ borderLeftColor: TONE[change.tone], color: 'var(--ink)' }}>
              {change.text}
            </li>
          ))}
        </ul>
      )}
      <Prose size="fine">
        Snapshots are kept in this browser. They do not follow you to another
        machine, and clearing site data clears them.
      </Prose>
    </Panel>
  )
}
