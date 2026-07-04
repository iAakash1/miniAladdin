/* Tests for the pure Market Dashboard derivations (Phase: Market Dashboard
   UX) — regime labeling, quick signals, the deterministic hero summary,
   macro card grouping, and heatmap intensity. */

import assert from 'node:assert/strict'
import test from 'node:test'
import {
  type Breadth,
  type DashboardData,
  type EventRow,
  eventBucket,
  eventsWithBuckets,
  groupMacroCards,
  heatIntensity,
  heroSummary,
  type IndexQuote,
  type MacroCard,
  marketTrend,
  quickSignals,
  type Regime,
  regimeLabel,
  signalConfidence,
} from '../src/lib/dashboardInsights'

function card(overrides: Partial<MacroCard> = {}): MacroCard {
  return {
    id: 'FEDFUNDS',
    label: 'Federal Funds Rate',
    value: 4.5,
    previous: 4.5,
    change: 0,
    direction: 'flat',
    unit: '%',
    trend: [4.5, 4.5, 4.5],
    updated: '2026-07-01',
    explain: "The Fed's policy rate.",
    ...overrides,
  }
}

function regime(overrides: Partial<Regime> = {}): Regime {
  return { available: true, risk_multiplier: 1.0, status: 'STABLE', yield_curve: 'normal', ...overrides }
}

function breadth(overrides: Partial<Breadth> = {}): Breadth {
  return {
    indexes: [], sectors_above_50d: 6, sector_count: 11, breadth_score: 55,
    explain: 'Breadth score explain.', leadership: 'Technology', laggard: 'Utilities',
    ...overrides,
  }
}

function dashboard(overrides: Partial<{ macro: DashboardData['macro']; breadth: Breadth }> = {}) {
  return {
    macro: { cards: [], regime: regime(), note: '', ...overrides.macro },
    breadth: overrides.breadth ?? breadth(),
  }
}

/* ── regimeLabel ───────────────────────────────────────────────────────────── */

test('regimeLabel maps STABLE/ELEVATED/CRITICAL to Low/Moderate/High Risk', () => {
  assert.deepEqual(regimeLabel(regime({ status: 'STABLE' })), { label: 'Low Risk', tone: 'pos' })
  assert.deepEqual(regimeLabel(regime({ status: 'ELEVATED' })), { label: 'Moderate Risk', tone: 'warn' })
  assert.deepEqual(regimeLabel(regime({ status: 'CRITICAL' })), { label: 'High Risk', tone: 'neg' })
})

test('regimeLabel handles an unavailable regime without guessing', () => {
  assert.deepEqual(regimeLabel(regime({ available: false, status: undefined })), {
    label: 'Regime unavailable', tone: 'neutral',
  })
})

/* ── quickSignals ──────────────────────────────────────────────────────────── */

test('quickSignals derives Momentum from the breadth score', () => {
  const bullish = quickSignals(dashboard({ breadth: breadth({ breadth_score: 72 }) }))
  const momentum = bullish.find((s) => s.id === 'momentum')
  assert.equal(momentum?.value, 'Bullish')
  assert.equal(momentum?.tone, 'pos')

  const bearish = quickSignals(dashboard({ breadth: breadth({ breadth_score: 20 }) }))
  assert.equal(bearish.find((s) => s.id === 'momentum')?.value, 'Bearish')
})

test('quickSignals derives Liquidity from the Dollar Index direction', () => {
  const macro = { cards: [card({ id: 'DTWEXBGS', direction: 'up' })], regime: regime(), note: '' }
  const signals = quickSignals(dashboard({ macro }))
  const liquidity = signals.find((s) => s.id === 'liquidity')
  assert.equal(liquidity?.value, 'Tightening')
  assert.equal(liquidity?.tone, 'warn')
})

test('quickSignals derives Inflation from headline CPI direction', () => {
  const macro = { cards: [card({ id: 'CPIAUCSL', direction: 'down', change: -0.3 })], regime: regime(), note: '' }
  const signals = quickSignals(dashboard({ macro }))
  const inflation = signals.find((s) => s.id === 'inflation')
  assert.equal(inflation?.value, 'Cooling')
  assert.equal(inflation?.tone, 'pos')
})

test('quickSignals derives Yield Curve from regime.yield_curve', () => {
  const signals = quickSignals(dashboard({ macro: { cards: [], regime: regime({ yield_curve: 'inverted' }), note: '' } }))
  const curve = signals.find((s) => s.id === 'yield-curve')
  assert.equal(curve?.value, 'Inverted')
  assert.equal(curve?.tone, 'warn')
})

test('quickSignals never includes a fabricated Credit signal', () => {
  const signals = quickSignals(dashboard())
  assert.ok(!signals.some((s) => s.id === 'credit'))
})

/* ── signalConfidence ──────────────────────────────────────────────────────── */

test('signalConfidence is the share of signals that are not warning/negative', () => {
  const signals = [
    { id: 'a', label: 'A', value: 'x', tone: 'pos' as const, explain: '' },
    { id: 'b', label: 'B', value: 'x', tone: 'pos' as const, explain: '' },
    { id: 'c', label: 'C', value: 'x', tone: 'warn' as const, explain: '' },
    { id: 'd', label: 'D', value: 'x', tone: 'neg' as const, explain: '' },
  ]
  assert.equal(signalConfidence(signals), 50)
})

