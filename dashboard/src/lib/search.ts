/*
 * Instant local matches for the search box.
 *
 * The search box waits 160ms and then asks the backend. Until that answer
 * lands there is nothing on screen, so typing "NVDA" shows an empty list for
 * as long as the network takes — even when NVDA is sitting in the reader's
 * own watchlist and the answer was known before the keystroke finished.
 *
 * These are matched against what this browser already holds, so they render
 * on the same frame as the keystroke. The network answer replaces them when
 * it arrives; it does not merge with them, because a local hit and a vendor
 * hit are different claims and interleaving them would make the list reorder
 * under the reader's cursor.
 *
 * Pure and side-effect-free so it is unit-testable, which is how the previous
 * version survived: it was tested, correct, and wired to nothing. It read a
 * `Watchlist[]` and an analysis history that the live search box does not
 * use, so it could never have run. It now takes the two lists the box
 * actually holds.
 */

import { watchSnapshot } from './symbols'

export interface LocalMatch {
  symbol: string
  /** Why this row is here — "Watchlist", "Recent". Never invented. */
  context: string
}

const MAX_LOCAL_MATCHES = 5

/**
 * Symbols this browser already knows that match what is being typed.
 *
 * A prefix match, not a substring one. "AP" should not surface GAP above
 * AAPL: in a ticker box the reader is typing the start of a symbol, and
 * substring matching puts accidental interior hits alongside the thing they
 * are actually reaching for.
 */
export function localMatches(
  value: string,
  recent: readonly string[],
  watched: readonly string[] = watchSnapshot(),
): LocalMatch[] {
  const needle = value.trim().toUpperCase()
  if (!needle) return []

  const out: LocalMatch[] = []
  const seen = new Set<string>()

  // Watchlist first: an explicitly kept symbol outranks one merely visited.
  for (const [list, context] of [[watched, 'Watchlist'], [recent, 'Recent']] as const) {
    for (const ticker of list) {
      const symbol = ticker.toUpperCase()
      if (seen.has(symbol) || !symbol.startsWith(needle)) continue
      seen.add(symbol)
      out.push({ symbol, context })
      if (out.length >= MAX_LOCAL_MATCHES) return out
    }
  }
  return out
}

export interface HighlightSegment {
  text: string
  match: boolean
}

/** Splits `text` around the first case-insensitive occurrence of `query`
 * so the caller can render the matched slice distinctly (e.g. <mark>). */
export function highlightSegments(text: string, query: string): HighlightSegment[] {
  const needle = query.trim()
  if (!needle) return [{ text, match: false }]

  const index = text.toLowerCase().indexOf(needle.toLowerCase())
  if (index === -1) return [{ text, match: false }]

  const segments: HighlightSegment[] = []
  if (index > 0) segments.push({ text: text.slice(0, index), match: false })
  segments.push({ text: text.slice(index, index + needle.length), match: true })
  if (index + needle.length < text.length) {
    segments.push({ text: text.slice(index + needle.length), match: false })
  }
  return segments
}
