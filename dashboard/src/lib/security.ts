/**
 * A security, independent of any research dataset.
 *
 * The terminal lost its most basic workflow — type a ticker, look at a company
 * — because every security surface had been wired through the research panel.
 * When that dataset went stale the whole path went with it, and the product
 * became a research archive with no way in.
 *
 * AAPL is AAPL whether or not an experiment ever scored it. This module is the
 * identity that holds regardless: it reads the live provider layer and knows
 * nothing about experiments, folds or gates.
 *
 * Three sources, in order of how fast they answer and how much they carry:
 *
 *   /api/screen?q=      symbol and name lookup, ~50ms, provider symbol database
 *   /api/quotes         last price and change, ~250ms
 *   /api/chart/{t}      daily closes and volume, ~330ms
 *
 * A fourth, /api/research/{ticker}, carries profile, fundamentals, filings,
 * ownership and news — and takes around twenty-four seconds. It is deliberately
 * not on the path to first paint. A security page that waits for it is a
 * security page nobody opens twice.
 */

export interface SecurityIdentity {
  /** The canonical ticker, uppercased. */
  symbol: string
  /** Company name as the symbol database reports it. */
  name: string | null
  /** Which provider answered, so the reader can see where identity came from. */
  via: string | null
}

export interface Quote {
  price: number | null
  change_1d: number | null
  change_1w: number | null
  source: string | null
  /** The provider's own staleness flag. Never inferred from the timestamp. */
  stale: boolean
}

export interface Bar {
  date: string
  close: number | null
  volume: number | null
}

/** A ticker as the symbol databases spell them. */
const SYMBOL = /^[A-Z][A-Z0-9.\-]{0,9}$/

/**
 * Whether a query looks like someone reaching for a ticker rather than
 * describing a research object.
 *
 * Used only for ordering — a ticker-shaped query puts securities first. It
 * never suppresses the other results, because "MOM" is both a plausible ticker
 * and the start of "momentum", and guessing wrong should cost an ordering
 * rather than an answer.
 */
export function looksLikeSymbol(query: string): boolean {
  return SYMBOL.test(query.trim().toUpperCase())
}

interface ScreenResult {
  symbol?: string
  name?: string
  via?: string
}

/**
 * Look up securities by ticker or company name.
 *
 * `signal` is required rather than optional: a search box fires a request per
 * keystroke, and without cancellation the answer to "AAP" can arrive after the
 * answer to "AAPL" and overwrite it. That is the one bug this function exists
 * to make hard.
 */
export async function searchSecurities(
  query: string,
  signal: AbortSignal,
): Promise<SecurityIdentity[]> {
  const q = query.trim()
  if (!q) return []

  const r = await fetch(`/api/screen?q=${encodeURIComponent(q)}`, { signal })
  if (!r.ok) throw new Error(`the symbol search returned ${r.status}`)
  const d: { results?: ScreenResult[] } = await r.json()

  return (d.results ?? [])
    .filter((x): x is ScreenResult & { symbol: string } => Boolean(x.symbol))
    .map((x) => ({
      symbol: x.symbol.toUpperCase(),
      name: x.name ?? null,
      via: x.via ?? null,
    }))
}

/** Last price for one or more symbols. */
export async function fetchQuotes(
  symbols: string[],
  signal?: AbortSignal,
): Promise<Record<string, Quote>> {
  if (!symbols.length) return {}
  const r = await fetch(`/api/quotes?symbols=${encodeURIComponent(symbols.join(','))}`, { signal })
  if (!r.ok) throw new Error(`the quote request returned ${r.status}`)
  const d: { quotes?: Record<string, Quote> } = await r.json()
  return d.quotes ?? {}
}

/** Daily closes for one symbol. */
export async function fetchBars(
  symbol: string,
  period: string,
  signal?: AbortSignal,
): Promise<Bar[]> {
  const r = await fetch(
    `/api/chart/${encodeURIComponent(symbol)}?period=${encodeURIComponent(period)}`,
    { signal },
  )
  if (!r.ok) throw new Error(`the price request returned ${r.status}`)
  const d: { prices?: Bar[] } = await r.json()
  return d.prices ?? []
}

/**
 * Rank symbol matches for a query.
 *
 * An exact ticker beats a name match, and a name that starts with the query
 * beats one that merely contains it. Typing "AAP" must reach AAPL before it
 * reaches Apple Hospitality REIT — the provider returns both, in its own order,
 * and its order is not ours.
 */
export function rankSecurities(query: string, rows: SecurityIdentity[]): SecurityIdentity[] {
  const q = query.trim().toUpperCase()
  if (!q) return rows

  const score = (s: SecurityIdentity): number => {
    const sym = s.symbol.toUpperCase()
    const name = (s.name ?? '').toUpperCase()
    if (sym === q) return 0
    if (sym.startsWith(q)) return 1
    if (name.startsWith(q)) return 2
    if (sym.includes(q)) return 3
    if (name.includes(q)) return 4
    return 5
  }

  // Stable within a rank: the provider's own ordering is preserved for ties,
  // which usually reflects listing prominence.
  return rows
    .map((s, i) => ({ s, r: score(s), i }))
    .sort((a, b) => a.r - b.r || a.i - b.i)
    .map((x) => x.s)
}
