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
  'AB', 'AG', 'AI', 'AS', 'ASA', 'BV', 'ETF', 'GMBH', 'II', 'III', 'IV',
  'KGAA', 'LP', 'LLC', 'NV', 'PLC', 'REIT', 'SA', 'SE', 'SPA', 'USA', 'UK',
  'US', 'VI', 'VII', 'AT&T', '3M',
])

/** Names whose own styling is internal capitalisation, not an acronym. */
const STYLED: Record<string, string> = {
  JPMORGAN: 'JPMorgan', MCDONALD: 'McDonald', MCDONALDS: 'McDonalds',
  ISHARES: 'iShares', ETRADE: 'E*TRADE', EBAY: 'eBay', PAYPAL: 'PayPal',
}

/** Suffixes that read better abbreviated with a stop. */
const SUFFIX: Record<string, string> = {
  INC: 'Inc.', CORP: 'Corp.', LTD: 'Ltd.', CO: 'Co.',
}

function word(raw: string, index: number, total: number): string {
  const bare = raw.replace(/[.,]$/, '')
  const trail = raw.slice(bare.length)

  /* A corporate suffix is only a suffix at the end. "CO" closing a name is
     "Co."; the same token opening one belongs to the name itself, as in
     "CO OPERATIVE GROUP". Checked before KEEP, because CORP and CO would
     otherwise be preserved verbatim and never abbreviate. */
  if (index === total - 1 && SUFFIX[bare]) return SUFFIX[bare]
  if (STYLED[bare]) return STYLED[bare] + trail
  if (KEEP.has(bare)) return bare + trail

  // A token carrying digits or an ampersand is a styling — 3M, AT&T, S&P.
  if (/[0-9&]/.test(bare)) return bare + trail

  /* A lone letter is a share class, not a word. "APPLOVIN CORP-CLASS A" came
     back as "Applovin Corp-Class a", because the minor-word list contains the
     article "a" — and a lowercase class letter reads as a typo in a list
     whose whole purpose is telling two listings of one company apart. */
  if (bare.length === 1) return bare.toUpperCase() + trail

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

  const parts = trimmed.split(/\s+/)
  return parts.map((w, i) => word(w, i, parts.length)).join(' ')
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

  /* An exact, closed list. These four are the venues whose abbreviation is
     universal in this context and cannot be mistaken for another exchange.
     Anything not on it is returned as the vendor wrote it — a guessed
     abbreviation is a claim about where a security lists, and that is exactly
     the kind of invention this product does not make. Callers keep the full
     string on hover either way. */
  const known: Record<string, string> = {
    'NEW YORK STOCK EXCHANGE': 'NYSE',
    'NASDAQ': 'NASDAQ',
    'LONDON STOCK EXCHANGE': 'LSE',
    'TORONTO STOCK EXCHANGE': 'TSX',
    /* ISO 10383 market identifiers. The merged profile does not always
       return the same field for the same company — Apple came back as
       "NASDAQ NMS - GLOBAL MARKET" from one provider and "XNAS" from
       another — and a four-letter code beside a ticker tells a reader
       nothing. These are exact identifiers rather than guesses, which is
       the same standard the descriptions above are held to. */
    XNAS: 'NASDAQ', XNGS: 'NASDAQ', XNMS: 'NASDAQ', XNCM: 'NASDAQ',
    /* Yahoo's own tier codes, which arrive bare. The merged profile is not
       deterministic — the same security came back as "NASDAQ NMS - GLOBAL
       MARKET" on one read and "NMS" on the next, depending on which vendor
       won the merge — so the header flipped between NASDAQ and NMS between
       page loads. NMS, NCM and NGM are NASDAQ tiers and nothing else. */
    NMS: 'NASDAQ', NCM: 'NASDAQ', NGM: 'NASDAQ', NYQ: 'NYSE', PCX: 'NYSE Arca',
    XNYS: 'NYSE', ARCX: 'NYSE Arca', BATS: 'Cboe BZX',
    XLON: 'LSE', XTSE: 'TSX', XETR: 'Xetra', XTKS: 'Tokyo',
  }
  return known[bare.toUpperCase()] ?? (bare || raw)
}
