/**
 * Visual identity — one place that decides what a thing *looks* like.
 *
 * Three kinds of identity appear across the terminal, and until now each
 * surface improvised its own: a ticker got a logo URL inlined at the call
 * site, a source got its raw vendor string printed, and a sector got
 * nothing. That drift is why the same company could read three different
 * ways on three pages.
 *
 * Everything here is derivation, never invention. A logo URL is built from a
 * ticker the payload already carries; a source domain comes from the article
 * URL the payload already carries. Nothing is fabricated, and every lookup
 * has a defined "no identity" answer rather than a guess.
 */

/* ── Company logos ────────────────────────────────────────────────────────
   Two independent providers, tried in order, because neither covers the
   whole universe: FMP catalogues US equities and most ETFs, Parquet covers
   several names FMP has never had. Measured against this product's own
   universe, both answer 200 for AAPL/NVDA/META/BRK-B/XLK/SPY and both 404
   for a symbol that does not exist — so a fallthrough is a real second
   chance rather than a second copy of the same answer.

   No third-party key is involved, which is why these two and not the
   better-known logo APIs: Clearbit's endpoint no longer resolves at all,
   and logo.dev answers 401 without a publishable token. */
/** Logo.dev publishable key, when the deployment supplies one.
 *
 *  The *publishable* key only — Logo.dev documents it as safe for
 *  browser-side image URLs, which is exactly this use. The secret key
 *  authenticates server-side lookup APIs, is read only by the backend, and
 *  must never reach a `NEXT_PUBLIC_*` variable or a client bundle.
 *
 *  Read through a guarded property access rather than destructured at module
 *  scope so a build without the variable produces an empty string instead of
 *  a crash, and so the chain below simply skips the provider. */
const LOGO_DEV_KEY =
  typeof process !== 'undefined' ? (process.env.NEXT_PUBLIC_LOGO_DEV_KEY ?? '') : ''

export const LOGO_PROVIDERS: ReadonlyArray<(symbol: string) => string> = [
  // Logo.dev first when configured: it is a dedicated brand-mark service
  // indexed by ticker, where the two below are side-effects of a market-data
  // product and a broker product respectively. `fallback=404` makes a miss a
  // clean error the <img> onError handler advances past, rather than a grey
  // placeholder that would look like a real logo and stop the chain.
  ...(LOGO_DEV_KEY
    ? [(s: string) =>
        `https://img.logo.dev/ticker/${encodeURIComponent(s)}` +
        `?token=${encodeURIComponent(LOGO_DEV_KEY)}&size=128&format=png&fallback=404`]
    : []),
  (s) => `https://financialmodelingprep.com/image-stock/${encodeURIComponent(s)}.png`,
  (s) => `https://assets.parqet.com/logos/symbol/${encodeURIComponent(s)}`,
]

/** Every URL worth trying for a ticker, best first. */
export function logoSources(ticker: string): string[] {
  const symbol = ticker.trim().toUpperCase()
  if (!symbol) return []
  return LOGO_PROVIDERS.map((build) => build(symbol))
}

/* ── Source identity ──────────────────────────────────────────────────────
   A favicon is fetched from the source's own domain rather than from a
   bundled set of publisher logos — bundling would be a licensing question
   and a maintenance burden, and it could only ever cover the publishers we
   thought of. The domain is extracted from the article URL, so it is the
   source's actual identity and not a name we mapped by hand.

   The map below exists only for sources that arrive *without* a URL —
   internal vendor identifiers like `fred` on a macro card. Those are our own
   strings, so resolving them is a lookup, not a guess. */
const VENDOR_DOMAINS: Record<string, string> = {
  fred: 'fred.stlouisfed.org',
  'st. louis fed': 'fred.stlouisfed.org',
  sec: 'sec.gov',
  'sec edgar': 'sec.gov',
  edgar: 'sec.gov',
  fmp: 'financialmodelingprep.com',
  'financial modeling prep': 'financialmodelingprep.com',
  yfinance: 'finance.yahoo.com',
  'yahoo finance': 'finance.yahoo.com',
  yahoo: 'finance.yahoo.com',
  polygon: 'polygon.io',
  tavily: 'tavily.com',
  reuters: 'reuters.com',
  bloomberg: 'bloomberg.com',
  barchart: 'barchart.com',
  'seeking alpha': 'seekingalpha.com',
  'markets insider': 'markets.businessinsider.com',
  cnbc: 'cnbc.com',
  marketwatch: 'marketwatch.com',
}

/**
 * The domain that identifies a source, or '' when nothing identifies it.
 *
 * The URL wins whenever there is one: it is the source's own address, where
 * the vendor string is whatever the feed chose to call itself that day
 * ("🔴 BREAKING | Barchart" is a real observed value). Returning '' rather
 * than a plausible-looking domain matters — a wrong favicon attributes a
 * claim to a publisher that never made it.
 */
export function sourceDomain(name?: string | null, url?: string | null): string {
  if (url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '')
    } catch {
      /* fall through to the vendor map */
    }
  }
  if (!name) return ''
  const key = name.trim().toLowerCase()
  if (VENDOR_DOMAINS[key]) return VENDOR_DOMAINS[key]
  // Feed names arrive decorated ("🔴 BREAKING | Barchart", "Reuters US").
  // Match on a contained vendor key rather than failing the whole lookup.
  const hit = Object.keys(VENDOR_DOMAINS).find((vendor) => key.includes(vendor))
  return hit ? VENDOR_DOMAINS[hit] : ''
}

/** Favicon for a domain, at a size that stays sharp on a 16-20px plate. */
export function faviconFor(domain: string, size = 64): string {
  return `https://www.google.com/s2/favicons?sz=${size}&domain=${encodeURIComponent(domain)}`
}

/**
 * A source's display name, cleaned of feed decoration.
 *
 * Only strips leading emoji/ALL-CAPS banner segments that RSS aggregators
 * prepend ("🔴 BREAKING | Barchart" → "Barchart"). If stripping would leave
 * nothing, the original is kept — a slightly noisy name beats an empty one.
 */
export function sourceLabel(name?: string | null, url?: string | null): string {
  const raw = (name ?? '').trim()
  if (raw) {
    const tail = raw.split('|').pop()?.trim()
    if (tail) return tail
    return raw
  }
  return sourceDomain(null, url) || 'Unattributed'
}

/* ── Sector identity ──────────────────────────────────────────────────────
   Each GICS sector has a sector-SPDR ETF that *is* a real listed ticker with
   a real logo, and the product already trades on those symbols in the
   breadth map. Mapping a sector name to its proxy therefore borrows an
   identity that genuinely stands for the sector rather than inventing an
   icon for it. A sector with no proxy gets no mark. */
const SECTOR_PROXY: Record<string, string> = {
  technology: 'XLK',
  'information technology': 'XLK',
  financials: 'XLF',
  'financial services': 'XLF',
  healthcare: 'XLV',
  'health care': 'XLV',
  energy: 'XLE',
  industrials: 'XLI',
  'consumer discretionary': 'XLY',
  'consumer cyclical': 'XLY',
  'consumer staples': 'XLP',
  'consumer defensive': 'XLP',
  utilities: 'XLU',
  materials: 'XLB',
  'basic materials': 'XLB',
  'real estate': 'XLRE',
  'communication services': 'XLC',
  communications: 'XLC',
}

/** The ETF whose logo stands for a sector, or '' when none does. */
export function sectorProxy(sector?: string | null): string {
  if (!sector) return ''
  return SECTOR_PROXY[sector.trim().toLowerCase()] ?? ''
}
