/**
 * The tab title for a page that is about one security.
 *
 * The company, evidence and agent-run pages are client components or share a
 * layout, so none could set a title: every company a reader opened was a tab
 * called "OmniSignal — Evidence-grounded equity research", and a browser
 * history of a day's research read as the same page forty times. The root
 * layout's template appends " · OmniSignal".
 */

const SYMBOL = /^[A-Z0-9.^-]{1,10}$/

/**
 * A URL segment as text. A stray "%" is not a reason to throw: this runs in
 * the shell and in the palette, which are mounted on every page, so a bad
 * escape in an address must not take the whole screen down with it.
 */
export function safeDecode(segment: string | undefined | null): string {
  if (!segment) return ''
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

/** A route segment as the symbol it names, or null when it is not one. */
export function symbolFromSegment(segment: string | undefined): string | null {
  if (!segment) return null
  let decoded: string
  try {
    decoded = decodeURIComponent(segment)
  } catch {
    return null
  }
  const symbol = decoded.toUpperCase()
  return SYMBOL.test(symbol) ? symbol : null
}

export function securityTitle(segment: string | undefined, what: string, fallback: string): string {
  const symbol = symbolFromSegment(segment)
  return symbol ? `${symbol} ${what}` : fallback
}
