/* Tests for the pure market-level "what changed" diff logic (Research UX
   pass — the market-wide counterpart to lib/history.ts's diffSnapshots). */

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  diffMarketSnapshots,
  snapshotFromDashboard,
  type MarketSnapshot,
} from '../src/lib/marketHistory'
import type { DashboardData, MacroCard, IndexQuote } from '../src/lib/dashboardInsights'

function snap(overrides: Partial<MarketSnapshot> = {}): MarketSnapshot {
  return {
    ts: '2026-07-01T00:00:00Z',
    regimeStatus: 'STABLE',
    riskMultiplier: 1.0,
    yieldCurve: 'normal',
    breadthScore: 55,
    leadership: 'Technology',
    laggard: 'Utilities',
    vix: 15,
    fedRate: 4.5,
    cpiValue: 3.0,
    cpiDirection: 'flat',
    spyChange1w: 0.5,
    ...overrides,
  }
}

function indexQuote(overrides: Partial<IndexQuote> = {}): IndexQuote {
  return { symbol: 'SPY', price: 500, change_1d: 0.2, change_1w: 0.5, ...overrides }
}

function macroCard(overrides: Partial<MacroCard> = {}): MacroCard {
  return {
    id: 'FEDFUNDS', label: 'Federal Funds Rate', value: 4.5, previous: 4.5, change: 0,
    direction: 'flat', unit: '%', trend: [4.5], updated: '2026-07-01', explain: '',
    ...overrides,
  }
}

function dashboardFixture(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    macro: {
      cards: [macroCard(), macroCard({ id: 'CPIAUCSL', value: 3.0, direction: 'flat' })],
      regime: { available: true, status: 'STABLE', risk_multiplier: 1.0, yield_curve: 'normal' },
      note: '',
    },
    breadth: {
      indexes: [indexQuote({ symbol: 'SPY' }), indexQuote({ symbol: 'VIX', price: 15, change_1d: 0, change_1w: 0 })],
      sectors_above_50d: 6, sector_count: 11, breadth_score: 55,
      explain: '', leadership: 'Technology', laggard: 'Utilities',
    },
    sectors: [],
    events: [],
    generated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  }
}

/* ── snapshotFromDashboard ─────────────────────────────────────────────── */

test('snapshotFromDashboard extracts the hero-driving fields from a dashboard payload', () => {
  const snapshot = snapshotFromDashboard(dashboardFixture())
  assert.equal(snapshot.regimeStatus, 'STABLE')
  assert.equal(snapshot.breadthScore, 55)
  assert.equal(snapshot.leadership, 'Technology')
  assert.equal(snapshot.laggard, 'Utilities')
  assert.equal(snapshot.vix, 15)
  assert.equal(snapshot.fedRate, 4.5)
  assert.equal(snapshot.cpiValue, 3.0)
  assert.equal(snapshot.spyChange1w, 0.5)
})

test('snapshotFromDashboard nulls out regime fields when the regime is unavailable, rather than guessing', () => {
  const snapshot = snapshotFromDashboard(dashboardFixture({
    macro: { cards: [], regime: { available: false }, note: '' },
  }))
  assert.equal(snapshot.regimeStatus, null)
  assert.equal(snapshot.yieldCurve, null)
})

/* ── diffMarketSnapshots ───────────────────────────────────────────────── */

test('flags a regime escalation as negative and de-escalation as positive', () => {
  const escalation = diffMarketSnapshots(snap({ regimeStatus: 'STABLE' }), snap({ regimeStatus: 'CRITICAL' }))
  const regimeChange = escalation.find((c) => c.id === 'regime')
  assert.ok(regimeChange)
  assert.equal(regimeChange?.tone, 'neg')
  assert.match(regimeChange!.text, /Low Risk.*High Risk/)

  const deescalation = diffMarketSnapshots(snap({ regimeStatus: 'CRITICAL' }), snap({ regimeStatus: 'STABLE' }))
  assert.equal(deescalation.find((c) => c.id === 'regime')?.tone, 'pos')
})

test('flags a yield curve inversion and its resolution', () => {
  const inverted = diffMarketSnapshots(snap({ yieldCurve: 'normal' }), snap({ yieldCurve: 'inverted' }))
  const change = inverted.find((c) => c.id === 'yield-curve')
  assert.equal(change?.tone, 'warn')
  assert.match(change!.text, /inverted/)

  const resolved = diffMarketSnapshots(snap({ yieldCurve: 'inverted' }), snap({ yieldCurve: 'normal' }))
  assert.equal(resolved.find((c) => c.id === 'yield-curve')?.tone, 'pos')
})

test('only flags breadth moves at or above the 10-point threshold', () => {
  const small = diffMarketSnapshots(snap({ breadthScore: 55 }), snap({ breadthScore: 60 }))
  assert.equal(small.find((c) => c.id === 'breadth'), undefined)

  const large = diffMarketSnapshots(snap({ breadthScore: 55 }), snap({ breadthScore: 70 }))
  const change = large.find((c) => c.id === 'breadth')
  assert.ok(change)
  assert.equal(change?.tone, 'pos')
  assert.match(change!.text, /55%.*70%/)
})

test('flags sector leadership and laggard changes independently', () => {
  const changes = diffMarketSnapshots(
    snap({ leadership: 'Technology', laggard: 'Utilities' }),
    snap({ leadership: 'Energy', laggard: 'Real Estate' }),
  )
  assert.ok(changes.find((c) => c.id === 'leadership'))
  assert.ok(changes.find((c) => c.id === 'laggard'))
})

test('only flags VIX moves at or above the 15% relative threshold', () => {
  const small = diffMarketSnapshots(snap({ vix: 15 }), snap({ vix: 16 }))
  assert.equal(small.find((c) => c.id === 'vix'), undefined)

  const spike = diffMarketSnapshots(snap({ vix: 15 }), snap({ vix: 20 }))
  const change = spike.find((c) => c.id === 'vix')
  assert.ok(change)
  assert.equal(change?.tone, 'warn')

  const drop = diffMarketSnapshots(snap({ vix: 20 }), snap({ vix: 15 }))
  assert.equal(drop.find((c) => c.id === 'vix')?.tone, 'pos')
})

test('flags a CPI direction change and a Fed rate change', () => {
  const cpi = diffMarketSnapshots(snap({ cpiDirection: 'flat' }), snap({ cpiDirection: 'up' }))
  assert.equal(cpi.find((c) => c.id === 'cpi')?.tone, 'warn')

  const cut = diffMarketSnapshots(snap({ fedRate: 4.5 }), snap({ fedRate: 4.25 }))
  const fedChange = cut.find((c) => c.id === 'fed')
  assert.ok(fedChange)
  assert.equal(fedChange?.tone, 'pos')
  assert.match(fedChange!.text, /cut/)

  const hike = diffMarketSnapshots(snap({ fedRate: 4.25 }), snap({ fedRate: 4.5 }))
  assert.match(hike.find((c) => c.id === 'fed')!.text, /raised/)
})

test('returns no changes for two identical snapshots', () => {
  const identical = diffMarketSnapshots(snap(), snap())
  assert.deepEqual(identical, [])
})
