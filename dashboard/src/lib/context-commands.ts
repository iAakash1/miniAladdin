/**
 * The commands that only make sense where the reader currently is.
 *
 * A palette earns its shortcut by acting on the thing being investigated:
 * standing on AAPL, the useful commands are about AAPL. This is a pure
 * function of the route so it can be tested without a browser, and so the
 * palette cannot offer an action for an object that is not open. Every href
 * is a route the product serves.
 */

export interface ContextCommand {
  id: string
  label: string
  /** What it does, where the label alone is not enough. */
  note?: string
  /** A route to push. Exactly one of href or `act` is set. */
  href?: string
  /** A named side effect the palette knows how to run. */
  act?: 'watch' | 'unwatch'
  /** The symbol an action applies to. */
  symbol?: string
}

export interface RouteContext {
  pathname: string
  /** Query parameters, already decoded. */
  params: Record<string, string | undefined>
  /** Symbols this browser has opened, most recent first. */
  recent?: string[]
  /** Whether the current symbol is on one of the account's lists. */
  watched?: boolean
}

export const companyHref = (symbol: string, tab?: string): string =>
  `/company/${encodeURIComponent(symbol)}${tab && tab !== 'overview' ? `?tab=${tab}` : ''}`

/** The symbol a company route names, or null. */
export function companyFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/company\/([^/?#]+)/)
  return m ? decodeURIComponent(m[1]).toUpperCase() : null
}

const TABS: Array<{ tab: string; label: string; note: string }> = [
  { tab: 'evidence', label: 'evidence and provenance', note: 'inputs, provider agreement, validation' },
  { tab: 'report', label: 'research report', note: 'the full grounded report' },
  { tab: 'financials', label: 'financials', note: 'SEC filed facts, statements, ratios' },
  { tab: 'filings', label: 'SEC filings', note: 'primary-source documents' },
  { tab: 'technicals', label: 'technicals', note: 'price structure and indicators' },
  { tab: 'relationships', label: 'relationships', note: 'knowledge graph around the company' },
]

/**
 * Commands for the object currently open, most useful first. Empty where the
 * route carries no object.
 */
export function contextCommands(ctx: RouteContext): ContextCommand[] {
  const { pathname, params } = ctx

  const symbol = companyFromPath(pathname)
  if (symbol) {
    // Comparison needs a second security; the last other name opened is the
    // one usually meant. With none, the command is omitted.
    const against = (ctx.recent ?? []).find((s) => s.toUpperCase() !== symbol)
    return [
      ctx.watched
        ? { id: 'unwatch', label: `Remove ${symbol} from watchlists`, act: 'unwatch', symbol }
        : { id: 'watch', label: `Add ${symbol} to watchlist`, act: 'watch', symbol },
      ...TABS.map((t) => ({ id: t.tab, label: `${symbol} ${t.label}`, note: t.note, href: companyHref(symbol, t.tab) })),
      ...(against ? [{
        id: 'compare',
        label: `Compare ${symbol} with ${against}`,
        note: 'the last other name opened here',
        href: `/terminal/compare?a=${encodeURIComponent(symbol)}&b=${encodeURIComponent(against)}`,
      }] : []),
      { id: 'agents', label: `Run the agent pipeline for ${symbol}`, note: 'claim-by-claim trace and validation', href: `/terminal/agents/${encodeURIComponent(symbol)}` },
      { id: 'paper', label: `Paper trade ${symbol}`, note: 'simulated account — no real money', href: `${companyHref(symbol)}?paper=1` },
    ]
  }

  if (pathname.startsWith('/terminal/compare')) {
    const a = (params.a ?? '').toUpperCase()
    const b = (params.b ?? '').toUpperCase()
    if (!a || !b) return []
    return [
      { id: 'swap', label: `Swap — ${b} against ${a}`, note: 'reverses which side is the baseline', href: `/terminal/compare?a=${encodeURIComponent(b)}&b=${encodeURIComponent(a)}` },
      { id: 'open-a', label: `Open ${a}`, href: companyHref(a) },
      { id: 'open-b', label: `Open ${b}`, href: companyHref(b) },
    ]
  }

  return []
}
