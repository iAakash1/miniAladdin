'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import PageHeader from '@/components/ui/PageHeader'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import Tooltip from '@/components/ui/Tooltip'
import { FACTOR_LABELS, diffSnapshots, useAllHistory } from '@/lib/history'
import ConfirmButton from '@/components/ui/ConfirmButton'
import CompanyMark from '@/components/ui/CompanyMark'
import { ConfidenceBar } from '@/components/ui/DataMarks'
import { notify } from '@/components/ui/Toasts'
import { fmtPctRaw, timeAgo } from '@/lib/format'
import PositionsPanel from '@/components/terminal/PositionsPanel'
import {
  SUGGESTED_LISTS,
  type Watchlist,
  addTicker,
  createWatchlist,
  deleteWatchlist,
  refreshWatchlists,
  removeTicker,
  useWatchlists,
  useWatchlistsStatus,
} from '@/lib/watchlists'

interface Quote {
  price?: number
  change_1d?: number | null
  change_1w?: number | null
  error?: string
  stale?: boolean
}

const VERDICT_ORDER = ['Strong Sell', 'Sell', 'Hold', 'Buy', 'Strong Buy']

function verdictTone(verdict: string): string {
  return verdict.includes('Buy') ? 'badge--pos' : verdict.includes('Sell') ? 'badge--neg' : 'badge--warn'
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
  if (value === null || value === undefined) return <span style={{ color: 'var(--faint)' }}>—</span>
  // Fixed precision, via the shared formatter. Rendering `{value}%` raw meant
  // the 1D and 1W columns of the same row disagreed about decimals — "-1.62%"
  // next to "+1.6%" — and a change that rounds to zero kept its minus sign.
  const text = fmtPctRaw(value, 2, true)
  const tone = parseFloat(text) > 0 ? 'var(--pos)' : parseFloat(text) < 0 ? 'var(--neg)' : 'var(--muted)'
  return <span className="num" style={{ color: tone }}>{text}</span>
}

interface StorageRow {
  label: string
  location: string
  detail: string
}

const STORAGE_ROWS: StorageRow[] = [
  { label: 'Watchlists', location: 'Cloud', detail: 'Synced to your OmniSignal account — sign in on any device and they follow you.' },
  { label: 'Portfolio positions', location: 'Cloud', detail: 'Shares and average cost, stored per account like watchlists.' },
  { label: 'Analysis history & saved reports', location: 'Cloud', detail: 'Every completed analysis is recorded automatically to your account — browse it in the Vault tab.' },
  { label: 'Verdict timeline (Analyze page)', location: 'Browser', detail: 'The per-ticker run-to-run diff shown under an analysis still lives in this browser’s local storage.' },
  { label: 'Prices & quotes', location: 'Server (live)', detail: 'Fetched fresh from the provider chain each time you open this list or click Refresh — not cached in your browser between visits.' },
  { label: 'AI research narrative', location: 'Server (5 min cache)', detail: 'Briefly cached to avoid duplicate model calls; the full report is kept with each history row.' },
]

/** Explicit, unambiguous account of where portfolio data actually lives —
 *  the product currently keeps all user-editable state client-side by
 *  design, so this states that plainly rather than leaving it implicit. */
