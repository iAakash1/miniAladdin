'use client'

/*
 * Turning the engine's output into sentences, without turning it into advice.
 *
 * Everything here is presentation. No number is computed, adjusted or
 * re-derived — a Beginner reader and an Advanced reader are looking at the
 * same scorecard, and the only difference is how much of it is drawn.
 *
 * Three phrasings are load-bearing and are the reason this file exists rather
 * than the strings living inline:
 *
 *   - a signal is the model's, never the reader's ("OmniSignal model signal:
 *     BUY", never "you should buy")
 *   - confidence describes the evidence, never the outcome ("analysis
 *     confidence 78/100", never "78% chance of a gain")
 *   - risk describes exposure, never a probability of loss
 *
 * The first two are the difference between an educational research tool and
 * an unlicensed investment recommendation, and they are easy to lose one
 * careless label at a time.
 */

import { FACTOR_GLOSSARY, type FactorKey } from '@/lib/factorGlossary'
import type { QuantFactor } from '@/lib/types'

export interface Reason {
  key: string
  label: string
  detail: string
  contribution: number
}

/** Plain-language name for a factor, falling back to the engine's own key.
 *  The fallback is deliberate: a factor the glossary has not documented yet
 *  is still shown under its real name rather than hidden, because hiding it
 *  would silently drop a reason that moved the score. */
function describe(name: string): { label: string; detail: string } {
  const entry = FACTOR_GLOSSARY[name as FactorKey]
  if (entry) return { label: entry.label, detail: entry.short }
  return { label: name.replace(/_/g, ' '), detail: 'A factor in the scoring engine.' }
}

/**
 * The strongest factors for and against, taken from what the engine weighted.
 *
 * Derived from actual contributions, never from a phrase bank: a reason a
 * reader cannot trace back to a factor row is a reason we invented. If the
 * engine scored nothing, this returns nothing rather than filling the space.
 */
export function reasons(factors: QuantFactor[] | undefined, limit = 3): {
  positive: Reason[]
  cautious: Reason[]
} {
  const scored = (factors ?? []).filter(
    (f) => f.score !== null && Number.isFinite(f.contribution),
  )
  const toReason = (f: QuantFactor): Reason => ({
    key: f.name,
    ...describe(f.name),
    contribution: f.contribution,
  })
  return {
    positive: scored
      .filter((f) => f.contribution > 0)
      .sort((a, b) => b.contribution - a.contribution)
      .slice(0, limit)
      .map(toReason),
    cautious: scored
      .filter((f) => f.contribution < 0)
      .sort((a, b) => a.contribution - b.contribution)
      .slice(0, limit)
      .map(toReason),
  }
}

/**
 * What would have to change for the conclusion to change.
 *
 * Built from the factors actually carrying the verdict — if momentum is what
 * is holding a Buy up, momentum deteriorating is what would undermine it.
 * Nothing here predicts an event or names a date: those would be claims about
 * the future, and the evidence contains none.
 */
export function whatCouldChange(
  factors: QuantFactor[] | undefined,
  verdict: string | null,
): string[] {
  const { positive, cautious } = reasons(factors, 2)
  const out: string[] = []
  const bullish = (verdict ?? '').toLowerCase().includes('buy')

  for (const r of positive) {
    out.push(
      bullish
        ? `${r.label} weakening would remove the main support for this signal.`
        : `${r.label} strengthening further could start to outweigh the concerns.`,
    )
  }
  for (const r of cautious) {
    out.push(
      bullish
        ? `${r.label} deteriorating further would start to outweigh the support.`
        : `${r.label} recovering would remove one of the main concerns.`,
    )
  }
  out.push('A shift in the macro regime changes the gate applied to every signal.')
  return out.slice(0, 4)
}

/** One sentence on what a risk band means — exposure, never a probability. */
export function explainRisk(level: string | null, score: number | null): string {
  if (!level) {
    return 'Risk could not be measured for this security, which is not the same as it being low.'
  }
  const suffix = score === null ? '' : ` The model scores it ${score} out of 100.`
  switch (level.toUpperCase()) {
    case 'LOW':
      return `Low risk means volatility, drawdown and market sensitivity are all modest relative to the rest of the universe.${suffix}`
    case 'HIGH':
      return `High risk means this security carries notably more volatility, drawdown or market sensitivity than most of the universe.${suffix}`
    default:
      return `Medium risk means there is meaningful volatility or market sensitivity here, but it is not among the highest in the universe.${suffix}`
  }
}

/**
 * One sentence on what an analysis-confidence number means.
 *
 * Never a probability of profit. Confidence here measures how complete and
 * how internally consistent the evidence was — a high reading on a security
 * that then falls is not a contradiction, because the number was never a
 * forecast.
 */
export function explainConfidence(confidence: number | null): string {
  if (confidence === null) {
    return 'Analysis confidence could not be computed for this security.'
  }
  if (confidence >= 60) {
    return 'Most of the evidence is present, current and broadly agrees. This describes the evidence, not the likelihood of a gain.'
  }
  if (confidence >= 40) {
    return 'The evidence is reasonably complete but the factors disagree in places. This describes the evidence, not the likelihood of a gain.'
  }
  return 'Evidence is incomplete or the factors disagree materially, so the model is unsure. This describes the evidence, not the likelihood of a loss.'
}

/** Data completeness, stated as coverage rather than as accuracy. */
export function explainCompleteness(completeness: number | null): string {
  if (completeness === null) return 'Data coverage is unknown for this security.'
  const pct = Math.round(completeness * 100)
  return `${pct}% of the factors the model can compute had the data they needed. This is coverage, not accuracy.`
}

/** "OmniSignal model signal: BUY" — the model's statement, attributed. */
export function signalSentence(verdict: string | null): string {
  return verdict
    ? `OmniSignal model signal: ${verdict.toUpperCase()}.`
    : 'OmniSignal could not produce a signal for this security.'
}

export const DISCLAIMER =
  'An educational quantitative signal, not personalised investment advice.'
