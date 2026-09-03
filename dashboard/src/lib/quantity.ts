/**
 * The canonical numerical presentation system.
 *
 * A quantitative terminal's primary visual material is numbers, and until now
 * their formatting lived in 173 separate `toFixed` calls with five different
 * precisions for the same class of measure. An information coefficient rendered
 * to three decimals on one screen and five on another is not a style
 * inconsistency — it implies a precision the estimate does not have, and it
 * makes two screens showing the same figure look like they disagree.
 *
 * So a number declares what kind of quantity it is, and this decides how it
 * looks. The precision for each kind is chosen from what the measurement can
 * actually support:
 *
 *   an information coefficient is a correlation estimated from a few hundred
 *   dated observations. Four decimals is already generous; six is noise
 *   dressed as rigour.
 *
 *   a Sharpe ratio from four hundred periods has a standard error near 0.05.
 *   Three decimals states a difference the sample cannot resolve, so it gets
 *   two.
 *
 *   a probability is bounded and a reader compares it against a threshold, so
 *   it keeps enough digits to sit either side of one.
 *
 * Nothing here converts. A return of 0.0231 is shown as 0.0231 with its unit,
 * not as 2.31%, because the engine's own unit is the decimal and re-scaling in
 * the display layer is how a figure comes to mean two things in one product.
 * The unit label carries the interpretation instead.
 */

export type Kind =
  | 'ic'            // rank correlation in [-1, 1]
  | 'correlation'   // Pearson or Spearman in [-1, 1]
  | 'ratio'         // dimensionless: Sharpe, Sortino, Calmar, Omega
  | 'sharpe'        // a ratio whose sampling error deserves fewer digits
  | 'tstat'         // a test statistic
  | 'probability'   // bounded [0, 1], compared against a threshold
  | 'share'         // a fraction of a whole
  | 'return'        // a return in the series' own units
  | 'magnitude'     // a loss reported positive
  | 'volatility'    // annualised dispersion
  | 'drawdown'      // a decline, signed negative
  | 'weight'        // a portfolio weight
  | 'multiple'      // a turnover or leverage multiple
  | 'currency'      // a price or notional
  | 'bps'           // basis points, as basis points
  | 'count'         // an integer
  | 'sessions'      // a count of trading sessions
  | 'seconds'
  | 'eigenvalue'    // very small or very large; exponential
  | 'score'         // an arbitrary model score
  | 'rank'
  | 'zscore'
  | 'date'
  | 'timestamp'

interface Spec {
  digits: number
  /** Prefix a + on non-negative values, where direction is the point. */
  signed: boolean
  /** Rendered small after the figure. */
  unit?: string
  /** Colour by sign. Off unless the sign genuinely means better or worse. */
  tone: boolean
  /** Exponential below this magnitude, where fixed decimals would show zero. */
  exponentialBelow?: number
}

export const SPECS: Record<Kind, Spec> = {
  // A correlation from a few hundred dated observations. Four decimals is
  // already generous; six would be noise dressed as rigour.
  ic:          { digits: 4, signed: true,  unit: 'rank corr.', tone: true },
  correlation: { digits: 3, signed: true,  tone: false },

  ratio:       { digits: 3, signed: true,  tone: true },
  // Four hundred periods gives a Sharpe a standard error near 0.05. Three
  // decimals states a difference the sample cannot resolve.
  sharpe:      { digits: 2, signed: true,  tone: true },
  tstat:       { digits: 2, signed: true,  tone: false },

  // Bounded, and read against a threshold, so it keeps enough digits to sit
  // clearly on one side of one.
  probability: { digits: 4, signed: false, tone: false },
  share:       { digits: 3, signed: false, tone: false },

  return:      { digits: 4, signed: true,  unit: 'ret', tone: true },
  magnitude:   { digits: 4, signed: false, tone: false },
  volatility:  { digits: 4, signed: false, unit: 'ann.', tone: false },
  drawdown:    { digits: 4, signed: false, tone: true },

  weight:      { digits: 4, signed: true,  tone: true },
  multiple:    { digits: 2, signed: false, unit: '×', tone: false },
  currency:    { digits: 2, signed: false, tone: false },
  bps:         { digits: 1, signed: false, unit: 'bp', tone: false },

  count:       { digits: 0, signed: false, tone: false },
  sessions:    { digits: 0, signed: false, unit: 'sess', tone: false },
  seconds:     { digits: 1, signed: false, unit: 's', tone: false },

  // Spans many orders of magnitude and is often near zero, where fixed
  // decimals would print 0.0000 for a value whose sign is the whole point.
  eigenvalue:  { digits: 3, signed: true,  tone: false, exponentialBelow: 1e-3 },

  score:       { digits: 4, signed: true,  tone: false },
  rank:        { digits: 0, signed: false, tone: false },
  zscore:      { digits: 2, signed: true,  tone: false },

  date:        { digits: 0, signed: false, tone: false },
  timestamp:   { digits: 0, signed: false, tone: false },
}

