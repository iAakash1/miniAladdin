'use client'

/*
 * Market-level "what changed" — mirrors the per-ticker verdict history in
 * lib/history.ts, but keyed on a single fixed slot (there's only one
 * market) instead of per-ticker. Every dashboard load snapshots the fields
 * that actually drive the hero and quick-signal badges; the diff between
 * the two most recent snapshots is what "What changed since your last
 * visit" reports. Client-side only, same trust model as history.ts and the
 * free-tier counter — the backend has no concept of "your last visit".
 */

import { useSyncExternalStore } from 'react'
import type { DashboardData } from './dashboardInsights'

const KEY = 'omni_market_history_v1'
const MAX_SNAPSHOTS = 30
const EVENT = 'omni-market-history'

export interface MarketSnapshot {
  ts: string
  regimeStatus: string | null
  riskMultiplier: number | null
  yieldCurve: string | null
  breadthScore: number | null
  leadership: string | null
  laggard: string | null
  vix: number | null
  fedRate: number | null
  cpiValue: number | null
  cpiDirection: 'up' | 'down' | 'flat' | null
  spyChange1w: number | null
}

/* ── storage (same pattern as lib/history.ts) ──────────────────────────── */

type Snapshots = MarketSnapshot[]

function read(): Snapshots {
  if (typeof window === 'undefined') return []
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]') as Snapshots
  } catch {
    return []
  }
}

function write(snapshots: Snapshots) {
  localStorage.setItem(KEY, JSON.stringify(snapshots))
  window.dispatchEvent(new Event(EVENT))
}

let cachedRaw = ''
let cachedSnapshots: Snapshots = []

