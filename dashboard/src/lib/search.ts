/*
 * Pure helpers for the unified search box (search-fix pass).
 *
 * Local matches surface portfolio/watchlist/history hits instantly, with
 * zero network dependency — the fix for "NVDA -> Nothing Found" while NVDA
 * sat in the user's own portfolio does not need the backend to answer at
 * all for that case. Kept pure and side-effect-free so it's unit-testable
 * the same way lib/history.ts's diffSnapshots is.
 */

import type { AnalysisSnapshot } from './history'
import type { Watchlist } from './watchlists'

export interface LocalMatch {
  symbol: string
  context: string
}

const MAX_LOCAL_MATCHES = 5

/** Substring match (case-insensitive on the ticker) against the user's own
 * watchlists and analysis history — no network round trip. */
export function localMatches(
  value: string,
  lists: Watchlist[],
  history: Record<string, AnalysisSnapshot[]>,
): LocalMatch[] {
  const needle = value.trim().toUpperCase()
  if (!needle) return []

  const out: LocalMatch[] = []
  const seen = new Set<string>()

  for (const list of lists) {
    for (const ticker of list.tickers) {
      if (seen.has(ticker) || !ticker.includes(needle)) continue
      seen.add(ticker)
      out.push({ symbol: ticker, context: `In ${list.name}` })
    }
  }

  for (const [ticker, timeline] of Object.entries(history)) {
    if (seen.has(ticker) || !ticker.includes(needle) || timeline.length === 0) continue
    seen.add(ticker)
    const latest = timeline[timeline.length - 1]
    out.push({ symbol: ticker, context: `Analyzed — ${latest.verdict}` })
  }

  return out.slice(0, MAX_LOCAL_MATCHES)
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
