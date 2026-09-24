import type { Analysis, Verdict } from '@/lib/types'

export type Tone = 'pos' | 'neg' | 'warn' | 'info' | 'muted'

export function signalTone(v: Verdict): Tone {
  if (v === 'Buy' || v === 'Strong Buy') return 'pos'
  if (v === 'Sell' || v === 'Strong Sell') return 'neg'
  return 'muted'
}

export function verdictWord(v: Verdict): string {
  return v
}

/** Every vendor that contributed at least one input to this run. */
export function providerSet(a: Analysis): string[] {
  const out = new Set<string>()
  for (const s of a.provenance?.summary.sources ?? []) {
    for (const part of s.split(',')) {
      const v = part.trim()
      if (v) out.add(v)
    }
  }
  return [...out].sort()
}

/** Plain names for the engine's factor keys. */
export const FACTOR_NAMES: Record<string, string> = {
  r12_1: '12-1 month momentum',
  r63: '63-day momentum',
  r21: '21-day momentum (timing)',
  vol_confirm: 'Volume confirmation',
  high52_prox: '52-week-high proximity',
  rel21_vs_spy: 'Relative strength vs SPY',
  reversal: 'Short-term reversal',
  pead: 'Post-earnings drift',
  gross_profitability: 'Gross profitability (GP/A)',
  net_issuance: 'Net share issuance',
  asset_growth: 'Asset growth',
  sentiment: 'News sentiment',
  earnings_yield: 'Earnings yield',
  target_upside: 'Analyst target upside',
  pe_gap: 'P/E gap to sector',
}

export function factorName(key: string): string {
  return FACTOR_NAMES[key] ?? key.replace(/_/g, ' ')
}

export const FAMILY_ORDER = ['momentum', 'fundamental', 'quality', 'news', 'reversal'] as const

export const FAMILY_LABEL: Record<string, string> = {
  momentum: 'Momentum',
  fundamental: 'Fundamental',
  quality: 'Quality',
  news: 'News',
  reversal: 'Reversal',
}

/** The family score the scorecard carries for a family key. */
export function familyScore(a: Analysis, family: string): number | null {
  const q = a.quant
  if (!q) return null
  switch (family) {
    case 'momentum': return q.momentumScore
    case 'fundamental': return q.fundamentalScore
    case 'quality': return q.qualityScore
    case 'news': return q.newsScore
    case 'reversal': return q.reversalScore
    default: return null
  }
}

/** Relative age in words, or null for an unparseable stamp. */
export function age(iso: string | null | undefined): string | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return null
  const m = Math.round((Date.now() - t) / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