test('signalConfidence is 0 for an empty signal list, not NaN', () => {
  assert.equal(signalConfidence([]), 0)
})

/* ── marketTrend ───────────────────────────────────────────────────────────── */

function index(overrides: Partial<IndexQuote> = {}): IndexQuote {
  return { symbol: 'SPY', price: 500, change_1d: 0.1, change_1w: 1.2, ...overrides }
}

test('marketTrend reads SPY 1-week change and applies a deadband around zero', () => {
  assert.equal(marketTrend([index({ change_1w: 1.2 })]).label, 'Up')
  assert.equal(marketTrend([index({ change_1w: -1.2 })]).label, 'Down')
  assert.equal(marketTrend([index({ change_1w: 0.1 })]).label, 'Flat')
})

test('marketTrend is Flat with no changePct when SPY is missing', () => {
  assert.deepEqual(marketTrend([index({ symbol: 'QQQ' })]), { label: 'Flat', changePct: null })
})

/* ── heroSummary ───────────────────────────────────────────────────────────── */

test('heroSummary produces at most three sentences, all traceable to real fields', () => {
  const macro = {
    cards: [
      card({ id: 'CPIAUCSL', direction: 'down' }),
      card({ id: 'UNRATE', direction: 'up' }),
    ],
    regime: regime({ status: 'ELEVATED', risk_multiplier: 1.25 }),
    note: '',
  }
  const summary = heroSummary({ macro, breadth: breadth({ breadth_score: 65, leadership: 'Technology' }) })
  const sentenceCount = summary.split('. ').filter(Boolean).length
  assert.ok(sentenceCount <= 3)
  assert.match(summary, /cautious/)
  assert.match(summary, /1\.25/)
  assert.match(summary, /cool/)
  assert.match(summary, /softening/)
  assert.match(summary, /Technology/)
})

test('heroSummary degrades gracefully when the regime is unavailable', () => {
  const summary = heroSummary({
    macro: { cards: [], regime: regime({ available: false, status: undefined }), note: '' },
    breadth: breadth({ breadth_score: null }),
  })
  assert.equal(summary, '')
})

/* ── groupMacroCards ───────────────────────────────────────────────────────── */

test('groupMacroCards buckets known series ids into Economic/Rates/Inflation', () => {
  const cards = [
    card({ id: 'A191RL1Q225SBEA' }), // GDP -> economic
    card({ id: 'DGS10' }), // 10Y -> rates
    card({ id: 'PPIACO' }), // PPI -> inflation
    card({ id: 'SOME_UNKNOWN_SERIES' }),
  ]
  const groups = groupMacroCards(cards)
  assert.equal(groups.economic.length, 1)
  assert.equal(groups.rates.length, 1)
  assert.equal(groups.inflation.length, 1)
  const total = groups.economic.length + groups.rates.length + groups.inflation.length
  assert.equal(total, 3) // the unknown series is dropped, not mis-filed
})

/* ── heatIntensity ─────────────────────────────────────────────────────────── */

test('heatIntensity floors at a visible minimum and caps at the range ceiling', () => {
  assert.equal(heatIntensity(null), 0)
  assert.equal(heatIntensity(0), 6) // floor — still visibly colored
  const capped = heatIntensity(50, 15) // far beyond the cap
  assert.equal(capped, 6 + 32)
})

test('heatIntensity scales monotonically with magnitude', () => {
  const small = heatIntensity(2, 15)
  const large = heatIntensity(10, 15)
  assert.ok(large > small)
})

/* ── eventBucket ───────────────────────────────────────────────────────────── */

test('eventBucket labels days-away into Today/Tomorrow/This week/Later', () => {
  assert.equal(eventBucket(0), 'Today')
  assert.equal(eventBucket(1), 'Tomorrow')
  assert.equal(eventBucket(5), 'This week')
  assert.equal(eventBucket(7), 'This week')
  assert.equal(eventBucket(8), 'Later')
})

function event(overrides: Partial<EventRow> = {}): EventRow {
  return {
    date: '2026-07-04', type: 'CPI', title: 'June CPI release', importance: 'high',
    days_away: 0, historical_move: null, explain: '', ...overrides,
  }
}

test('eventsWithBuckets marks only the first row of each consecutive bucket', () => {
  const rows = eventsWithBuckets([
    event({ days_away: 0, type: 'CPI' }),
    event({ days_away: 1, type: 'PPI' }),
    event({ days_away: 5, type: 'Jobs Report' }),
    event({ days_away: 6, type: 'FOMC' }),
  ])
  assert.deepEqual(rows.map((r) => [r.bucket, r.showBucket]), [
    ['Today', true],
    ['Tomorrow', true],
    ['This week', true],
    ['This week', false],
  ])
})

test('eventsWithBuckets returns an empty array for an empty input without mutating anything external', () => {
  assert.deepEqual(eventsWithBuckets([]), [])
})
