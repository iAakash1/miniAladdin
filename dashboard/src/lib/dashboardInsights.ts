/*
 * Pure derivations for the Market Dashboard hero + sections (Phase: Market
 * Dashboard UX). Every function here takes the exact payload already
 * returned by GET /api/dashboard (see src/services/dashboard_service.py)
 * and reshapes/summarizes it for presentation — nothing here calls a new
 * endpoint, invents a data point, or asks a model to guess. That keeps the
 * hero's "AI Summary" honest: it is a deterministic template over real
 * fields, not a generated one, so it can never hallucinate.
 *
 * Kept pure and side-effect-free so it's unit-testable the same way
 * lib/history.ts's diffSnapshots and lib/search.ts's localMatches are.
 */

export type Tone = 'pos' | 'neg' | 'warn' | 'neutral'

export interface MacroCard {
  id: string
  label: string
  value: number
  previous: number | null
  change: number | null
  direction: 'up' | 'down' | 'flat'
  unit: string
  trend: number[]
  updated: string
  explain: string
}

export interface Regime {
  available: boolean
  risk_multiplier?: number
  status?: string
  yield_curve?: string
  recession_warning?: boolean
  explain?: string
}

export interface IndexQuote {
  symbol: string
  price: number
  change_1d: number | null
  change_1w: number | null
}

export interface Breadth {
  indexes: IndexQuote[]
  sectors_above_50d: number
  sector_count: number
  breadth_score: number | null
  explain: string
  leadership: string | null
  laggard: string | null
}

export interface SectorRow {
  symbol: string
  name: string
  price: number
  strength_21d: number | null
  momentum_63d: number | null
  volatility: number
  above_50d: boolean
  verdict: string
}

export interface EventRow {
  date: string
  type: string
  title: string
  importance: string
  days_away: number
  historical_move: number | null
  explain: string
}

export interface DashboardData {
  macro: { cards: MacroCard[]; regime: Regime; note: string }
  breadth: Breadth
  sectors: SectorRow[]
  events: EventRow[]
  generated_at: string
}

/* ── FRED series ids (src/services/dashboard_service.py MACRO_SERIES) ────── */

export const SERIES = {
  fed: 'FEDFUNDS',
  tenYear: 'DGS10',
  twoYear: 'DGS2',
  curve: 'T10Y2Y',
  realYield: 'DFII10',
  dollar: 'DTWEXBGS',
  cpi: 'CPIAUCSL',
  coreCpi: 'CPILFESL',
  ppi: 'PPIACO',
  unemployment: 'UNRATE',
  gdp: 'A191RL1Q225SBEA',
  retail: 'RSAFS',
  sentiment: 'UMCSENT',
  housing: 'HOUST',
} as const

export function findCard(cards: MacroCard[], id: string): MacroCard | undefined {
  return cards.find((card) => card.id === id)
}

/* ── Regime label ─────────────────────────────────────────────────────────── */

export interface RegimeLabel {
  label: string
  tone: Tone
}

/** Maps the engine's MacroStatus (STABLE/ELEVATED/CRITICAL —
 * src/models.py) straight to a hero-grade label. Nothing invented. */
export function regimeLabel(regime: Regime): RegimeLabel {
  if (!regime.available || !regime.status) return { label: 'Regime unavailable', tone: 'neutral' }
  switch (regime.status) {
    case 'CRITICAL':
      return { label: 'High Risk', tone: 'neg' }
    case 'ELEVATED':
      return { label: 'Moderate Risk', tone: 'warn' }
    case 'STABLE':
      return { label: 'Low Risk', tone: 'pos' }
    default:
      return { label: regime.status, tone: 'neutral' }
  }
}

/* ── Quick signals ─────────────────────────────────────────────────────────── */

export interface QuickSignal {
  id: string
  label: string
  value: string
  tone: Tone
  explain: string
}

/**
 * Five compact badges, each traceable to a real field:
 *   Momentum   <- breadth score (share of sectors above their 50-day avg)
 *   Macro      <- regime.status (systemic risk multiplier bucket)
 *   Liquidity  <- Dollar Index direction (a stronger dollar tightens
 *                 global financial conditions — already the documented
 *                 explanation on that FRED card)
 *   Inflation  <- headline CPI direction
 *   Yield Curve<- regime.yield_curve (10Y-2Y inversion)
 * "Credit" was dropped from the original mock-up: there is no free credit-
 * spread series in MACRO_SERIES, and this codebase's own convention is to
 * omit what has no real source rather than invent it (see dashboard_service
 * .py's ISM/PMI and constituent-membership notes).
 */
