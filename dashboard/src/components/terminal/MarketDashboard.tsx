'use client'

import { useEffect, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import BreadthHeatmap from './BreadthHeatmap'
import EventsTimeline from './EventsTimeline'
import MacroSections from './MacroSections'
import MarketHero from './MarketHero'
import type { DashboardData } from '@/lib/dashboardInsights'

function DashboardSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} aria-hidden="true">
      <Skeleton height={230} />
      <Skeleton height={260} />
      <Skeleton height={180} />
    </div>
  )
}

/**
 * Terminal home: "what is happening in the market right now?" — answered
 * in the hero, in one glance. Everything below it is progressive
 * disclosure: a visual breadth read, a timeline of upcoming events, then
 * the full 14-indicator macro board grouped into three collapsed sections
 * for whoever wants to drill in. Same /api/dashboard call as before, same
 * 15-minute cache — this pass only changes how the response is presented.
 */
export default function MarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [failed, setFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    fetch('/api/dashboard', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((json: DashboardData) => {
        if (alive) {
          setData(json)
          setFailed(false)
        }
      })
      .catch((error: unknown) => {
        if (alive && (error as Error).name !== 'AbortError') setFailed(true)
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [reloadKey])

  if (failed) {
    return (
      <EmptyState
        title="Market data is unreachable"
        description="The dashboard service didn't respond. This usually resolves quickly."
        action={
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => { setData(null); setFailed(false); setReloadKey((key) => key + 1) }}>
            Try again
          </button>
        }
      />
    )
  }

  if (!data) return <DashboardSkeleton />

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <MarketHero data={data} />
      <BreadthHeatmap breadth={data.breadth} sectors={data.sectors} />
      <EventsTimeline events={data.events} />
      <MacroSections cards={data.macro.cards} />
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', textAlign: 'center' }}>
        Data refreshes every 15 minutes · generated {new Date(data.generated_at).toLocaleTimeString()}
      </p>
    </div>
  )
}
