/**
 * What a displayed number means.
 *
 * `quantity.ts` answers how a figure is printed. This answers what it is: what
 * it can be compared with, what its sign means, whether zero is a measurement
 * or a placeholder, and what would make it wrong.
 *
 * The separation matters because every serious defect found in this product so
 * far has been semantic rather than typographic. A count printed as "+0" was
 * formatted flawlessly and claimed a change that had not happened. A hit rate
 * of 61 printed as "61.000" was arithmetically exact and stated the wrong unit.
 * A rank correlation minus a return correlation produced a well-formatted
 * number with no referent at all, tinted green because it came out positive.
 *
 * None of those are caught by a formatter. They are caught by knowing what the
 * number is.
 *
 * ── The four independent dimensions ──────────────────────────────────────
 *
 * A figure carries four things that are routinely and wrongly collapsed into
 * one another:
 *
 *   magnitude   how large it is
 *   direction   whether larger is better, worse, or neither
 *   evidence    whether it can be believed
 *   state       whether it was observed at all
 *
 * A net Sharpe of +0.111 has positive magnitude, a favourable direction, poor
 * evidence (PBO 0.929) and a recorded state. Painting it green because it is
 * positive collapses evidence into direction, and that is precisely the error
 * an evidence-first product exists to prevent. Tone here is therefore derived
 * from direction only, and evidence is carried separately for the caller to
 * render as its own signal.
 */

import { format, type Formatted, type Kind } from './quantity'

/* ── comparability ───────────────────────────────────────────────────────── */

/**
 * Two quantities may be subtracted only when they share a class.
 *
 * The class is coarser than the kind on purpose: a Sharpe and a Sortino are
 * both `risk-adjusted-return` and comparing them is defensible, while a rank
 * correlation and a return correlation are both "a correlation" and comparing
 * them is not — one measures agreement with an ordering, the other agreement
 * with a magnitude.
 */
export type ComparabilityClass =
  | 'rank-agreement'        // IC against a rank target
  | 'linear-agreement'      // correlation against a value
  | 'risk-adjusted-return'  // Sharpe, Sortino, Calmar
  | 'test-statistic'
  | 'probability'
  | 'proportion'
  | 'return'
  | 'dispersion'            // volatility, tracking error — annualised
  | 'loss'                  // drawdown, CVaR, EVaR
  | 'weight'
  | 'multiple'
  | 'money'
  | 'basis-points'
  | 'cardinality'           // counts, sessions
  | 'duration'
  | 'standardised'          // z-scores
  | 'ordinal'               // ranks
  | 'opaque'                // scores, eigenvalues: no cross-object meaning
  | 'temporal'

/** Whether a larger number is better, worse, or neither. */
export type Direction = 'higher-better' | 'lower-better' | 'neither'

/** How a difference between two of these should be expressed. */
export type DeltaKind =
  | 'absolute'      // B − A, in the metric's own units
  | 'basis-points'  // a difference already in bp
  | 'multiplicative' // a ratio, where "twice" is the meaningful statement
  | 'none'          // no difference is meaningful

export interface Semantics {
  /** What a reader should call it. */
  label: string
  class: ComparabilityClass
  direction: Direction
  delta: DeltaKind
  /**
   * Whether the payload sends a fraction (0.61) or an already-scaled figure
   * (61). Nothing is inferred from the magnitude — a hit rate of 0.61 and one
   * of 61 are both plausible, and guessing is how "61.000" reached the screen.
   */
  scale: 'unit' | 'percent' | 'none'
  /** What a measured zero means for this quantity, where it is not obvious. */
  zeroMeans?: string
  /** What its absence means, where that differs from "not measured". */
  nullMeans?: string
}

/**
 * Semantics per kind. Every kind in the quantity system appears here, so a
 * value can always answer what it is — a kind with no entry is a kind whose
 * meaning nobody has decided, and that is worth failing a test over.
 */
