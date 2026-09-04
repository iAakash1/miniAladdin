/**
 * Every place a reader can go, declared once.
 *
 * The sidebar, the command palette, the keyboard chords and the shortcut sheet
 * were four independent lists of the same destinations. They drifted, exactly
 * as four hand-maintained copies of anything drift: "Go to Securities" in the
 * palette pointed at /terminal/analyze while the same label under the same
 * `g s` in the sidebar pointed at /terminal/security. Both routes were live, so
 * nothing failed — the reader simply arrived somewhere else depending on how
 * they asked, and one of the two destinations was still running the shell the
 * rest of the product had replaced.
 *
 * One list. The four surfaces read it.
 *
 * The grouping is by what a reader is doing, not by the research pipeline's
 * stages. It used to run Observe / Explain / Validate / Allocate / Verify /
 * Record — an accurate description of how the research was built and a poor
 * description of how anyone uses the product. Terminal comes first because it
 * is where a session starts and returns; Research and Evidence are real and
 * sit below the things used every day.
 */

export interface Destination {
  /** Canonical route. */
  href: string
  /** What the reader calls it, everywhere it appears. */
  label: string
  /** Fixed-width mark, so the eye tracks a straight left edge down the list. */
  glyph: string
  /** The letter that follows `g`. Unique across the registry. */
  key: string
  /** The question this workspace answers, for the palette's result context. */
  answers: string
}

export interface DestinationGroup {
  /** A stage of the research loop, not a backend module. */
  group: string
  items: Destination[]
}

export const DESTINATIONS: DestinationGroup[] = [
  {
    // What a terminal opens on and returns to. Four destinations, used daily.
    group: 'Terminal',
    items: [
      { href: '/terminal/command', label: 'Terminal', glyph: '⌘', key: 'c', answers: 'what you are watching, and what moved' },
      { href: '/terminal/security', label: 'Securities', glyph: 'T', key: 's', answers: 'one name: price, history, and our record against it' },
      { href: '/terminal/market', label: 'Market', glyph: 'M', key: 'j', answers: 'indices, breadth, sectors and what changed' },
      { href: '/terminal/portfolio', label: 'Watchlists', glyph: 'W', key: 'z', answers: 'the names you are following' },
      // Named "Paper", never "Trade" or "Portfolio". The label is the first
      // and most-seen place the environment is stated, and a nav entry that
      // reads "Trade" has already implied something untrue.
      //
      // The chord is `i`, not `p`: Performance has held `p` since before this
      // existed, and quietly taking a letter out from under an existing
      // workspace breaks the muscle memory of anyone already using it. The
      // route-integrity test caught the collision, which is what it is for.
      { href: '/terminal/paper', label: 'Paper', glyph: 'P', key: 'i', answers: 'a simulated account — no real money' },
    ],
  },
  {
    // The book and what it risks.
    group: 'Portfolio',
    items: [
      { href: '/terminal/book', label: 'Book', glyph: 'B', key: 'b', answers: 'what is held, and what it costs to hold it' },
      { href: '/terminal/risk', label: 'Risk', glyph: 'R', key: 'r', answers: 'where the risk is, under four different assumptions' },
      { href: '/terminal/covariance', label: 'Covariance', glyph: 'Σ', key: 'k', answers: 'how the estimators disagree' },
      { href: '/terminal/performance', label: 'Performance', glyph: '∿', key: 'p', answers: 'what the strategy did, gross and net' },
    ],
  },
  {
    // The analytical layer. Real, and secondary to the terminal above it.
    group: 'Research',
    items: [
      { href: '/terminal/factorlab', label: 'Factors', glyph: 'K', key: 'f', answers: 'what explains cross-sectional behaviour' },
      { href: '/terminal/signals', label: 'Signals', glyph: 'S', key: 'g', answers: 'what the search found, and what it cost in significance' },
      { href: '/terminal/lab', label: 'Models', glyph: 'µ', key: 'm', answers: 'what was trained, and what survived out of sample' },
      { href: '/terminal/relationships', label: 'Relationships', glyph: '◇', key: 'h', answers: 'what connects to what, and on whose authority' },
      { href: '/terminal/compare', label: 'Compare', glyph: '⇄', key: 'w', answers: 'one object against another, where that is meaningful' },
      { href: '/terminal/diff', label: 'Difference', glyph: 'Δ', key: 'q', answers: 'what changed between two artifacts' },
    ],
  },
  {
    // Whether any of it should be believed. The archive lives here.
    group: 'Evidence',
    items: [
      { href: '/terminal/evidence', label: 'Evidence', glyph: 'E', key: 'v', answers: 'whether any of it should be believed' },
      { href: '/terminal/gates', label: 'Gates', glyph: '⊟', key: 'a', answers: 'what blocks everything' },
      { href: '/terminal/experiments', label: 'Experiments', glyph: 'X', key: 'x', answers: 'the research record, including the void ones' },
      { href: '/terminal/calibration', label: 'Calibration', glyph: 'C', key: 'u', answers: 'whether a score means what it says' },
    ],
  },
  {
    group: 'Data',
    items: [
      { href: '/terminal/data', label: 'Data', glyph: 'D', key: 'd', answers: 'whether this data can be trusted for research' },
      { href: '/terminal/providers', label: 'Providers', glyph: 'V', key: 'o', answers: 'who supplied what, and whether they are reporting' },
      { href: '/terminal/provenance', label: 'Provenance', glyph: '⤳', key: 'n', answers: 'where a result came from, and where trust stopped' },
      { href: '/terminal/handbook', label: 'Handbook', glyph: 'H', key: 'y', answers: 'how every measure is computed' },
    ],
  },
  {
    group: 'Record',
    items: [
      { href: '/terminal/memos', label: 'Memos', glyph: 'N', key: 'e', answers: 'what was written down' },
      { href: '/terminal/timeline', label: 'Timeline', glyph: '│', key: 't', answers: 'what happened, in order' },
    ],
  },
]


/** Flat view, in navigation order. */
export const ALL_DESTINATIONS: Destination[] = DESTINATIONS.flatMap((g) => g.items)

/** The `g`-chord map, derived rather than restated. */
export const GOTO: Record<string, string> = Object.fromEntries(
  ALL_DESTINATIONS.map((d) => [d.key, d.href]),
)

/** One destination by its chord letter. */
export function destinationFor(key: string): Destination | undefined {
  return ALL_DESTINATIONS.find((d) => d.key === key)
}

/** One destination by route, for breadcrumbs and active-state marking. */
export function destinationAt(pathname: string): Destination | undefined {
  return ALL_DESTINATIONS.find((d) => pathname === d.href || pathname.startsWith(`${d.href}/`))
}
