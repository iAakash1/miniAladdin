/**
 * The commands that only make sense where the reader currently is.
 *
 * The palette offered twenty-four variations of "Go to X" and nothing else,
 * which makes it a menu with a text box. A palette earns its shortcut by
 * acting on the thing being investigated: standing on AAPL, the useful
 * commands are about AAPL, and standing on a comparison they are about the
 * pair.
 *
 * This is a pure function of the route so it can be tested without a browser,
 * and so the palette cannot offer an action for an object that is not open.
 * Nothing here invents a destination: every href is a route the product
 * already serves, and every anchor is an id the target page actually renders.
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
  /** Whether the current symbol is on the watchlist. */
  watched?: boolean
}

const sec = (s: string) => `/terminal/security?symbol=${encodeURIComponent(s)}`

/**
 * Commands for the object currently open, most useful first.
 *
 * Returns an empty list where the route carries no object — the palette then
 * shows navigation alone, which is the honest answer rather than a set of
 * actions pointing at nothing.
 */
export function contextCommands(ctx: RouteContext): ContextCommand[] {
  const { pathname, params } = ctx

  if (pathname.startsWith('/terminal/security')) {
    const symbol = (params.symbol ?? '').toUpperCase()
    if (!symbol) return []

    // The last other name this browser opened. Comparison needs a second
    // security and the one just looked at is the one usually meant; with no
    // second name the command is omitted rather than offered against nothing.
    const against = (ctx.recent ?? []).find((s) => s.toUpperCase() !== symbol)

    return [
      ctx.watched
        ? { id: 'unwatch', label: `Remove ${symbol} from watchlist`, act: 'unwatch', symbol }
        : { id: 'watch', label: `Add ${symbol} to watchlist`, act: 'watch', symbol },
      ...(against ? [{
        id: 'compare',
        label: `Compare ${symbol} with ${against}`,
        note: 'the last other name opened here',
        href: `/terminal/compare?a=${encodeURIComponent(symbol)}&b=${encodeURIComponent(against)}`,
      }] : []),
      // Anchors the security page actually renders. See app/terminal/security.
      { id: 'fundamentals', label: `${symbol} fundamentals`, note: 'valuation, margins, growth, ownership', href: `${sec(symbol)}#sec-fundamentals` },
      { id: 'filings', label: `${symbol} filings and coverage`, note: 'primary source documents', href: `${sec(symbol)}#sec-company` },
      { id: 'price', label: `${symbol} price history`, href: `${sec(symbol)}#sec-price` },
      /* Reaches the security page, where the ticket lives — not a separate
         trading screen. An order is something done to the object in front of
         you, and the label says paper wherever it appears. */
      { id: 'paper', label: `Paper trade ${symbol}`, note: 'simulated account — no real money', href: sec(symbol) },
    ]
  }

  if (pathname.startsWith('/terminal/compare')) {
    const a = (params.a ?? '').toUpperCase()
    const b = (params.b ?? '').toUpperCase()
    if (!a || !b) return []
    return [
      { id: 'swap', label: `Swap — ${b} against ${a}`, note: 'reverses which side is the baseline', href: `/terminal/compare?a=${encodeURIComponent(b)}&b=${encodeURIComponent(a)}` },
      { id: 'open-a', label: `Open ${a}`, href: sec(a) },
      { id: 'open-b', label: `Open ${b}`, href: sec(b) },
    ]
  }

  return []
}