export const SEMANTICS: Record<Kind, Semantics> = {
  ic: {
    label: 'information coefficient', class: 'rank-agreement',
    direction: 'higher-better', delta: 'absolute', scale: 'unit',
    zeroMeans: 'no measured agreement between the prediction and the outcome',
  },
  correlation: {
    label: 'correlation', class: 'linear-agreement',
    direction: 'neither', delta: 'absolute', scale: 'unit',
    zeroMeans: 'no linear relationship in this sample',
  },
  ratio: {
    label: 'ratio', class: 'opaque',
    direction: 'neither', delta: 'absolute', scale: 'none',
  },
  sharpe: {
    label: 'Sharpe ratio', class: 'risk-adjusted-return',
    direction: 'higher-better', delta: 'absolute', scale: 'none',
    zeroMeans: 'return indistinguishable from the risk-free rate over the window',
  },
  tstat: {
    label: 't-statistic', class: 'test-statistic',
    direction: 'neither', delta: 'absolute', scale: 'none',
    zeroMeans: 'the estimate sits exactly on the null',
  },
  probability: {
    label: 'probability', class: 'probability',
    direction: 'neither', delta: 'absolute', scale: 'unit',
  },
  share: {
    label: 'share', class: 'proportion',
    direction: 'neither', delta: 'absolute', scale: 'unit',
  },
  percent: {
    label: 'percentage', class: 'proportion',
    direction: 'neither', delta: 'absolute', scale: 'percent',
  },
  return: {
    label: 'return', class: 'return',
    direction: 'higher-better', delta: 'absolute', scale: 'unit',
  },
  magnitude: {
    label: 'magnitude', class: 'loss',
    direction: 'lower-better', delta: 'absolute', scale: 'none',
  },
  volatility: {
    label: 'annualised volatility', class: 'dispersion',
    direction: 'neither', delta: 'absolute', scale: 'unit',
    zeroMeans: 'no variation in the sample, which usually means too few observations',
  },
  drawdown: {
    // Signed negative by convention, and the registry confirms it: every
    // recorded max_drawdown is at or below zero. A drawdown nearer zero is
    // therefore the better outcome, which makes this higher-better despite
    // describing a loss. `magnitude` is the same quantity reported positive,
    // and it is lower-better — the two must not be confused, because the
    // direction inverts with the sign convention and nothing on screen says
    // which convention a payload used.
    label: 'drawdown', class: 'loss',
    direction: 'higher-better', delta: 'absolute', scale: 'unit',
    zeroMeans: 'the series never fell below a prior peak in this window',
  },
  weight: {
    label: 'portfolio weight', class: 'weight',
    direction: 'neither', delta: 'absolute', scale: 'unit',
    zeroMeans: 'no position held',
  },
  multiple: {
    label: 'multiple', class: 'multiple',
    direction: 'neither', delta: 'multiplicative', scale: 'none',
  },
  currency: {
    label: 'currency amount', class: 'money',
    direction: 'neither', delta: 'absolute', scale: 'none',
  },
  bps: {
    label: 'basis points', class: 'basis-points',
    direction: 'lower-better', delta: 'basis-points', scale: 'none',
  },
  count: {
    label: 'count', class: 'cardinality',
    direction: 'neither', delta: 'absolute', scale: 'none',
    zeroMeans: 'none, counted — not "none found because nothing was looked at"',
  },
  sessions: {
    label: 'trading sessions', class: 'cardinality',
    direction: 'neither', delta: 'absolute', scale: 'none',
  },
  seconds: {
    label: 'seconds', class: 'duration',
    direction: 'neither', delta: 'absolute', scale: 'none',
  },
  eigenvalue: {
    label: 'eigenvalue', class: 'opaque',
    direction: 'neither', delta: 'none', scale: 'none',
    zeroMeans: 'a singular direction: the matrix is not of full rank',
  },
  score: {
    label: 'score', class: 'opaque',
    direction: 'neither', delta: 'none', scale: 'none',
    nullMeans: 'no score was produced; the scale is model-specific and has no default',
  },
  rank: {
    label: 'rank', class: 'ordinal',
    direction: 'neither', delta: 'none', scale: 'none',
  },
  zscore: {
    label: 'z-score', class: 'standardised',
    direction: 'neither', delta: 'absolute', scale: 'none',
    zeroMeans: 'exactly at the sample mean',
  },
  date: {
    label: 'date', class: 'temporal',
    direction: 'neither', delta: 'none', scale: 'none',
  },
  timestamp: {
    label: 'timestamp', class: 'temporal',
    direction: 'neither', delta: 'none', scale: 'none',
  },
}

