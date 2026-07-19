'use client'

/*
 * Verdict history — every analysis run is snapshotted client-side
 * (localStorage; this product keeps user state on the client by design —
 * same trust model as the free-tier counter). Timeline diffs compare
 * FACTOR CONTRIBUTIONS between runs, not just scores, so every verdict
 * change can say exactly why.
 */

import { useSyncExternalStore } from 'react'
import type { Analysis } from './types'

const KEY = 'omni_history_v1'
const MAX_PER_TICKER = 50
const EVENT = 'omni-history'

export interface FactorSnapshot {
  name: string
  family: string
  contribution: number
}

export interface AnalysisSnapshot {
  ts: string // ISO
  verdict: string
  rawVerdict: string | null
  confidence: number
  riskLevel: string | null
  rawScore: number | null
  momentumScore: number | null
  fundamentalScore: number | null
  newsScore: number | null
  macroGate: number | null
  srm: number
  regimes: string[]
  factors: FactorSnapshot[]
  price: number
}

export interface FactorDelta {
  name: string
  family: string
  before: number
  after: number
  delta: number
}

export interface SnapshotDiff {
  verdictChanged: boolean
  direction: 'upgrade' | 'downgrade' | 'unchanged'
  confidenceDelta: number
  scoreDelta: number | null
  topDrivers: FactorDelta[]
  gateDelta: number | null
  regimesEntered: string[]
  regimesExited: string[]
}

const VERDICT_ORDER = ['Strong Sell', 'Sell', 'Hold', 'Buy', 'Strong Buy']

/* ── storage ────────────────────────────────────────────────────────────── */

type Store = Record<string, AnalysisSnapshot[]>

function read(): Store {
  if (typeof window === 'undefined') return {}
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Store
  } catch {
    return {}
  }
}

function write(store: Store) {
  localStorage.setItem(KEY, JSON.stringify(store))
  window.dispatchEvent(new Event(EVENT))
}

let cachedRaw = ''
let cachedStore: Store = {}

function snapshotStore(): Store {
  if (typeof window === 'undefined') return cachedStore
  const raw = localStorage.getItem(KEY) ?? '{}'
  if (raw !== cachedRaw) {
    cachedRaw = raw
    try {
      cachedStore = JSON.parse(raw) as Store
    } catch {
      cachedStore = {}
    }
  }
  return cachedStore
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

/** Non-reactive read — for consumers outside React (Intelligence OS
 *  providers), matching readWatchlistsSnapshot in the watchlists store. */
export function readHistorySnapshot(): Store {
  return snapshotStore()
}

export function useHistory(ticker: string | null): AnalysisSnapshot[] {
  const store = useSyncExternalStore(subscribe, snapshotStore, () => ({}) as Store)
  return ticker ? (store[ticker.toUpperCase()] ?? []) : []
}

export function useAllHistory(): Store {
  return useSyncExternalStore(subscribe, snapshotStore, () => ({}) as Store)
}

/* ── recording ──────────────────────────────────────────────────────────── */

export function recordAnalysis(analysis: Analysis): void {
  if (typeof window === 'undefined') return
  const quant = analysis.quant
  const snapshot: AnalysisSnapshot = {
    ts: new Date().toISOString(),
    verdict: analysis.riskAdjusted,
    rawVerdict: quant?.rawVerdict ?? analysis.verdict,
    confidence: analysis.engineConfidence ?? 50,
    riskLevel: analysis.riskLevel,
    rawScore: quant?.rawScore ?? null,
    momentumScore: quant?.momentumScore ?? null,
    fundamentalScore: quant?.fundamentalScore ?? null,
    newsScore: quant?.newsScore ?? null,
    macroGate: quant?.macroGate ?? null,
    srm: analysis.macro.srm,
    regimes: quant?.regimes ?? [],
    factors: (quant?.factors ?? []).map((f) => ({
      name: f.name,
      family: f.family,
      contribution: f.contribution,
    })),
    price: analysis.price,
  }
  const store = read()
  const key = analysis.ticker.toUpperCase()
  const timeline = store[key] ?? []
  timeline.push(snapshot)
  store[key] = timeline.slice(-MAX_PER_TICKER)
  write(store)
}

/* ── diffing (pure — unit-tested) ───────────────────────────────────────── */

export function diffSnapshots(before: AnalysisSnapshot, after: AnalysisSnapshot): SnapshotDiff {
  const beforeRank = VERDICT_ORDER.indexOf(before.verdict)
  const afterRank = VERDICT_ORDER.indexOf(after.verdict)

  const beforeMap = new Map(before.factors.map((f) => [f.name, f]))
  const afterMap = new Map(after.factors.map((f) => [f.name, f]))
  const names = new Set([...beforeMap.keys(), ...afterMap.keys()])

  const deltas: FactorDelta[] = []
  for (const name of names) {
    const prev = beforeMap.get(name)
    const next = afterMap.get(name)
    const b = prev?.contribution ?? 0
    const a = next?.contribution ?? 0
    if (Math.abs(a - b) > 1e-6) {
      deltas.push({
        name,
        family: (next ?? prev)!.family,
        before: b,
        after: a,
        delta: Number((a - b).toFixed(4)),
      })
    }
  }
  deltas.sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta))

  return {
    verdictChanged: before.verdict !== after.verdict,
    direction:
      afterRank > beforeRank ? 'upgrade' : afterRank < beforeRank ? 'downgrade' : 'unchanged',
    confidenceDelta: after.confidence - before.confidence,
    scoreDelta:
      before.rawScore !== null && after.rawScore !== null
        ? Number((after.rawScore - before.rawScore).toFixed(4))
        : null,
    topDrivers: deltas.slice(0, 5),
    gateDelta:
      before.macroGate !== null && after.macroGate !== null
        ? Number((after.macroGate - before.macroGate).toFixed(4))
        : null,
    regimesEntered: after.regimes.filter((r) => !before.regimes.includes(r)),
    regimesExited: before.regimes.filter((r) => !after.regimes.includes(r)),
  }
}

/** Human labels for factor names — used by timeline explanations. */
export const FACTOR_LABELS: Record<string, string> = {
  r12_1: '12-1 momentum',
  r21: '21-day momentum (timing)',
  r63: '63-day momentum',
  rsi_dev: 'RSI deviation',
  macd_hist: 'MACD histogram',
  rev5: '5-day reversal',
  reversal: 'Reversal (5d + RSI, contrarian)',
  vol_confirm: 'Volume confirmation',
  high52_prox: '52-week-high proximity',
  rel21_vs_spy: 'Relative strength vs SPY',
  target_upside: 'Analyst target upside',
  earnings_yield: 'Earnings yield',
  pe_gap: 'Forward PE gap',
  pead: 'Post-earnings drift',
  gross_profitability: 'Gross profitability (GP/A)',
  net_issuance: 'Net share issuance',
  asset_growth: 'Asset growth',
  sentiment: 'News sentiment',
}