export interface Formatted {
  /** The figure, ready to render. Empty when the value is absent. */
  text: string
  unit?: string
  /** Whether the caller should colour by sign for this kind. */
  tone: boolean
  /** True when there is no value — the caller renders an em dash, not a zero. */
  absent: boolean
}

const ABSENT: Formatted = { text: '—', tone: false, absent: true }

export function isPresent(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/**
 * Format a quantity by kind.
 *
 * `digits` overrides the kind's precision only where a caller genuinely knows
 * better — a headline figure shown larger, for instance. It is not a way to
 * opt out of the system.
 */
export function format(
  value: number | string | null | undefined,
  kind: Kind = 'ratio',
  overrides?: { digits?: number; signed?: boolean; unit?: string; tone?: boolean },
): Formatted {
  const spec = SPECS[kind] ?? SPECS.ratio
  const digits = overrides?.digits ?? spec.digits
  const signed = overrides?.signed ?? spec.signed
  const unit = overrides?.unit ?? spec.unit
  const tone = overrides?.tone ?? spec.tone

  if (value === null || value === undefined) return ABSENT

  if (typeof value === 'string') {
    return { text: value, unit, tone: false, absent: value.length === 0 }
  }
  if (!Number.isFinite(value)) return ABSENT

  // Dates arrive as numbers only by accident; a caller passing one has a bug
  // worth seeing rather than a timestamp worth rendering.
  if (kind === 'date' || kind === 'timestamp') {
    return { text: String(value), unit, tone: false, absent: false }
  }

  if (kind === 'count' || kind === 'rank' || kind === 'sessions') {
    return { text: Math.round(value).toLocaleString('en-US'), unit, tone, absent: false }
  }

  if (kind === 'currency') {
    return {
      text: value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }),
      unit, tone, absent: false,
    }
  }

  const magnitude = Math.abs(value)
  if (spec.exponentialBelow !== undefined && magnitude > 0 && magnitude < spec.exponentialBelow) {
    const text = value.toExponential(Math.max(1, digits - 1))
    return { text: signed && value >= 0 ? `+${text}` : text, unit, tone, absent: false }
  }

  const fixed = value.toFixed(digits)
  return { text: signed && value >= 0 ? `+${fixed}` : fixed, unit, tone, absent: false }
}

/** A date, rendered the one way this product renders dates. */
export function formatDate(v: string | null | undefined): string {
  if (!v) return '—'
  return v.slice(0, 10)
}

/** A timestamp, to the second. Never to the millisecond: nothing here is that fast. */
export function formatTimestamp(v: string | null | undefined): string {
  if (!v) return '—'
  return v.slice(0, 19).replace('T', ' ')
}

/**
 * A duration in whole days between two dates, or null where either is missing.
 * Used for filing lags and coverage windows, which were each computing this
 * inline with slightly different rounding.
 */
export function daysBetween(from: string | null | undefined, to: string | null | undefined): number | null {
  if (!from || !to) return null
  const a = Date.parse(from)
  const b = Date.parse(to)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null
  return Math.round((b - a) / 86_400_000)
}