export function semanticsOf(kind: Kind): Semantics {
  return SEMANTICS[kind] ?? SEMANTICS.ratio
}

/* ── comparability ───────────────────────────────────────────────────────── */

export interface Comparability {
  ok: boolean
  /** Why not, phrased for a reader rather than for a log. */
  reason?: string
  /**
   * Comparable, but something differs that the reader has to be told.
   *
   * The distinction from `reason` is the whole point. A price-to-earnings
   * against a margin is not a comparison and refusing it is correct. Apple's
   * fiscal 2025 revenue against Microsoft's fiscal 2024 revenue *is* a
   * comparison — of the same metric, on the same basis, in the same unit —
   * it is simply a comparison of two different years, and a reader who is
   * told that can use it. Refusing it would withhold something useful;
   * showing it silently would assert the years are the same.
   */
  caveat?: string
}

/**
 * Whether two quantities may be differenced.
 *
 * `basis` is what the numbers were measured against — a prediction target, a
 * horizon, an annualisation convention. Two metrics of the same kind measured
 * against different bases are still not comparable: a mean IC against
 * fwd_rank_21 and one against fwd_ret_21 are both `rank-agreement` by kind and
 * mean different things in fact.
 */
export function comparable(
  a: { kind: Kind; basis?: string; period?: string },
  b: { kind: Kind; basis?: string; period?: string },
): Comparability {
  const sa = semanticsOf(a.kind)
  const sb = semanticsOf(b.kind)

  if (sa.class !== sb.class) {
    return {
      ok: false,
      reason: `${sa.label} and ${sb.label} measure different things — ${sa.class.replace(/-/g, ' ')} against ${sb.class.replace(/-/g, ' ')}`,
    }
  }
  if (sa.scale !== sb.scale) {
    return {
      ok: false,
      reason: `one is expressed as a ${sa.scale === 'percent' ? 'percentage' : 'fraction'} and the other is not`,
    }
  }
  if (sa.delta === 'none') {
    return { ok: false, reason: `a difference between two ${sa.label}s carries no meaning` }
  }
  if (a.basis !== undefined && b.basis !== undefined && a.basis !== b.basis) {
    return {
      ok: false,
      /* Not "not the same scale", which was true of the case this was written
         for and false in general. Two vendor prices measured against a last
         sale and against the previous session's close are on identical
         scales — both are dollars — and are still not the same measurement.
         Saying "scale" there sent a reader looking for a unit error that was
         not present and away from the difference that was. */
      reason: `measured against ${a.basis} and ${b.basis}, which are not the same measurement`,
    }
  }

  /* One side declares what it was measured against and the other is silent.
     The period checks below have always had this branch and the basis check
     did not, so an unlabelled quantity compared against a labelled one was
     waved through in silence — which is the worse of the two cases, because
     an unstated basis cannot be ruled out as a different one. */
  if ((a.basis === undefined) !== (b.basis === undefined)) {
    const known = a.basis ?? b.basis
    return {
      ok: true,
      caveat: `one side is measured against ${known} and the other does not say what it is measured against`,
    }
  }

  /* Two observations of one metric over different windows. Still the same
     measurement on the same basis, so the comparison holds — but the reader
     is comparing two periods, and nothing else on the row would say so. */
  if (a.period !== undefined && b.period !== undefined && a.period !== b.period) {
    return {
      ok: true,
      caveat: `${a.period} against ${b.period} — different periods, not the same observation`,
    }
  }

  /* One side declares a period and the other does not. That is not a
     mismatch to report as a difference between two known windows; it is not
     knowing what the second one covers, which is worse. */
  if ((a.period === undefined) !== (b.period === undefined)) {
    const known = a.period ?? b.period
    return {
      ok: true,
      caveat: `one side covers ${known} and the other does not say which period it covers`,
    }
  }

  return { ok: true }
}

