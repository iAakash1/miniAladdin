'use client'

import { Badge, StateBlock, Value } from '@/components/system'
import Link from 'next/link'
import { useMemo, useState } from 'react'
import Skeleton from '@/components/ui/Skeleton'
import Tooltip from '@/components/ui/Tooltip'
import { FACTOR_LABELS, diffSnapshots, useAllHistory } from '@/lib/history'
import ActionMenu from '@/components/system/ActionMenu'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import SymbolSpark from '@/components/visual/SymbolSpark'
import { ConfidenceBar, StatusPill, TrendMark } from '@/components/ui/DataMarks'
import { notify } from '@/components/ui/Toasts'
import { fmtPctRaw, timeAgo, fmtSigned, fmtNum } from '@/lib/format'
import PositionsPanel from '@/components/terminal/PositionsPanel'
import PortfolioIntelligence from '@/components/terminal/PortfolioIntelligence'
import { refreshQuotes } from '@/lib/quote-hub'
import { useQuotes } from '@/lib/use-quotes'
import { useResearchHistory, verdictBadgeTone } from '@/lib/use-research-history'
import {
  type Watchlist,
  refreshWatchlists,
  removeTicker,
  useWatchlists,
  useWatchlistsStatus,
} from '@/lib/watchlists'

const VERDICT_ORDER = ['Strong Sell', 'Sell', 'Hold', 'Buy', 'Strong Buy']

/** One spelling for a verdict. The account's research record stores "BUY" and
 *  "STRONG_BUY"; this browser's snapshots store "Buy". Ranked as written, every
 *  recorded run sorted as unanalysed and the column mixed "BUY" with "Buy". */
export function canonicalVerdict(v: string): string {
  const words = v.trim().replace(/[_-]+/g, ' ').toLowerCase().split(/\s+/)
  const titled = words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  return VERDICT_ORDER.includes(titled) ? titled : v
}

/** How current a stored analysis is.
 *
 *  A watchlist is only useful if you can see at a glance which rows you can
 *  still trust. Shape carries the state as well as colour — solid, ring,
 *  dash — so it survives a colour-blind reader and a greyscale screenshot.
 *  The boundary is one week: analyses are recomputed on demand, not on a
 *  schedule, so anything older has seen a week of price action it never saw. */
function freshness(ts: string | null | undefined): string {
  if (!ts) return 'sdot--none'
  const age = Date.now() - new Date(ts).getTime()
  if (Number.isNaN(age)) return 'sdot--none'
  return age < 7 * 86_400_000 ? 'sdot--fresh' : 'sdot--stale'
}

function ChangeCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--ink-faint)' }}>—</span>
  // Fixed precision, via the shared formatter. Rendering `{value}%` raw meant
  // the 1D and 1W columns of the same row disagreed about decimals — "-1.62%"
  // next to "+1.6%" — and a change that rounds to zero kept its minus sign.
  const text = fmtPctRaw(value, 2, true)
  // The tone and the mark follow the figure as displayed (rounded to two
  // places), computed from the number — never by parsing the text back,
  // which carries a typographic minus.
  const signed = Math.round(value * 100) / 100
  const tone = signed > 0 ? 'var(--e-pos)' : signed < 0 ? 'var(--e-neg)' : 'var(--ink-muted)'
  // The mark is keyed to the *rounded* figure, not the raw one, so a move
  // that displays as 0.00% cannot show an arrow contradicting its own text.
  return (
    <span className="u-row" style={{ gap: 6, justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
      <TrendMark value={signed} />
      <span className="num" style={{ color: tone }}>{text}</span>
    </span>
  )
}

interface StorageRow {
  label: string
  location: string
  detail: string
}

const STORAGE_ROWS: StorageRow[] = [
  { label: 'Watchlists', location: 'Cloud', detail: 'Synced to your OmniSignal account — sign in on any device and they follow you.' },
  { label: 'Portfolio positions', location: 'Cloud', detail: 'Shares and average cost, stored per account like watchlists.' },
  { label: 'Analysis history & saved reports', location: 'Cloud', detail: 'Every completed analysis is recorded automatically to your account — browse it in the Research log tab.' },
  { label: 'Verdict timeline (Analyze page)', location: 'Browser', detail: 'The per-ticker run-to-run diff shown under an analysis still lives in this browser’s local storage.' },
  { label: 'Prices & quotes', location: 'Server (live)', detail: 'Read from the provider chain, shared with every other panel showing the same symbol, and re-read every 30 seconds or when you click Refresh. Held in memory for the session only — never stored between visits.' },
  { label: 'AI research narrative', location: 'Server (5 min cache)', detail: 'Briefly cached to avoid duplicate model calls; the full report is kept with each history row.' },
]

/** Explicit, unambiguous account of where portfolio data actually lives —
 *  the product currently keeps all user-editable state client-side by
 *  design, so this states that plainly rather than leaving it implicit. */
function StorageStatus() {
  return (
    <details className="panel disclosure panel--compact">
      <summary style={{ fontSize: 'var(--t-body)', fontWeight: 600, color: 'var(--ink)' }}>
        Where is this stored?
      </summary>
      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {STORAGE_ROWS.map((row) => (
          <div key={row.label} style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ width: 190, flexShrink: 0, fontSize: 'var(--t-small)', fontWeight: 600, color: 'var(--ink)' }}>
              {row.label}
            </span>
            <Badge>{row.location}</Badge>
            <span style={{ fontSize: 'var(--t-small)', color: 'var(--ink-muted)', lineHeight: 1.5, flex: '1 1 320px' }}>
              {row.detail}
            </span>
          </div>
        ))}
      </div>
    </details>
  )
}