export function quickSignals(data: Pick<DashboardData, 'macro' | 'breadth'>): QuickSignal[] {
  const { cards, regime } = data.macro
  const signals: QuickSignal[] = []

  if (data.breadth.breadth_score !== null) {
    const score = data.breadth.breadth_score
    signals.push({
      id: 'momentum',
      label: 'Momentum',
      value: score >= 60 ? 'Bullish' : score <= 40 ? 'Bearish' : 'Neutral',
      tone: score >= 60 ? 'pos' : score <= 40 ? 'neg' : 'neutral',
      explain: `${score}% of sectors trade above their 50-day average.`,
    })
  }

  if (regime.available && regime.status) {
    signals.push({
      id: 'macro',
      label: 'Macro',
      value: regime.status === 'STABLE' ? 'Stable' : regime.status === 'ELEVATED' ? 'Caution' : 'Stressed',
      tone: regime.status === 'STABLE' ? 'pos' : regime.status === 'ELEVATED' ? 'warn' : 'neg',
      explain: regime.explain ?? 'Systemic Risk Multiplier composite.',
    })
  }

  const dollar = findCard(cards, SERIES.dollar)
  if (dollar) {
    signals.push({
      id: 'liquidity',
      label: 'Liquidity',
      value: dollar.direction === 'up' ? 'Tightening' : dollar.direction === 'down' ? 'Easing' : 'Stable',
      tone: dollar.direction === 'up' ? 'warn' : dollar.direction === 'down' ? 'pos' : 'neutral',
      explain: 'A stronger dollar tightens global financial conditions; a weaker one eases them.',
    })
  }

  const cpi = findCard(cards, SERIES.cpi)
  if (cpi) {
    signals.push({
      id: 'inflation',
      label: 'Inflation',
      value: cpi.direction === 'down' ? 'Cooling' : cpi.direction === 'up' ? 'Rising' : 'Stable',
      tone: cpi.direction === 'down' ? 'pos' : cpi.direction === 'up' ? 'warn' : 'neutral',
      explain: `Headline CPI is ${fmtSign(cpi.change)}${cpi.change !== null ? Math.abs(cpi.change) : ''}pp year-over-year vs. the prior reading.`,
    })
  }

  if (regime.available && regime.yield_curve) {
    signals.push({
      id: 'yield-curve',
      label: 'Yield Curve',
      value: regime.yield_curve === 'inverted' ? 'Inverted' : 'Normal',
      tone: regime.yield_curve === 'inverted' ? 'warn' : 'pos',
      explain: 'Curve inversion (10Y below 2Y) has preceded past recessions.',
    })
  }

  return signals
}

function fmtSign(value: number | null): string {
  if (value === null) return ''
  return value > 0 ? '+' : value < 0 ? '-' : ''
}

/** Share of quick signals that are not flashing a warning — a transparent,
 * recomputable "how aligned is the picture right now" score. Not a model
 * confidence estimate; the label says so via its tooltip. */
export function signalConfidence(signals: QuickSignal[]): number {
  if (signals.length === 0) return 0
  const aligned = signals.filter((signal) => signal.tone !== 'warn' && signal.tone !== 'neg').length
  return Math.round((aligned / signals.length) * 100)
}

/* ── Trend (SPY, 1-week) ───────────────────────────────────────────────────── */

export interface MarketTrend {
  label: 'Up' | 'Down' | 'Flat'
  changePct: number | null
}

const TREND_DEADBAND_PCT = 0.5 // +/- half a percent counts as "flat", not noise

export function marketTrend(indexes: IndexQuote[]): MarketTrend {
  const spy = indexes.find((index) => index.symbol === 'SPY')
  if (!spy || spy.change_1w === null) return { label: 'Flat', changePct: null }
  if (spy.change_1w > TREND_DEADBAND_PCT) return { label: 'Up', changePct: spy.change_1w }
  if (spy.change_1w < -TREND_DEADBAND_PCT) return { label: 'Down', changePct: spy.change_1w }
  return { label: 'Flat', changePct: spy.change_1w }
}

/* ── Hero summary (deterministic — no model call) ─────────────────────────── */

/** Up to three sentences, each built only from fields already present in
 * the payload. No network call, no LLM — see module docstring. */