/* ── deltas ──────────────────────────────────────────────────────────────── */

export type Interpretation = 'better' | 'worse' | 'unchanged' | 'no-direction' | 'incomparable'

export interface Delta {
  /** The arithmetic, or null where none is meaningful. */
  value: number | null
  kind: DeltaKind
  /**
   * What the difference is measured in, which is not always what the operands
   * are measured in.
   *
   * The gap between two percentages is percentage points, not percent: a
   * margin going from 48.6% to 67.9% is +19.3pp, and calling that +19.3%
   * describes a completely different quantity — a 19.3% relative increase
   * would be 58.0%. And a multiplicative delta is a ratio, so it carries ×;
   * without it, "0.74" between a P/E of 37 and one of 28 reads as an absolute
   * difference of three quarters of a turn.
   */
  unit: string | null
  /** Rendered difference, already formatted. */
  formatted: Formatted | null
  /**
   * What the difference means. Deliberately separate from `value`: a number
   * and a judgement about it are different claims, and a UI that cannot hold
   * them apart ends up colouring arithmetic it has not understood.
   */
  interpretation: Interpretation
  /** Present only when the two could not be compared. */
  reason?: string
  /**
   * Present when the two *were* compared but something about them differs
   * that the reader must be told — most often that the observations cover
   * different periods. A difference carrying a caveat is still a difference;
   * it is just not a difference between like and like.
   */
  caveat?: string
}

/**
 * Difference between a value and its baseline, with its interpretation.
 *
 * Refuses rather than guesses. `B − A` is not "improvement": for PBO and
 * drawdown and turnover and cost, a smaller number is the better one, and for
 * a t-statistic or a weight neither direction is better at all.
 */
export function delta(
  value: number | null | undefined,
  baseline: number | null | undefined,
  // Periods travel with the operands, not with the caller's intent: a
  // difference between two windows is a different claim from a difference
  // within one, and only the operands know which this is.
  a: { kind: Kind; basis?: string; period?: string },
  b: { kind: Kind; basis?: string; period?: string } = a,
): Delta {
  const fit = comparable(a, b)
  if (!fit.ok) {
    return { value: null, kind: 'none', unit: null, formatted: null, interpretation: 'incomparable', reason: fit.reason }
  }
  if (!isFinite2(value) || !isFinite2(baseline)) {
    return {
      value: null, kind: semanticsOf(a.kind).delta, unit: null, formatted: null,
      interpretation: 'incomparable',
      reason: 'one side was not recorded, and a difference against a missing value is not zero',
    }
  }

  const s = semanticsOf(a.kind)
  const raw = s.delta === 'multiplicative'
    ? (baseline === 0 ? null : value / baseline)
    : value - baseline

  if (raw === null) {
    return {
      value: null, kind: s.delta, unit: null, formatted: null, interpretation: 'incomparable',
      reason: 'the baseline is zero, so a multiple against it is undefined',
    }
  }

  const moved = s.delta === 'multiplicative' ? raw - 1 : raw
  const interpretation: Interpretation =
    Math.abs(moved) < Number.EPSILON ? 'unchanged'
      : s.direction === 'neither' ? 'no-direction'
        : (s.direction === 'higher-better') === (moved > 0) ? 'better' : 'worse'

  const formatKind = s.delta === 'multiplicative' ? 'multiple' : a.kind
  const signed = s.delta !== 'multiplicative'
  let formatted = format(raw, formatKind, { signed })

  /* A difference that is real but smaller than its own display precision
     rendered as a signed zero. Costco's trailing net margin is 3.01% against
     Walmart's 3.00%; both show as 3.0%, and the difference showed as
     "-0.0pp" — a figure the reader cannot reconcile with either operand and
     which reads as a rounding artefact even though the sign is correct.

     Given more decimals it becomes -0.01pp, which is small and true. Only
     when even that cannot show the movement is the reader told the
     difference sits below the precision on screen. */
  if (moved !== 0 && readsAsNoChange(formatted.text, formatKind, signed)) {
    const finer = format(raw, formatKind, { signed, digits: 4 })
    // If four decimals still cannot show it, the movement is smaller than
    // anything this page could act on; the rounded figure stands.
    if (!readsAsNoChange(finer.text, formatKind, signed, 4)) {
      formatted = { ...finer, text: trimZeros(finer.text) }
    }
  }

  return {
    value: raw,
    kind: s.delta,
    unit: deltaUnit(a.kind, s.delta),
    formatted,
    interpretation,
    // Survives the arithmetic. A period mismatch does not stop the
    // subtraction; it changes what the answer means.
    caveat: fit.caveat,
  }
}