export type SortKey =
  | 'ticker' | 'price' | 'change_1d' | 'change_1w' | 'verdict' | 'confidence' | 'analyzed'

export interface SortState { key: SortKey | null; dir: 'asc' | 'desc' }

interface SortableRow {
  ticker: string
  quote?: { price?: number | null; change_1d?: number | null; change_1w?: number | null }
  latest: { verdict: string; confidence: number | null; ts: string } | null
}

/** Value a column sorts on. `null` means "no value", and null always sorts
 *  last regardless of direction — a row with no analysis is not "the
 *  smallest", it is absent, and burying it under ascending confidence would
 *  hide exactly the rows that need attention. */
function sortValue(row: SortableRow, key: SortKey): number | string | null {
  switch (key) {
    case 'ticker': return row.ticker
    case 'price': return row.quote?.price ?? null
    case 'change_1d': return row.quote?.change_1d ?? null
    case 'change_1w': return row.quote?.change_1w ?? null
    case 'verdict': return row.latest ? VERDICT_ORDER.indexOf(row.latest.verdict) : null
    case 'confidence': return row.latest?.confidence ?? null
    case 'analyzed': return row.latest ? new Date(row.latest.ts).getTime() : null
    default: return null
  }
}

/** Stable sort by column. Returns the input untouched when no column is
 *  active, so the default verdict/confidence ranking survives. */
export function sortRows<T extends SortableRow>(rows: T[], sort: SortState): T[] {
  if (!sort.key) return rows
  const key = sort.key
  const sign = sort.dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const av = sortValue(a, key)
    const bv = sortValue(b, key)
    if (av === null && bv === null) return 0
    if (av === null) return 1          // absent rows sink, both directions
    if (bv === null) return -1
    if (typeof av === 'string' || typeof bv === 'string') {
      return sign * String(av).localeCompare(String(bv))
    }
    return sign * (av - bv)
  })
}

/** Click cycles: unsorted -> desc -> asc -> unsorted. Descending first
 *  because every column here is one people read "biggest first". */
export function nextSort(current: SortState, key: SortKey): SortState {
  if (current.key !== key) return { key, dir: 'desc' }
  if (current.dir === 'desc') return { key, dir: 'asc' }
  return { key: null, dir: 'desc' }
}

/** A column header that sorts.
 *
 *  `aria-sort` is what a screen reader announces, so it carries the state
 *  rather than the arrow glyph. The arrow is `aria-hidden` and reserved at
 *  all times — a caret that only exists on the active column shifts every
 *  other header by its width the moment you sort.
 */
function SortHeader({
  col, sort, onSort, num, children,
}: {
  col: SortKey
  sort: SortState
  onSort: (next: SortState) => void
  num?: boolean
  children: React.ReactNode
}) {
  const active = sort.key === col
  return (
    <th
      scope="col"
      className={num ? 'num' : undefined}
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        className={`th-sort${active ? ' is-active' : ''}`}
        onClick={() => onSort(nextSort(sort, col))}
      >
        {children}
        <span className="th-sort__caret" aria-hidden>
          {active ? (sort.dir === 'asc' ? '\u2191' : '\u2193') : '\u2195'}
        </span>
      </button>
    </th>
  )
}

