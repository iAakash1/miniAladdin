/* ============================================================
   Data access layer: fetchers + normalizers.
   The Railway backend nests fields differently per endpoint;
   everything is normalized here so components never touch
   raw shapes.
   ============================================================ */

import { parsePercentString } from './format'
import type {
  AiAnalysis,
  Analysis,
  FactorImpact,
  FactorImpacts,
  Headline,
  Macro,
  PricePoint,
  QuantCard,
  RawAiAnalysis,
  RawChartResponse,
  RawFactorImpact,
  RawMacroResponse,
  RawQuant,
  RawResearchMacro,
  RawResearchResponse,
  RiskLevel,
  Verdict,
} from './types'

const EMPTY_IMPACT: FactorImpact = { contribution: 0, factors: [] }

function normalizeImpact(raw: RawFactorImpact | undefined): FactorImpact {
  if (!raw) return EMPTY_IMPACT
  return { contribution: raw.contribution ?? 0, factors: raw.factors ?? [] }
}

const VERDICTS: Verdict[] = ['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell']

export const VERDICT_SCORE: Record<Verdict, number> = {
  'Strong Buy': 6,
  Buy: 3,
  Hold: 0,
  Sell: -3,
  'Strong Sell': -6,
}

function asVerdict(v: string | undefined | null): Verdict {
  return VERDICTS.includes(v as Verdict) ? (v as Verdict) : 'Hold'
}

function asHeadlineLabel(v: string | undefined): Headline['label'] {
  return v === 'Bullish' || v === 'Bearish' ? v : 'Neutral'
}

export function normalizeMacro(raw: RawMacroResponse | RawResearchMacro | null | undefined): Macro {
  if (!raw) {
    return { srm: 1, yieldSpread: 0, cpi: 0, fedRate: 0, inverted: false, status: 'UNKNOWN', recessionWarning: false }
  }
  // /api/macro nests values under `stats`; research nests them flat.
  const stats = 'stats' in raw && raw.stats ? raw.stats : (raw as RawResearchMacro)
  return {
    srm: raw.risk_multiplier ?? 1,
    yieldSpread: stats.yield_spread ?? 0,
    cpi: parsePercentString(stats.inflation_rate),
    fedRate: parsePercentString(stats.fed_funds_rate),
    inverted: stats.yield_curve_inverted ?? false,
    status: stats.status ?? 'UNKNOWN',
    recessionWarning: stats.recession_warning ?? false,
  }
}

function asRiskLevel(v: string | undefined | null): RiskLevel | null {
  return v === 'LOW' || v === 'MEDIUM' || v === 'HIGH' ? v : null
}

export function normalizeAi(raw: RawAiAnalysis | null | undefined): AiAnalysis | null {
  if (!raw || typeof raw.executive_summary !== 'string' || !raw.executive_summary) return null
  const rec = raw.recommendation
  const impacts = raw.factor_impacts
  const factorImpacts: FactorImpacts = {
    momentum: normalizeImpact(impacts?.momentum),
    quality: normalizeImpact(impacts?.quality),
    value: normalizeImpact(impacts?.value),
    pead: normalizeImpact(impacts?.pead),
    news: normalizeImpact(impacts?.news),
  }
  return {
    recommendation: rec === 'BUY' || rec === 'SELL' ? rec : 'HOLD',
    confidence: typeof raw.confidence === 'number' ? Math.round(raw.confidence) : 50,
    risk: asRiskLevel(raw.risk) ?? 'MEDIUM',
    executiveSummary: raw.executive_summary,
    investmentThesis: raw.investment_thesis ?? '',
    verdictRationale: raw.verdict_rationale ?? '',
    bullCase: raw.bull_case ?? '',
    bearCase: raw.bear_case ?? '',
    technicalReasoning: raw.technical_reasoning ?? '',
    momentumImpact: raw.momentum_impact ?? '',
    qualityImpact: raw.quality_impact ?? '',
    valueImpact: raw.value_impact ?? '',
    peadImpact: raw.pead_impact ?? '',
    macroReasoning: raw.macro_reasoning ?? '',
    newsReasoning: raw.news_reasoning ?? '',
    riskReasoning: raw.risk_reasoning ?? '',
    confidenceReason: raw.confidence_reason ?? '',
    topPositiveNarrative: raw.top_positive_narrative ?? '',
    topNegativeNarrative: raw.top_negative_narrative ?? '',
    keyCatalysts: raw.key_catalysts ?? [],
    keyRisks: raw.key_risks ?? [],
    thingsToWatch: raw.things_to_watch ?? [],
    investmentHorizon: raw.investment_horizon ?? '',
    marketOutlook: raw.market_outlook ?? '',
    conclusion: raw.conclusion ?? '',
    factorImpacts,
    generated: raw.generated ?? false,
    model: raw.model ?? null,
  }
}

function normalizeQuant(raw: RawQuant | null | undefined): QuantCard | null {
  if (!raw || typeof raw.raw_score !== 'number') return null
  return {
    rawScore: raw.raw_score,
    ungatedScore: raw.ungated_score ?? raw.raw_score,
    verdict: raw.verdict ?? 'Hold',
    rawVerdict: raw.raw_verdict ?? raw.verdict ?? 'Hold',
    confidence: raw.confidence ?? 50,
    confidenceLosses: raw.confidence_losses ?? [],
    uncertainty: raw.uncertainty ?? 0,
    uncertaintyComponents: raw.uncertainty_components ?? {},
    conflictIndex: raw.conflict_index ?? 0,
    momentumScore: raw.momentum_score ?? null,
    fundamentalScore: raw.fundamental_score ?? null,
    qualityScore: raw.quality_score ?? null,
    newsScore: raw.news_score ?? null,
    reversalScore: raw.reversal_score ?? null,
    macroGate: raw.macro_gate ?? 1,
    stressProbability: raw.stress_probability ?? null,
    riskScore: raw.risk_score ?? 50,
    riskComponents: raw.risk_components ?? [],
    weightsUsed: raw.weights_used ?? {},
    regimes: raw.regimes ?? [],
    factors: (raw.factors ?? []).map((f) => ({
      name: f.name,
      family: f.family,
      value: f.value ?? null,
      z: f.z ?? null,
      score: f.score ?? null,
      contribution: f.contribution,
    })),
    dataCompleteness: raw.data_completeness ?? 1,
    modelVersion: raw.model_version ?? 'scoring-v2',
  }
}