/**
 * Whether a rendered difference shows no movement at all.
 *
 * The figure that means "no change" depends on how the difference was
 * measured: nothing moved is 0 for a subtraction and 1 for a ratio. Rather
 * than pattern-match either, this formats the neutral value on the same terms
 * and compares — so the two stay in step if the formatter changes.
 */
function readsAsNoChange(
  text: string, kind: Kind, signed: boolean, digits?: number,
): boolean {
  const neutral = kind === 'multiple' ? 1 : 0
  // Magnitude only: "-0.0" and "0.0" both show nothing moving, and it is the
  // first of those that misleads.
  const bare = (t: string) => t.trim().replace(/^[+\-−]/, '')
  return bare(text) === bare(format(neutral, kind, { signed, digits }).text)
}

/** 0.0100 is 0.01. Trailing zeros claim precision the figure does not carry. */
function trimZeros(text: string): string {
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text
}

/**
 * A delta's signed movement, whichever way it was measured.
 *
 * An additive delta is already signed: 0 means no change. A multiplicative
 * one is a ratio, where no change is 1 — so testing `d.value > 0` on it is
 * true for every ratio a vendor can produce, and a caller doing that gets a
 * verdict that never depends on the data. That is exactly what the security
 * comparison was doing: every valuation multiple was coloured by the field's
 * declared direction alone, so a cheaper price-to-earnings and a dearer one
 * both rendered the same.
 *
 * `delta()` already applies this rule internally to reach its own
 * interpretation. This exports it, so a caller that overrides the
 * interpretation with a field-level direction overrides it on the same terms.
 */
export function deltaMoved(d: Delta): number | null {
  if (d.value === null || !isFinite2(d.value)) return null
  return d.kind === 'multiplicative' ? d.value - 1 : d.value
}

function isFinite2(v: number | null | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/**
 * The unit a difference is expressed in.
 *
 * Deliberately not the operands' unit. Subtracting one percentage from
 * another gives percentage points; dividing one multiple by another gives a
 * ratio. Both are routinely mislabelled with the operands' unit, and both read
 * as an entirely different quantity when they are.
 */
function deltaUnit(kind: Kind, deltaKind: DeltaKind): string | null {
  if (deltaKind === 'multiplicative') return '×'
  if (deltaKind === 'basis-points') return 'bp'
  const scale = semanticsOf(kind).scale
  if (scale === 'percent') return 'pp'
  return null
}

/* ── tone ────────────────────────────────────────────────────────────────── */

export type Tone = 'positive' | 'negative' | 'neutral'

/**
 * Colour for a value, from direction alone — never from sign.
 *
 * A quantity whose direction is `neither` is never coloured, however positive
 * it looks. A t-statistic of +3.67 is not good news; it is a large statistic,
 * and whether it means anything depends on how many were tried.
 *
 * Evidence is deliberately not an input here. A number can be favourable and
 * untrustworthy at once, and a single colour cannot say both — so evidence is
 * carried alongside as its own signal rather than folded into this one.
 */
export function toneFor(value: number | null | undefined, kind: Kind): Tone {
  const s = semanticsOf(kind)
  if (s.direction === 'neither') return 'neutral'
  if (!isFinite2(value) || value === 0) return 'neutral'
  const good = s.direction === 'higher-better' ? value > 0 : value < 0
  return good ? 'positive' : 'negative'
}
