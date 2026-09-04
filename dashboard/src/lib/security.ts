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

import { readResource } from './resource'
import { titleCase } from './text'

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

  const mapped = (d.results ?? [])
    .filter((x): x is ScreenResult & { symbol: string } => Boolean(x.symbol))
    .map((x) => ({
      symbol: x.symbol.toUpperCase(),
      name: x.name ? titleCase(x.name) : null,
      via: x.via ?? null,
    }))

  /* One row per security. The screen endpoint merges several symbol
     databases and does not reconcile them, so searching "app" returned APP
     twice — once as "APPLOVIN CORP-CLASS A" and once as "Applovin Corp".
     Two rows for one company in a list whose whole job is to let someone
     pick a company is a defect, and picking either row goes to the same
     page anyway.

     The keeper is the row that carries a name, and between two named rows
     the more specific one — a share-class suffix is information, and
     dropping it would make two genuinely different listings look identical.
     Ties keep the provider's own ordering, which tracks prominence. */
  const best = new Map<string, SecurityIdentity>()
  for (const row of mapped) {
    const held = best.get(row.symbol)
    if (!held) { best.set(row.symbol, row); continue }
    if (!held.name && row.name) { best.set(row.symbol, row); continue }
    if (held.name && row.name && row.name.length > held.name.length) best.set(row.symbol, row)
  }
  return [...best.values()]
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

/**
 * Ownership figures a reader should not compare, and why.
 *
 * Vendors assemble an ownership block from more than one filing, and the
 * pieces are not always measured over the same base. The case that shows up
 * on real names is a multi-class issuer: the shares outstanding are reported
 * for the listed class while the float spans every class, so the float comes
 * back larger than the count it is nominally a subset of.
 *
 * Nothing is corrected here. Choosing which of two vendor figures to override
 * would be inventing a number, and the reader is better served by knowing the
 * pair disagrees than by a silently repaired one that looks authoritative.
 *
 * Returns null when the block is internally consistent, which is the ordinary
 * case — of the large caps checked while writing this, only Alphabet trips it.
 */
export function ownershipConflict(o: {
  shares_outstanding?: number | null
  float_shares?: number | null
}): string | null {
  const shares = o.shares_outstanding
  const float = o.float_shares
  if (typeof shares !== 'number' || typeof float !== 'number') return null
  if (!Number.isFinite(shares) || !Number.isFinite(float)) return null
  if (float <= shares) return null
  return 'The float above is larger than the shares outstanding, which cannot be true of a single share class. This usually means the two figures are measured on different bases — the count for the listed class against a float spanning every class. Treat them as two vendor figures, not as a pair to divide.'
}

/** Calendar days each named range asks for. Mirrors the provider's own table. */
const RANGE_DAYS: Record<string, number> = {
  '1mo': 31, '3mo': 92, '6mo': 184, '1y': 366, '2y': 740, '5y': 1830,
}

/**
 * Whether the series that came back actually covers the range that was asked
 * for, and if not, what to tell the reader.
 *
 * A vendor plan can cap how far back history goes. Asking for five years of
 * AAPL returns 502 sessions — a little under two years — because the
 * answering vendor's plan stops there. The chart is then correct about every
 * point it draws and wrong about the one thing the control claims: the
 * window. A reader comparing "5Y" across two names is comparing two windows
 * neither of which is five years.
 *
 * The axis already carries the real dates. This says the quiet part: the
 * range you selected is not the range you got.
 *
 * Returns null when the series covers the request, which is the ordinary case.
 */
export function windowShortfall(
  range: string,
  firstDate: string | null | undefined,
  lastDate: string | null | undefined,
): string | null {
  const asked = RANGE_DAYS[range]
  if (!asked || !firstDate || !lastDate) return null

  const from = Date.parse(firstDate)
  const to = Date.parse(lastDate)
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return null

  const covered = (to - from) / 86_400_000
  // A week of slack absorbs holidays and a range that begins on a weekend.
  // Below 85% of the request the gap is structural, not calendar noise.
  if (covered >= asked * 0.85 || covered >= asked - 7) return null

  const years = covered / 365
  const span = years >= 1.5
    ? `${years.toFixed(1)} years`
    : `${Math.round(covered / 30.4)} months`
  return `History for this name begins ${firstDate}, so this window covers ${span} rather than the full range. The provider's plan limits how far back the series goes; the chart draws every session it was given.`
}

/**
 * A security's identity, on the fast path.
 *
 * The company's name is the first thing a reader needs and the research
 * payload is the last thing to arrive — twenty-five to sixty-five seconds for
 * a cold symbol. The symbol database answers the same question in about half
 * a second, so identity comes from there and the page can say "APPLE INC"
 * long before it can say anything about Apple.
 *
 * Read through the shared cache with the reference policy: a company's name
 * is the most stable fact on the page, and the search surface has usually
 * fetched it already on the way in.
 */
export async function fetchIdentity(symbol: string): Promise<SecurityIdentity | null> {
  const q = symbol.trim().toUpperCase()
  if (!q) return null

  const d = await readResource<{ results?: ScreenResult[] }>(
    `/api/screen?q=${encodeURIComponent(q)}`, 'reference',
  )
  const rows = (d.results ?? []).filter((x) => Boolean(x.symbol))

  // The search endpoint ranks by relevance, not by exactness. Asking for AAPL
  // and taking the first row would happily return an ADR that merely mentions
  // it, so the exact ticker is required rather than preferred.
  const exact = rows.find((x) => (x.symbol ?? '').toUpperCase() === q)
  if (!exact) return null

  return { symbol: q, name: exact.name ?? null, via: exact.via ?? null }
}