function StorageStatus() {
  return (
    <details className="panel disclosure" style={{ padding: '14px 18px' }}>
      <summary style={{ fontSize: '0.8125rem', fontWeight: 550, color: 'var(--text)' }}>
        Where is this stored?
      </summary>
      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {STORAGE_ROWS.map((row) => (
          <div key={row.label} style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ width: 190, flexShrink: 0, fontSize: '0.75rem', fontWeight: 550, color: 'var(--text)' }}>
              {row.label}
            </span>
            <span
              className="badge badge--neutral"
              style={{ height: 19, fontSize: '0.625rem', flexShrink: 0 }}
            >
              {row.location}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--muted)', lineHeight: 1.5, flex: '1 1 320px' }}>
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
  quote?: { price?: number; change_1d?: number | null; change_1w?: number | null }
  latest: { verdict: string; confidence: number; ts: string } | null
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

export default function PortfolioView() {
  const lists = useWatchlists()
  const wlStatus = useWatchlistsStatus()
  const history = useAllHistory()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [addSymbol, setAddSymbol] = useState('')
  const [quotes, setQuotes] = useState<Record<string, Quote>>({})
  const [loadingQuotes, setLoadingQuotes] = useState(false)
  const [quotesReload, setQuotesReload] = useState(0)
  const [quotesFetchedAt, setQuotesFetchedAt] = useState<string | null>(null)
  const [sort, setSort] = useState<SortState>({ key: null, dir: 'desc' })

  const active: Watchlist | null =
    lists.find((list) => list.id === activeId) ?? lists[0] ?? null
  const activeTickersKey = active?.tickers.join(',') ?? ''

  useEffect(() => {
    if (!activeTickersKey) {
      queueMicrotask(() => setQuotes({}))
      return undefined
    }
    const controller = new AbortController()
    let alive = true
    queueMicrotask(() => {
      if (alive) setLoadingQuotes(true)
    })
    fetch(`/api/quotes?symbols=${encodeURIComponent(activeTickersKey)}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((json: { quotes: Record<string, Quote> }) => {
        if (alive) {
          setQuotes(json.quotes ?? {})
          setQuotesFetchedAt(new Date().toISOString())
        }
      })
      .catch((error: unknown) => {
        if (alive && (error as Error).name !== 'AbortError') setQuotes({})
      })
      .finally(() => {
        if (alive) setLoadingQuotes(false)
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [activeTickersKey, quotesReload])

  /* ── ranking: analyzed first (verdict rank, then confidence), then by 1w momentum ── */
  const rows = useMemo(() => {
    if (!active) return []
    return active.tickers
      .map((ticker) => {
        const timeline = history[ticker] ?? []
        const latest = timeline[timeline.length - 1] ?? null
        const previous = timeline.length >= 2 ? timeline[timeline.length - 2] : null
        const diff = latest && previous ? diffSnapshots(previous, latest) : null
        return { ticker, quote: quotes[ticker], latest, previous, diff }
      })
      .sort((a, b) => {
        const aRank = a.latest ? VERDICT_ORDER.indexOf(a.latest.verdict) : -1
        const bRank = b.latest ? VERDICT_ORDER.indexOf(b.latest.verdict) : -1
        if (aRank !== bRank) return bRank - aRank
        if (a.latest && b.latest) return b.latest.confidence - a.latest.confidence
        return (b.quote?.change_1w ?? -999) - (a.quote?.change_1w ?? -999)
      })
  }, [active, history, quotes])

  const sortedRows = useMemo(() => sortRows(rows, sort), [rows, sort])

  /* ── store not ready yet: loading / unreachable ── */
  if (lists.length === 0 && (wlStatus === 'idle' || wlStatus === 'loading')) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} aria-busy="true">
        <Skeleton height={40} width={320} />
        <Skeleton height={220} />
      </div>
    )
  }
  if (lists.length === 0 && wlStatus === 'error') {
    return (
      <EmptyState
        title="Your watchlists couldn't be loaded"
        description="The persistence service didn't respond. Your lists are safe on the server — try again in a moment."
        action={
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => refreshWatchlists()}>
            Try again
          </button>
        }
      />
    )
  }

  /* ── no lists yet: suggestions ── */
  if (lists.length === 0) {
    return (
      <div>
        <EmptyState
          title="No watchlists yet"
          description="Create your first list, or start from a suggestion — lists are saved to your account and follow you across devices."
        />
        <div className="terminal-grid-four" style={{ maxWidth: 880, margin: '0 auto' }}>
          {SUGGESTED_LISTS.map((suggestion) => (
            <button
              key={suggestion.name}
              type="button"
              className="panel"
              onClick={() => void createWatchlist(suggestion.name, suggestion.tickers)}
              style={{ padding: '16px 18px', textAlign: 'left', cursor: 'pointer', background: 'var(--surface)' }}
            >
              <p className="h-panel" style={{ marginBottom: 6 }}>{suggestion.name}</p>
              <p className="num" style={{ fontSize: '0.6875rem', color: 'var(--muted)' }}>
                {suggestion.tickers.join(' · ')}
              </p>
            </button>
          ))}
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (newName.trim()) {
              void createWatchlist(newName)
              setNewName('')
            }
          }}
          style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 20 }}
        >
          <label htmlFor="new-list" className="visually-hidden">New watchlist name</label>
          <input
            id="new-list"
            className="input input--sm"
            style={{ maxWidth: 220 }}
            placeholder="Or name a new list…"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
          <button type="submit" className="btn btn--secondary btn--sm" disabled={!newName.trim()}>
            Create
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="page-stack">
      {/* Portfolio was the only route with no header at all: it opened
          straight into the watchlist switcher, which butted against the
          global nav and read as content clipped underneath it. The layout
          was never wrong — 28px of clearance was always there — the page
          simply had nothing establishing it. */}
      <PageHeader
        eyebrow="Portfolio"
        title="Watchlists & positions"
        lede="Every name you track, scored by the same engine as a full research report. Watchlists sync to your account; positions stay on this device."
        meta={
          <>
            <span>{lists.length} list{lists.length === 1 ? '' : 's'}</span>
            <span>{rows.length} name{rows.length === 1 ? '' : 's'} tracked</span>
          </>
        }
      />

      {/* List switcher */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <div className="seg" role="group" aria-label="Watchlists" style={{ flexWrap: 'wrap' }}>
          {lists.map((list) => (
            <button
              key={list.id}
              type="button"
              className="seg__btn"
              aria-pressed={active?.id === list.id}
              onClick={() => setActiveId(list.id)}
            >
              {list.name}
 <span className="num u-meta" >
                {list.tickers.length}
              </span>
            </button>
          ))}
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (newName.trim()) {
              void createWatchlist(newName).then((created) => {
                if (created) setActiveId(created.id)
              })
              setNewName('')
            }
          }}
          style={{ display: 'flex', gap: 6 }}
        >
          <label htmlFor="another-list" className="visually-hidden">New watchlist name</label>
          <input
            id="another-list"
            className="input"
            style={{ width: 150, height: 32, fontSize: '0.8125rem' }}
            placeholder="New list…"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
          <button type="submit" className="btn btn--ghost btn--sm" disabled={!newName.trim()}>
            Add
          </button>
        </form>
        {active && (
          <ConfirmButton
            className="btn btn--ghost btn--sm u-push"
            description={`Delete the watchlist ${active.name} and all ${active.tickers.length} of its tickers`}
            confirmLabel="Delete list?"
            onConfirm={() => {
              deleteWatchlist(active.id)
              setActiveId(null)
            }}
          >
            Delete list
          </ConfirmButton>
        )}
      </div>

      {active && (
        <>
          {/* Add ticker */}
          <form
            onSubmit={(event) => {
              event.preventDefault()
              const symbol = addSymbol.trim().toUpperCase()
              if (symbol) {
                // Adding already succeeded silently — the row appeared and
                // nothing said so, which is indistinguishable from a slow
                // network when the list is long enough to scroll.
                const duplicate = active.tickers.includes(symbol)
                addTicker(active.id, symbol)
                setAddSymbol('')
                notify(
                  duplicate ? `${symbol} is already in ${active.name}` : `${symbol} added to ${active.name}`,
                  duplicate ? 'warn' : 'ok',
                )
              }
            }}
            style={{ display: 'flex', gap: 8, alignItems: 'center' }}
          >
            <label htmlFor="add-ticker" className="visually-hidden">Add ticker to {active.name}</label>
            <input
              id="add-ticker"
              className="input mono"
              style={{ maxWidth: 180, height: 32, fontSize: '0.8125rem', letterSpacing: '0.06em' }}
              placeholder="Add ticker…"
              maxLength={8}
              value={addSymbol}
              onChange={(event) => setAddSymbol(event.target.value.toUpperCase().replace(/[^A-Z.^-]/g, ''))}
            />
            <button type="submit" className="btn btn--secondary btn--sm" disabled={!addSymbol.trim()}>
              Add to {active.name}
            </button>
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
              {quotesFetchedAt && !loadingQuotes && (
                <span className="u-meta">
                  Quotes updated {timeAgo(quotesFetchedAt)}
                </span>
              )}
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setQuotesReload((key) => key + 1)}
                disabled={loadingQuotes || active.tickers.length === 0}
              >
                {loadingQuotes ? 'Refreshing…' : 'Refresh quotes'}
              </button>
            </span>
          </form>

          {active.tickers.length === 0 ? (
            <EmptyState
              title={`${active.name} is empty`}
              description="Add tickers above. Analyzed tickers rank by verdict and confidence; the rest by weekly momentum."
            />
          ) : (
            <div className="panel" style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ minWidth: 960 }}>
                <caption className="visually-hidden">
                  {active.name} watchlist, ranked by verdict then confidence
                </caption>
                <thead>
                  <tr>
                    <SortHeader col="ticker" sort={sort} onSort={setSort}>Ticker</SortHeader>
                    <SortHeader col="price" sort={sort} onSort={setSort} num>Price</SortHeader>
                    <SortHeader col="change_1d" sort={sort} onSort={setSort} num>1D</SortHeader>
                    <SortHeader col="change_1w" sort={sort} onSort={setSort} num>1W</SortHeader>
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
                        <span className="u-row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                        <CompanyMark ticker={ticker} />
                        <Link
                          href={`/company/${ticker}`}
                          className="mono"
                          style={{ fontWeight: 600, textDecoration: 'none', color: 'var(--text)' }}
                        >
                          {ticker}
                        </Link>
                        </span>
                      </td>
                      <td className="num">
                        {loadingQuotes && !quote ? <Skeleton width={54} height={14} /> :
                          quote?.price !== undefined ? quote.price : <span style={{ color: 'var(--faint)' }}>—</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}><ChangeCell value={quote?.change_1d} /></td>
                      <td style={{ textAlign: 'right' }}><ChangeCell value={quote?.change_1w} /></td>
                      <td>
                        {latest ? (
                          <span className={`badge ${verdictTone(latest.verdict)}`} style={{ height: 19, fontSize: '0.625rem' }}>
                            {latest.verdict}
                          </span>
                        ) : (
                          <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>not analyzed</span>
                        )}
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
                        {previous ? previous.verdict : '—'}
                      </td>
                      <td>
                        {diff && (diff.verdictChanged || Math.abs(diff.confidenceDelta) >= 3) ? (
                          <Tooltip label={`Why ${ticker} changed`}>
                            <p style={{ margin: 0, fontWeight: 550, color: 'var(--text)' }}>
                              Confidence {diff.confidenceDelta >= 0 ? '+' : ''}{diff.confidenceDelta}pp
                              {diff.scoreDelta !== null && ` · composite ${diff.scoreDelta >= 0 ? '+' : ''}${diff.scoreDelta.toFixed(3)}`}
                            </p>
                            {diff.topDrivers.length > 0 && (
                              <ul style={{ listStyle: 'none', margin: '6px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {diff.topDrivers.slice(0, 3).map((driver) => (
                                  <li key={driver.name} className="u-meta">
                                    {FACTOR_LABELS[driver.name] ?? driver.name}: {driver.before.toFixed(2)} → {driver.after.toFixed(2)}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </Tooltip>
                        ) : null}
                        {diff?.verdictChanged ? (
                          <span
                            className={`badge ${diff.direction === 'upgrade' ? 'badge--pos' : 'badge--neg'}`}
                            style={{ height: 19, fontSize: '0.625rem', marginLeft: 4 }}
                          >
                            {diff.direction === 'upgrade' ? '▲ upgrade' : '▼ downgrade'}
                          </span>
                        ) : latest ? (
                          <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>unchanged</span>
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
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        <Link
                          href={`/company/${ticker}`}
                          className="btn btn--ghost btn--xs"
                          style={{ textDecoration: 'none' }}
                        >
                          Explain
                        </Link>
                        <ConfirmButton
                          className="btn btn--ghost btn--xs reveal"
                          description={`Remove ${ticker} from ${active.name}`}
                          confirmLabel="Remove?"
                          onConfirm={() => {
                            removeTicker(active.id, ticker)
                            notify(`${ticker} removed from ${active.name}`)
                          }}
                        >
                          ✕
                        </ConfirmButton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="u-meta">
            Verdict columns come from your own analysis runs, stored in this browser (see “Where is
            this stored?” below) — run Analyze on a ticker to populate them. Quotes via the provider
            fallback chain.
          </p>

          <PositionsPanel />

          <StorageStatus />
        </>
      )}
    </div>
  )
}