function snapshotStore(): Snapshots {
  if (typeof window === 'undefined') return cachedSnapshots
  const raw = localStorage.getItem(KEY) ?? '[]'
  if (raw !== cachedRaw) {
    cachedRaw = raw
    try {
      cachedSnapshots = JSON.parse(raw) as Snapshots
    } catch {
      cachedSnapshots = []
    }
  }
  return cachedSnapshots
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

export function useMarketHistory(): Snapshots {
  return useSyncExternalStore(subscribe, snapshotStore, () => [])
}

/* ── recording ──────────────────────────────────────────────────────────── */

/** Pure extraction — same fields the hero and quick-signal badges already
 * read from GET /api/dashboard (see lib/dashboardInsights.ts), nothing new
 * fetched or computed. */
export function snapshotFromDashboard(data: DashboardData): MarketSnapshot {
  const vix = data.breadth.indexes.find((index) => index.symbol === 'VIX')
  const spy = data.breadth.indexes.find((index) => index.symbol === 'SPY')
  const fed = data.macro.cards.find((card) => card.id === 'FEDFUNDS')
  const cpi = data.macro.cards.find((card) => card.id === 'CPIAUCSL')
  return {
    ts: data.generated_at,
    regimeStatus: data.macro.regime.available ? (data.macro.regime.status ?? null) : null,
    riskMultiplier: data.macro.regime.risk_multiplier ?? null,
    yieldCurve: data.macro.regime.available ? (data.macro.regime.yield_curve ?? null) : null,
    breadthScore: data.breadth.breadth_score,
    leadership: data.breadth.leadership,
    laggard: data.breadth.laggard,
    vix: vix ? vix.price : null,
    fedRate: fed ? fed.value : null,
    cpiValue: cpi ? cpi.value : null,
    cpiDirection: cpi ? cpi.direction : null,
    spyChange1w: spy ? spy.change_1w : null,
  }
}

/** Records the given dashboard payload as the latest snapshot, unless it's
 * an exact duplicate timestamp of the most recent one (a React remount on
 * the same unrefreshed server response) — so "since your last visit"
 * always reflects a genuinely new backend read, not a re-render. */
export function recordMarketSnapshot(data: DashboardData): void {
  if (typeof window === 'undefined') return
  const snapshot = snapshotFromDashboard(data)
  const history = read()
  const latest = history[history.length - 1]
  if (latest && latest.ts === snapshot.ts) return
  history.push(snapshot)
  write(history.slice(-MAX_SNAPSHOTS))
}

/* ── diffing (pure — unit-tested) ──────────────────────────────────────── */

export interface MarketChange {
  id: string
  text: string
  tone: 'pos' | 'neg' | 'warn' | 'neutral'
}

const REGIME_ORDER = ['STABLE', 'ELEVATED', 'CRITICAL']
const REGIME_LABEL: Record<string, string> = {
  STABLE: 'Low Risk',
  ELEVATED: 'Moderate Risk',
  CRITICAL: 'High Risk',
}

const BREADTH_MOVE_THRESHOLD = 10 // percentage points
const VIX_MOVE_THRESHOLD_PCT = 15 // relative

/** Compares the two most recent market snapshots and returns every
 * material change, each traceable to the exact fields it was computed
 * from — same "no silent black box" discipline as diffSnapshots in
 * lib/history.ts. Small, noisy wobbles are deliberately filtered by
 * threshold (see BREADTH_MOVE_THRESHOLD / VIX_MOVE_THRESHOLD_PCT) so this
 * section doesn't cry wolf on every 15-minute refresh. */
export function diffMarketSnapshots(before: MarketSnapshot, after: MarketSnapshot): MarketChange[] {
  const changes: MarketChange[] = []

  if (before.regimeStatus && after.regimeStatus && before.regimeStatus !== after.regimeStatus) {
    const escalated = REGIME_ORDER.indexOf(after.regimeStatus) > REGIME_ORDER.indexOf(before.regimeStatus)
    changes.push({
      id: 'regime',
      text: `Macro regime moved from ${REGIME_LABEL[before.regimeStatus] ?? before.regimeStatus} to ${REGIME_LABEL[after.regimeStatus] ?? after.regimeStatus}.`,
      tone: escalated ? 'neg' : 'pos',
    })
  }

  if (before.yieldCurve && after.yieldCurve && before.yieldCurve !== after.yieldCurve) {
    const invertedNow = after.yieldCurve === 'inverted'
    changes.push({
      id: 'yield-curve',
      text: invertedNow
        ? 'The yield curve inverted (10Y below 2Y).'
        : 'The yield curve returned to normal (10Y above 2Y).',
      tone: invertedNow ? 'warn' : 'pos',
    })
  }

  if (before.breadthScore !== null && after.breadthScore !== null
      && Math.abs(after.breadthScore - before.breadthScore) >= BREADTH_MOVE_THRESHOLD) {
    const rising = after.breadthScore > before.breadthScore
    changes.push({
      id: 'breadth',
      text: `Sector breadth ${rising ? 'improved' : 'weakened'} from ${before.breadthScore}% to ${after.breadthScore}% of sectors above their 50-day average.`,
      tone: rising ? 'pos' : 'neg',
    })
  }

  if (before.leadership && after.leadership && before.leadership !== after.leadership) {
    changes.push({
      id: 'leadership',
      text: `Sector leadership shifted from ${before.leadership} to ${after.leadership}.`,
      tone: 'neutral',
    })
  }

  if (before.laggard && after.laggard && before.laggard !== after.laggard) {
    changes.push({
      id: 'laggard',
      text: `The weakest sector shifted from ${before.laggard} to ${after.laggard}.`,
      tone: 'neutral',
    })
  }

  if (before.vix !== null && after.vix !== null && before.vix > 0) {
    const changePct = ((after.vix - before.vix) / before.vix) * 100
    if (Math.abs(changePct) >= VIX_MOVE_THRESHOLD_PCT) {
      const rising = changePct > 0
      changes.push({
        id: 'vix',
        text: `VIX ${rising ? 'rose' : 'fell'} ${Math.abs(changePct).toFixed(0)}% to ${after.vix.toFixed(1)}.`,
        tone: rising ? 'warn' : 'pos',
      })
    }
  }

  if (before.cpiDirection && after.cpiDirection && before.cpiDirection !== after.cpiDirection) {
    changes.push({
      id: 'cpi',
      text: `Headline CPI direction turned ${after.cpiDirection === 'down' ? 'lower' : after.cpiDirection === 'up' ? 'higher' : 'flat'}.`,
      tone: after.cpiDirection === 'down' ? 'pos' : after.cpiDirection === 'up' ? 'warn' : 'neutral',
    })
  }

  if (before.fedRate !== null && after.fedRate !== null && before.fedRate !== after.fedRate) {
    const cut = after.fedRate < before.fedRate
    changes.push({
      id: 'fed',
      text: `The Fed funds rate ${cut ? 'was cut' : 'was raised'} from ${before.fedRate.toFixed(2)}% to ${after.fedRate.toFixed(2)}%.`,
      tone: cut ? 'pos' : 'warn',
    })
  }

  return changes
}
