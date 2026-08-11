'use client'

import { useEffect, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import WorkBoot from '@/components/ui/WorkBoot'
import BreadthHeatmap from './BreadthHeatmap'
import EventsTimeline from './EventsTimeline'
import MacroSections from './MacroSections'
import MarketHero from './MarketHero'
import MarketWhatChanged from './MarketWhatChanged'
import type { DashboardData } from '@/lib/dashboardInsights'

/**
 * Market boot.
 *
 * Three full-width skeleton blocks were the wrong shape for this: at 230px
 * tall they dominate the viewport, they promise a layout the real dashboard
 * does not match, and the collapse from grey slabs to content is a visible
 * jolt rather than a transition.
 *
 * A small centred mark instead. It occupies almost nothing, it says the
 * application is deliberately working rather than half-rendered, and it
 * fades out as real content fades in — so the eye never has to re-anchor.
 */
function MarketBoot() {
  return (
    <WorkBoot
      label="Loading market data"
      hint="macro series, sector breadth and upcoming events"
    />
  )
}

/**
 * Terminal home: "what is happening in the market right now, and why?" —
 * answered in the hero, in one glance. Everything below it follows the
 * research-reading order: what changed since your last visit, upcoming
 * events worth watching, a visual breadth read, then the full 14-indicator
 * macro board grouped into three collapsed sections for whoever wants to
 * drill in. Same /api/dashboard call as before, same 15-minute cache —
 * this pass only changes how the response is presented.
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

  if (!data) return <MarketBoot />

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Reading order is the order an analyst actually asks the questions:
          what regime are we in, did anything change since I last looked, how
          broad is participation and where is leadership, what is the macro
          backdrop, and only then what is scheduled next.

          The calendar used to sit third, directly under the hero. At 597px
          it was the second-largest block on the page and pushed breadth —
          the thing that answers "is this rally real?" — below 1100px, so the
          question the page exists to answer lost its position to a list of
          dates nobody needs before they know the market's state. */}
      <MarketHero data={data} />
      <MarketWhatChanged data={data} />
      <BreadthHeatmap breadth={data.breadth} sectors={data.sectors} />
      <MacroSections cards={data.macro.cards} />
      <EventsTimeline events={data.events} />
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', textAlign: 'center' }}>
        Data refreshes every 15 minutes · generated {new Date(data.generated_at).toLocaleTimeString()}
      </p>
    </div>
  )
}