export function normalizeAnalysis(raw: RawResearchResponse): Analysis {
  const t = raw.technicals ?? {}
  const s = raw.sentiment ?? null
  const verdict = asVerdict(t.raw_signal ?? raw.verdict)
  const riskAdjusted = asVerdict(t.risk_adjusted_signal ?? raw.verdict)

  return {
    ticker: raw.ticker ?? t.ticker ?? '—',
    historyId: raw.history_id ?? null,
    companyName: t.company_name ?? raw.ticker ?? '—',
    sector: t.sector ? titleCase(t.sector) : null,
    marketCap: t.market_cap ?? null,

    verdict,
    riskAdjusted,
    signalScore: VERDICT_SCORE[riskAdjusted],

    engineConfidence: typeof raw.confidence === 'number' ? raw.confidence : null,
    riskLevel: asRiskLevel(raw.risk_level),
    rationale: raw.rationale ?? null,
    quant: normalizeQuant(raw.quant),
    ai: normalizeAi(raw.ai),

    price: t.current_price ?? 0,
    return5d: t.return_5d ?? 0,
    return21d: t.return_21d ?? 0,
    volatility: t.volatility ?? 0,
    sharpe: t.sharpe_ratio ?? 0,
    sortino: t.sortino_ratio ?? 0,
    rsi: t.rsi_14 ?? 0,
    maxDrawdown: t.max_drawdown ?? 0,
    macdCrossover: t.macd_crossover ?? null,

    peRatio: t.pe_ratio ?? null,
    forwardPe: t.forward_pe ?? null,
    eps: t.eps ?? null,
    beta: t.beta ?? null,
    analystTarget: t.analyst_target ?? null,
    week52High: t.week_52_high ?? null,
    week52Low: t.week_52_low ?? null,

    sentimentScore: s?.average_score ?? null,
    sentimentLabel: s?.dominant_label ?? null,
    headlineCount: s?.headline_count ?? 0,
    headlines: (s?.headlines ?? []).map((h) => ({
      title: h.title ?? '',
      score: h.score ?? 0,
      label: asHeadlineLabel(h.label),
      source: h.source ?? '',
      url: h.url ?? '',
      publishedAt: h.published_at ?? '',
    })),

    macro: normalizeMacro(raw.macro),
    mode: raw.mode ?? 'full',
    technicalIntelligence: raw.technical_intelligence ?? null,
    streetIntelligence: raw.street_intelligence ?? null,
  }
}

export function normalizeChart(raw: RawChartResponse): PricePoint[] {
  return (raw.prices ?? []).map((p) => ({
    date: p.date,
    close: p.close,
    volume: p.volume ?? 0,
  }))
}

function titleCase(v: string): string {
  return v
    .toLowerCase()
    .split(/[\s_]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/* ---------- Client fetchers (browser, via Next rewrites to Railway) ---------- */

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function fetchAnalysis(ticker: string, fast: boolean): Promise<RawResearchResponse> {
  // The Clerk token lets the backend persist this run to the user's history
  // automatically; without it the analysis still works, just unrecorded.
  const { authFetch } = await import('./persistence')
  const res = await authFetch(`/api/research/${encodeURIComponent(ticker)}${fast ? '?fast=true' : ''}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(body?.detail || `The analysis service returned an error (${res.status}).`, res.status)
  }
  return res.json()
}

export async function fetchChart(ticker: string, period: string): Promise<RawChartResponse> {
  const res = await fetch(`/api/chart/${encodeURIComponent(ticker)}?period=${encodeURIComponent(period)}`)
  if (!res.ok) return { prices: [] }
  return res.json()
}

/*
 * Every /terminal/* page mounts TerminalHeader independently and each one
 * calls fetchMacroClient() on its own — navigating Market -> Portfolio ->
 * Validation -> Methodology in one session was firing a fresh
 * GET /api/macro on every single page mount, for a value the backend
 * itself only refreshes every 15 minutes (MacroProvider.TTL,
 * src/providers/providers.py). MACRO_CACHE_TTL_MS mirrors that same
 * short-lived-cache-plus-single-flight shape the provider layer already
 * uses server-side (src/providers/dedupe.py SingleFlight) — applied here
 * client-side for the one clearly duplicated request, not a general
 * fetch-caching layer.
 */
const MACRO_CACHE_TTL_MS = 60_000
let macroCache: { data: Macro; fetchedAt: number } | null = null
let macroInflight: Promise<Macro | null> | null = null

export async function fetchMacroClient(): Promise<Macro | null> {
  if (macroCache && Date.now() - macroCache.fetchedAt < MACRO_CACHE_TTL_MS) {
    return macroCache.data
  }
  if (macroInflight) return macroInflight

  macroInflight = (async () => {
    try {
      const res = await fetch('/api/macro')
      if (!res.ok) return null
      const data = normalizeMacro((await res.json()) as RawMacroResponse)
      macroCache = { data, fetchedAt: Date.now() }
      return data
    } catch {
      return null
    } finally {
      macroInflight = null
    }
  })()
  return macroInflight
}