export function heroSummary(data: Pick<DashboardData, 'macro' | 'breadth'>): string {
  const { regime, cards } = data.macro
  const sentences: string[] = []

  if (regime.available && regime.status && regime.risk_multiplier !== undefined) {
    const tone = regime.status === 'STABLE' ? 'constructive'
      : regime.status === 'ELEVATED' ? 'cautious' : 'stressed'
    sentences.push(
      `Markets remain ${tone}, with a systemic risk multiplier of ${regime.risk_multiplier.toFixed(2)}${regime.yield_curve === 'inverted' ? ' and an inverted yield curve' : ''}.`,
    )
  }

  const cpi = findCard(cards, SERIES.cpi)
  const unemployment = findCard(cards, SERIES.unemployment)
  if (cpi) {
    const cpiPhrase = cpi.direction === 'down' ? 'continues to cool'
      : cpi.direction === 'up' ? 'is accelerating' : 'is holding steady'
    const laborPhrase = unemployment
      ? unemployment.direction === 'up' ? 'labor conditions are softening'
        : unemployment.direction === 'down' ? 'the labor market is tightening'
          : 'labor conditions look stable'
      : null
    sentences.push(`Inflation ${cpiPhrase}${laborPhrase ? ` while ${laborPhrase}` : ''}.`)
  }

  if (data.breadth.breadth_score !== null) {
    const score = data.breadth.breadth_score
    const breadthPhrase = score >= 60 ? 'broad participation across sectors'
      : score <= 40 ? 'narrowing sector participation' : 'mixed sector participation'
    sentences.push(
      `Breadth shows ${breadthPhrase}${data.breadth.leadership ? `, led by ${data.breadth.leadership}` : ''}.`,
    )
  }

  return sentences.slice(0, 3).join(' ')
}

/* ── Macro card grouping ───────────────────────────────────────────────────── */

export type MacroGroupId = 'economic' | 'rates' | 'inflation'

const GROUP_BY_SERIES: Record<string, MacroGroupId> = {
  [SERIES.gdp]: 'economic',
  [SERIES.retail]: 'economic',
  [SERIES.sentiment]: 'economic',
  [SERIES.housing]: 'economic',
  [SERIES.unemployment]: 'economic',
  [SERIES.fed]: 'rates',
  [SERIES.tenYear]: 'rates',
  [SERIES.twoYear]: 'rates',
  [SERIES.curve]: 'rates',
  [SERIES.realYield]: 'rates',
  [SERIES.dollar]: 'rates',
  [SERIES.cpi]: 'inflation',
  [SERIES.coreCpi]: 'inflation',
  [SERIES.ppi]: 'inflation',
}

export const MACRO_GROUP_TITLES: Record<MacroGroupId, string> = {
  economic: 'Economic Conditions',
  rates: 'Interest Rates',
  inflation: 'Inflation',
}

/** Buckets the flat card list the API returns into the three named groups
 * the dashboard now presents as separate expandable sections. A card whose
 * id isn't recognized is dropped rather than mis-filed. */
export function groupMacroCards(cards: MacroCard[]): Record<MacroGroupId, MacroCard[]> {
  const groups: Record<MacroGroupId, MacroCard[]> = { economic: [], rates: [], inflation: [] }
  for (const card of cards) {
    const group = GROUP_BY_SERIES[card.id]
    if (group) groups[group].push(card)
  }
  return groups
}

/* ── Sector heatmap intensity ──────────────────────────────────────────────── */

const HEAT_FLOOR_PCT = 6
const HEAT_RANGE_PCT = 32

/** Maps a 21-day strength reading to a 0-100 color-mix strength for
 * heatmap tiles, capped so a single outlier sector doesn't wash out the
 * rest, and floored so even a flat sector still reads as colored. Kept in
 * the 6-38% band deliberately — the same order of magnitude as the
 * existing --pos-wash/--neg-wash tokens — so tile text never loses
 * contrast against its own background. */
export function heatIntensity(value: number | null, capPct = 15): number {
  if (value === null) return 0
  return HEAT_FLOOR_PCT + Math.round(Math.min(Math.abs(value) / capPct, 1) * HEAT_RANGE_PCT)
}

/* ── Events timeline bucketing ─────────────────────────────────────────────── */

export function eventBucket(daysAway: number): 'Today' | 'Tomorrow' | 'This week' | 'Later' {
  if (daysAway === 0) return 'Today'
  if (daysAway === 1) return 'Tomorrow'
  if (daysAway <= 7) return 'This week'
  return 'Later'
}

export interface BucketedEvent {
  event: EventRow
  bucket: string
  /** True for the first event in each bucket — the row that should render
   * the "Today"/"Tomorrow"/... heading. Computed here, once, as a pure
   * fold over the (already date-sorted) list, so the rendering component
   * never has to mutate a variable across a render pass. */
  showBucket: boolean
}

export function eventsWithBuckets(events: EventRow[]): BucketedEvent[] {
  return events.reduce<BucketedEvent[]>((rows, event) => {
    const bucket = eventBucket(event.days_away)
    const showBucket = rows.length === 0 || rows[rows.length - 1].bucket !== bucket
    rows.push({ event, bucket, showBucket })
    return rows
  }, [])
}
