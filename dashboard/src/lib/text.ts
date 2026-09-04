/**
 * Text the product renders at display size.
 *
 * The symbol database returns legal names in capitals — "APPLE INC",
 * "JPMORGAN CHASE & CO", "AT&T INC". Set at 34px that reads as a banner
 * shouting at the reader rather than as the name of a company, so the one
 * place the product uses display type is also the one place it has to care
 * how a name is cased.
 *
 * Nothing here changes what a name *is*. Casing is presentation; the original
 * string stays available for search, for copy, and for the title attribute.
 */

/** Words that stay lowercase inside a name, never at its start. */
const MINOR = new Set([
  'a', 'an', 'and', 'as', 'at', 'but', 'by', 'de', 'del', 'der', 'for', 'in',
  'la', 'las', 'los', 'nv', 'of', 'on', 'or', 'the', 'to', 'van', 'von',
])

/** Forms that are acronyms or stylings, not words, and stay exactly as given. */
const KEEP = new Set([
  'AB', 'AG', 'AI', 'AS', 'ASA', 'BV', 'CO', 'CORP', 'ETF', 'GMBH', 'II',
  'III', 'IV', 'KGAA', 'LP', 'LLC', 'NV', 'PLC', 'REIT', 'SA', 'SE', 'SPA',
  'USA', 'UK', 'US', 'VI', 'VII', 'AT&T', 'JPMORGAN', '3M',
])

/** Suffixes that read better abbreviated with a stop. */
const SUFFIX: Record<string, string> = {
  INC: 'Inc.', CORP: 'Corp.', LTD: 'Ltd.', CO: 'Co.',
}

function word(raw: string, index: number): string {
  const bare = raw.replace(/[.,]$/, '')
  const trail = raw.slice(bare.length)

  if (KEEP.has(bare)) return bare + trail
  if (SUFFIX[bare]) return SUFFIX[bare]

  // A token carrying digits or an ampersand is a styling — 3M, AT&T, S&P.
  if (/[0-9&]/.test(bare)) return bare + trail

  const lower = bare.toLowerCase()
  if (index > 0 && MINOR.has(lower)) return lower + trail

  // Hyphenated and slashed names capitalise on both sides of the separator.
  const cased = lower.replace(/(^|[-/'])([a-z])/g, (_m, sep: string, ch: string) => sep + ch.toUpperCase())
  return cased + trail
}

/**
 * A legal name, cased for display.
 *
 * Only applied to names that arrive shouting. A name already in mixed case is
 * returned untouched, because the provider that bothered to case it knows
 * better than this function does.
 */
export function titleCase(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return trimmed
  if (!/[A-Z]/.test(trimmed)) return trimmed
  // Any lowercase letter means the source already cased it deliberately.
  if (/[a-z]/.test(trimmed)) return trimmed

  return trimmed.split(/\s+/).map(word).join(' ')
}

/**
 * A listing venue, short enough to sit beside the ticker.
 *
 * Vendors return the full market description — "NASDAQ NMS - GLOBAL MARKET",
 * "NEW YORK STOCK EXCHANGE, INC." — which is accurate and far too long for a
 * line whose job is to say, at a glance, where this thing trades. This takes
 * the market's name and drops the tier and the legal form.
 *
 * It condenses; it never translates. An unrecognised venue is returned as
 * given rather than guessed at, and callers keep the full string on the
 * element's title so nothing is actually lost.
 */
export function venueLabel(exchange: string | null | undefined): string | null {
  if (!exchange) return null
  const raw = exchange.trim()
  if (!raw) return null

  // Everything after a dash is the tier or segment, not the venue.
  const head = raw.split(/\s[-–—]\s/)[0]
    .replace(/,?\s*(inc|incorporated|llc|plc|ltd)\.?$/i, '')
    .trim()

  // Market tiers that describe a segment of a venue already named.
  const bare = head
    .replace(/\s+(nms|ngs|ngm|cm|global (select )?market|capital market|composite)$/i, '')
    .trim()

  return bare || raw
}
