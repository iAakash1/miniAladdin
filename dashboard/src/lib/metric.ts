/**
 * A displayed value and everything a reader may ask about it.
 *
 * The product's rule since Phase 7: an element is correct only when its
 * appearance, its meaning, its source, its state, its interaction and its
 * failure behaviour all agree. A value that satisfies four of those and not
 * the fifth is a defect, not a rough edge.
 *
 * Holding those together requires them to live in one place. Scattered through
 * JSX they drift: the formatter learns the precision, the tooltip learns the
 * method, the panel header learns the source, and no single site knows enough
 * to notice when two of them disagree. `MetricPresentation` is that one place.
 *
 * It answers, for any figure on screen:
 *
 *   What is this?              kind, and the label its semantics carry
 *   What unit is it in?        from the kind, never inferred from magnitude
 *   How is it formatted?       from the kind's precision
 *   Can it be compared?        comparability class and basis
 *   What does positive mean?   direction — which is not the same as sign
 *   What does zero mean?       stated where it is not obvious
 *   What does null mean?       not recorded, which is never zero
 *   Where did it come from?    source
 *   When was it observed?      asOf, and how stale that makes it
 *   What would make it wrong?  failure conditions, from the methodology
 */

import { format, isPresent, type Formatted, type Kind } from './quantity'
import {
  comparable, delta, semanticsOf, toneFor,
  type Comparability, type Delta, type Semantics, type Tone,
} from './semantics'

/**
 * How much a reader should trust a figure, independent of how large it is.
 *
 * Kept apart from tone on purpose. A net Sharpe of +0.111 alongside a PBO of
 * 0.929 is favourable and untrustworthy simultaneously, and collapsing the two
 * into one colour is how a research product starts flattering itself.
 */
export type Evidence = 'established' | 'provisional' | 'contested' | 'unestablished'

/** Whether the figure describes now, or the last time anything was known. */
export type Observation = 'observed' | 'last-observed' | 'unavailable' | 'not-recorded'

export interface MetricInput {
  value: number | string | null | undefined
  kind: Kind
  /** What the number was measured against: a target, a horizon, a convention. */
  basis?: string
  /** Where it came from — an artifact path, an endpoint, a vendor. */
  source?: string
  /** When the underlying observation was made. */
  asOf?: string
  /** How it was computed, in one line. */
  method?: string
  /** The object it belongs to, for navigation and inspection. */
  object?: { kind: string; id: string; label?: string }
  /** What would make this figure wrong. Only conditions the methodology states. */
  failureConditions?: string[]
  evidence?: Evidence
  observation?: Observation
  /** Precision override, for a headline figure shown larger. Not an opt-out. */
  digits?: number
}

export interface MetricPresentation extends MetricInput {
  semantics: Semantics
  formatted: Formatted
  tone: Tone
  /** True when there is no value to show — the caller renders absence, not zero. */
  absent: boolean
  /** Whether this figure may be differenced against another. */
  comparableWith: (other: { kind: Kind; basis?: string }) => Comparability
  /** The difference from a baseline, with its interpretation kept separate. */
  against: (baseline: number | null | undefined, other?: { kind: Kind; basis?: string }) => Delta
}

export function metric(input: MetricInput): MetricPresentation {
  const semantics = semanticsOf(input.kind)
  const formatted = format(input.value, input.kind, { digits: input.digits })
  const numeric = isPresent(input.value) ? input.value : null

  return {
    ...input,
    semantics,
    formatted,
    tone: toneFor(numeric, input.kind),
    absent: formatted.absent,
    comparableWith: (other) => comparable({ kind: input.kind, basis: input.basis }, other),
    against: (baseline, other) =>
      delta(numeric, baseline, { kind: input.kind, basis: input.basis }, other),
  }
}

/* ── explicit formatters ─────────────────────────────────────────────────────
   A named entry point per semantic kind.

   The generic `format(value, kind)` is one positional argument away from the
   Evidence registry's failure mode: pass the wrong kind and the output is
   beautifully formatted and wrong, with nothing at the call site to read as
   suspicious. `formatCount(103)` cannot silently become a signed ratio, and
   `formatPercentage(61)` states in its own name which of 0.61 and 61 it
   expects. Making the mistake requires writing something that looks wrong. */

export const formatCount = (v: number | null | undefined) => format(v, 'count')
export const formatCorrelation = (v: number | null | undefined) => format(v, 'correlation')
export const formatIC = (v: number | null | undefined) => format(v, 'ic')
export const formatSharpe = (v: number | null | undefined) => format(v, 'sharpe')
export const formatTStat = (v: number | null | undefined) => format(v, 'tstat')
export const formatProbability = (v: number | null | undefined) => format(v, 'probability')
export const formatShare = (v: number | null | undefined) => format(v, 'share')
export const formatBasisPoints = (v: number | null | undefined) => format(v, 'bps')
export const formatVolatility = (v: number | null | undefined) => format(v, 'volatility')
export const formatDrawdown = (v: number | null | undefined) => format(v, 'drawdown')
export const formatMultiple = (v: number | null | undefined) => format(v, 'multiple')
export const formatWeight = (v: number | null | undefined) => format(v, 'weight')
export const formatReturn = (v: number | null | undefined) => format(v, 'return')
export const formatCurrency = (v: number | null | undefined) => format(v, 'currency')
export const formatSeconds = (v: number | null | undefined) => format(v, 'seconds')
export const formatZScore = (v: number | null | undefined) => format(v, 'zscore')

/**
 * A value the backend already scaled to percent — 61 meaning 61%.
 *
 * It does not multiply. A caller holding 0.61 has a fraction and must say so
 * by calling `formatShare`; converting here would mean the same function
 * rendering 0.61 and 61 identically, which is how "HIT RATE 61.000" happened
 * in the other direction.
 */
export const formatPercentage = (v: number | null | undefined) => format(v, 'percent')