/** What the research says about the names on your lists, and what changed. */
function ListMonitor() {
  const lists = useWatchlists()
  const wlStatus = useWatchlistsStatus()
  const history = useAllHistory()
  // Company names from the account's research record — a database read.
  const research = useResearchHistory()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [sort, setSort] = useState<SortState>({ key: null, dir: 'desc' })
  // The ticker whose removal is awaiting a second, explicit press.
  const [removing, setRemoving] = useState<string | null>(null)

  const active: Watchlist | null =
    lists.find((list) => list.id === activeId) ?? lists[0] ?? null

  /* This list reads prices from the shared hub rather than fetching its own.
     It used to fetch once on mount and never again, so a watchlist left open
     kept quoting a price the watchlist panel elsewhere had already replaced.
     Two surfaces disagreeing about the last trade of one security is not a
     cosmetic problem. */
  const { quotes, at: quotesFetchedAt, loading: loadingQuotes } =
    useQuotes(active?.tickers ?? [])


  /* ── ranking: analyzed first (verdict rank, then confidence), then by 1w momentum ── */
  const rows = useMemo(() => {
    if (!active) return []
    return active.tickers
      .map((ticker) => {
        const timeline = history[ticker] ?? []
        const local = timeline[timeline.length - 1] ?? null
        const previous = timeline.length >= 2 ? timeline[timeline.length - 2] : null
        const diff = local && previous ? diffSnapshots(previous, local) : null
        // The account's research record, not only this browser's. Home's
        // watchlist read the server record and this page read local storage,
        // so one AAPL was "Buy 33" there and "not analyzed" here. The newer
        // of the two runs is shown; the change columns still need the local
        // snapshots, which carry the factor detail the record does not.
        const recorded = research.latest(ticker)
        const recordedView = recorded ? {
          ts: recorded.created_at,
          verdict: canonicalVerdict(recorded.verdict),
          confidence: recorded.confidence,
          riskLevel: recorded.risk_level,
        } : null
        const latest = local && (!recordedView || Date.parse(local.ts) >= Date.parse(recordedView.ts))
          ? { ts: local.ts, verdict: canonicalVerdict(local.verdict), confidence: local.confidence as number | null, riskLevel: local.riskLevel }
          : recordedView
        return { ticker, quote: quotes[ticker], latest, previous, diff }
      })
      .sort((a, b) => {
        const aRank = a.latest ? VERDICT_ORDER.indexOf(a.latest.verdict) : -1
        const bRank = b.latest ? VERDICT_ORDER.indexOf(b.latest.verdict) : -1
        if (aRank !== bRank) return bRank - aRank
        if (a.latest && b.latest) return (b.latest.confidence ?? 0) - (a.latest.confidence ?? 0)
        return (b.quote?.change_1w ?? -999) - (a.quote?.change_1w ?? -999)
      })
  }, [active, history, quotes, research])

  const sortedRows = useMemo(() => sortRows(rows, sort), [rows, sort])

  const head = (
    <header className="sys-panel-head">
      <div className="sys-panel-head__title">
        <h2 className="sys-panel-title">Research across your lists</h2>
        <span className="sys-panel-sub">
          {active
            ? `${rows.length} ${rows.length === 1 ? 'name' : 'names'} in ${active.name} · ${rows.filter((r) => r.latest).length} researched`
            : 'verdicts and what changed between runs'}
        </span>
      </div>
      <Link className="cw-more" href="/terminal/watchlists">Manage lists</Link>
    </header>
  )

  /* ── store not ready yet: loading / unreachable / signed out ── */
  if (lists.length === 0 && (wlStatus === 'idle' || wlStatus === 'loading')) {
    return <section className="sys-panel pf-monitor">{head}<StateBlock state="waking" title="Loading your watchlists" /></section>
  }
  if (lists.length === 0 && wlStatus === 'unauthenticated') {
    return (
      <section className="sys-panel pf-monitor">
        {head}
        <StateBlock state="blocked" title="Sign in to see your lists" detail="Your session was not accepted. Lists are stored with your account and are unaffected." />
      </section>
    )
  }
  if (lists.length === 0 && wlStatus === 'error') {
    return (
      <section className="sys-panel pf-monitor">
        {head}
        <StateBlock state="unavailable" title="Your watchlists could not be loaded" detail="The persistence service did not answer. Your lists are stored on the server and are unaffected.">
          <button type="button" className="sys-btn" onClick={() => refreshWatchlists()}>Try again</button>
        </StateBlock>
      </section>
    )
  }

  /* ── no lists yet: what this section will show, and where lists are made ── */
  if (lists.length === 0) {
    return (
      <section className="sys-panel pf-monitor">
        {head}
        <div className="pf-monitor__empty">
          <p>
            Once you keep a watchlist, each name appears here with its latest verdict, confidence and
            risk, and with what changed since the run before. Holdings above do not depend on it.
          </p>
          <Link href="/terminal/watchlists" className="sys-btn">Create a watchlist</Link>
        </div>
      </section>
    )
  }

  return (
    <section className="sys-panel pf-monitor" aria-label="Research across your lists">
      {head}
      <div className="pf-monitor__bar">
        <div className="seg" role="group" aria-label="Watchlist">
          {lists.map((list) => (
            <button
              key={list.id}
              type="button"
              className="seg__btn"
              aria-pressed={active?.id === list.id}
              onClick={() => setActiveId(list.id)}
            >
              {list.name}
              <span className="num u-meta">{list.tickers.length}</span>
            </button>
          ))}
        </div>
        <span className="pf-monitor__quotes">
          {/* Feed state as a state, not as prose. The pulse is bound to
              an actual in-flight fetch, so it stops when the work does. */}
          {loadingQuotes ? (
            <StatusPill tone="accent" label="Fetching quotes" pulse />
          ) : quotesFetchedAt ? (
            <span className="u-meta">Quotes updated {timeAgo(quotesFetchedAt)}</span>
          ) : null}
          <button
            type="button"
            className="sys-btn sys-btn--ghost sys-btn--xs"
            onClick={() => refreshQuotes()}
            disabled={loadingQuotes || !active || active.tickers.length === 0}
          >
            {loadingQuotes ? 'Refreshing…' : 'Refresh quotes'}
          </button>
        </span>
      </div>

      {active && (
        <>
          {active.tickers.length === 0 ? (
            <p className="pf-monitor__note">
              {active.name} is empty. Add symbols on <Link href="/terminal/watchlists">Watchlists</Link>; researched
              names rank by verdict and confidence, the rest by weekly momentum.
            </p>
          ) : (
            <div className="sys-scroll-x">
              <table className="sys-table" style={{ minWidth: 960 }}>
                <caption className="visually-hidden">
                  {active.name} watchlist, ranked by verdict then confidence
                </caption>
                <thead>
                  <tr>
                    <SortHeader col="ticker" sort={sort} onSort={setSort}>Ticker</SortHeader>
                    <SortHeader col="price" sort={sort} onSort={setSort} num>Price</SortHeader>
                    <SortHeader col="change_1d" sort={sort} onSort={setSort} num>1D</SortHeader>
                    <SortHeader col="change_1w" sort={sort} onSort={setSort} num>1W</SortHeader>
                    <th scope="col">3 months</th>
                    <SortHeader col="verdict" sort={sort} onSort={setSort}>Verdict</SortHeader>
                    <th scope="col">Previous</th>
                    <th scope="col">Change</th>
                    <SortHeader col="confidence" sort={sort} onSort={setSort} num>Confidence</SortHeader>
                    <th scope="col">Risk</th>
                    <SortHeader col="analyzed" sort={sort} onSort={setSort}>Last analyzed</SortHeader>
                    <th scope="col" className="num"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map(({ ticker, quote, latest, previous, diff }) => (
                    <tr key={ticker}>
                      <td>
                        <CompanyIdentity
                          symbol={ticker}
                          name={research.latest(ticker)?.company_name}
                          size="sm"
                          href={`/company/${encodeURIComponent(ticker)}`}
                        />
                      </td>
                      <td className="num">
                        {loadingQuotes && !quote ? <Skeleton width={54} height={14} /> :
                          quote?.price != null ? <Value value={quote.price} kind="currency" /> : <span style={{ color: 'var(--ink-faint)' }}>—</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}><ChangeCell value={quote?.change_1d} /></td>
                      <td style={{ textAlign: 'right' }}><ChangeCell value={quote?.change_1w} /></td>
                      <td><SymbolSpark values={quote?.closes ?? (quotesFetchedAt ? [] : undefined)} width={84} height={20} /></td>
                      <td>
                        {latest ? (
                          <Badge tone={verdictBadgeTone(latest.verdict)}>{latest.verdict}</Badge>
                        ) : (
                          <span style={{ fontSize: 'var(--t-small)', color: 'var(--ink-faint)' }}>not analyzed</span>
                        )}
                      </td>
                      <td style={{ fontSize: 'var(--t-small)', color: 'var(--ink-faint)' }}>
                        {previous ? previous.verdict : '—'}
                      </td>
                      <td>
                        {diff && (diff.verdictChanged || Math.abs(diff.confidenceDelta) >= 3) ? (
                          <Tooltip label={`Why ${ticker} changed`}>
                            <p style={{ margin: 0, fontWeight: 600, color: 'var(--ink)' }}>
                              Confidence {fmtSigned(diff.confidenceDelta, 0)}pp
                              {diff.scoreDelta !== null && ` · composite ${fmtSigned(diff.scoreDelta, 3)}`}
                            </p>
                            {diff.topDrivers.length > 0 && (
                              <ul style={{ listStyle: 'none', margin: '6px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {diff.topDrivers.slice(0, 3).map((driver) => (
                                  <li key={driver.name} className="u-meta">
                                    {FACTOR_LABELS[driver.name] ?? driver.name}: {fmtNum(driver.before, 2)} → {fmtNum(driver.after, 2)}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </Tooltip>
                        ) : null}
                        {diff?.verdictChanged ? (
                          <Badge tone={diff.direction === 'upgrade' ? 'pass' : 'fail'}>
                            {diff.direction === 'upgrade' ? '▲ upgrade' : '▼ downgrade'}
                          </Badge>
                        ) : latest ? (
                          <span style={{ fontSize: 'var(--t-small)', color: 'var(--ink-faint)' }}>unchanged</span>
                        ) : null}
                      </td>
                      <td className="num">
                        <ConfidenceBar value={latest?.confidence} />
                      </td>
                      <td className="u-note">
                        {latest?.riskLevel?.toLowerCase() ?? '—'}
                      </td>
                      <td className="u-note">
                        <span className="u-row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                          <span className={`sdot ${freshness(latest?.ts)}`} aria-hidden />
                          {latest ? timeAgo(latest.ts) : 'never analyzed'}
                        </span>
                      </td>
                      <td className="trk-acts">
                        {removing === ticker ? (
                          <span className="trk-confirm" role="group" aria-label={`Remove ${ticker} from ${active.name}?`}>
                            <button
                              type="button" className="sys-btn sys-btn--xs sys-btn--danger"
                              onClick={() => {
                                setRemoving(null)
                                removeTicker(active.id, ticker)
                                notify(`${ticker} removed from ${active.name}`)
                              }}
                            >
                              Remove {ticker}
                            </button>
                            <button type="button" className="sys-btn sys-btn--xs" onClick={() => setRemoving(null)}>Keep</button>
                          </span>
                        ) : (
                          <>
                            <Link href={`/company/${encodeURIComponent(ticker)}`} className="sys-btn sys-btn--xs">Open</Link>
                            <ActionMenu
                              label={`Actions for ${ticker}`}
                              items={[
                                { kind: 'link', label: 'Paper order…', href: `/terminal/paper?ticket=${encodeURIComponent(ticker)}&origin=watchlist` },
                                { kind: 'separator' },
                                { label: `Remove from ${active.name}…`, onSelect: () => setRemoving(ticker), tone: 'danger' },
                              ]}
                            />
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="pf-monitor__note">
            Verdict, confidence and risk come from your account&apos;s latest research run; the change
            columns compare the last two runs opened in this browser. Quotes via the provider fallback
            chain; trends are three months of daily closes.
          </p>
        </>
      )}
    </section>
  )
}

/**
 * The portfolio: what you hold, how it has done, where the risk sits — then
 * what the research says about the names you follow. Holdings never wait on
 * watchlists: an account with positions and no lists still sees its book.
 */
export default function PortfolioView() {
  return (
    <div className="pf-page">
      <PositionsPanel />
      {/* Book-level figures sit under the positions they are computed
          from, so the reader has already seen the holdings the
          concentration is about. */}
      <PortfolioIntelligence />
      <ListMonitor />
      <StorageStatus />
    </div>
  )
}
