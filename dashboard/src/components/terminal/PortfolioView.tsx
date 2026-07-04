'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { diffSnapshots, useAllHistory } from '@/lib/history'
import {
  SUGGESTED_LISTS,
  type Watchlist,
  addTicker,
  createWatchlist,
  deleteWatchlist,
  removeTicker,
  useWatchlists,
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

function ChangeCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span style={{ color: 'var(--faint)' }}>—</span>
  return (
    <span className="num" style={{ color: value >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
      {value >= 0 ? '+' : ''}
      {value}%
    </span>
  )
}

export default function PortfolioView() {
  const lists = useWatchlists()
  const history = useAllHistory()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [addSymbol, setAddSymbol] = useState('')
  const [quotes, setQuotes] = useState<Record<string, Quote>>({})
  const [loadingQuotes, setLoadingQuotes] = useState(false)
  const [quotesReload, setQuotesReload] = useState(0)

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
        if (alive) setQuotes(json.quotes ?? {})
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

  /* ── no lists yet: suggestions ── */
  if (lists.length === 0) {
    return (
      <div>
        <EmptyState
          title="No watchlists yet"
          description="Create your first list, or start from a suggestion — everything is stored in this browser."
        />
        <div className="terminal-grid-four" style={{ maxWidth: 880, margin: '0 auto' }}>
          {SUGGESTED_LISTS.map((suggestion) => (
            <button
              key={suggestion.name}
              type="button"
              className="panel"
              onClick={() => createWatchlist(suggestion.name, suggestion.tickers)}
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
              createWatchlist(newName)
              setNewName('')
            }
          }}
          style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 20 }}
        >
          <label htmlFor="new-list" className="visually-hidden">New watchlist name</label>
          <input
            id="new-list"
            className="input"
            style={{ maxWidth: 220, height: 36 }}
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
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
              <span className="num" style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>
                {list.tickers.length}
              </span>
            </button>
          ))}
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (newName.trim()) {
              const created = createWatchlist(newName)
              setActiveId(created.id)
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
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            style={{ marginLeft: 'auto', color: 'var(--neg)' }}
            onClick={() => {
              deleteWatchlist(active.id)
              setActiveId(null)
            }}
          >
            Delete list
          </button>
        )}
      </div>

      {active && (
        <>
          {/* Add ticker */}
          <form
            onSubmit={(event) => {
              event.preventDefault()
              if (addSymbol.trim()) {
                addTicker(active.id, addSymbol)
                setAddSymbol('')
              }
            }}
            style={{ display: 'flex', gap: 8 }}
          >
            <label htmlFor="add-ticker" className="visually-hidden">Add ticker to {active.name}</label>
            <input
              id="add-ticker"
              className="input mono"
              style={{ maxWidth: 180, height: 36, letterSpacing: '0.06em' }}
              placeholder="Add ticker…"
              maxLength={8}
              value={addSymbol}
              onChange={(event) => setAddSymbol(event.target.value.toUpperCase().replace(/[^A-Z.^-]/g, ''))}
            />
            <button type="submit" className="btn btn--secondary btn--sm" disabled={!addSymbol.trim()}>
              Add to {active.name}
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              style={{ marginLeft: 'auto' }}
              onClick={() => setQuotesReload((key) => key + 1)}
              disabled={loadingQuotes || active.tickers.length === 0}
            >
              {loadingQuotes ? 'Refreshing…' : 'Refresh quotes'}
            </button>
          </form>

          {active.tickers.length === 0 ? (
            <EmptyState
              title={`${active.name} is empty`}
              description="Add tickers above. Analyzed tickers rank by verdict and confidence; the rest by weekly momentum."
            />
          ) : (
            <div className="panel" style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ minWidth: 820 }}>
                <caption className="visually-hidden">
                  {active.name} watchlist, ranked by verdict then confidence
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Ticker</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Price</th>
                    <th scope="col" style={{ textAlign: 'right' }}>1D</th>
                    <th scope="col" style={{ textAlign: 'right' }}>1W</th>
                    <th scope="col">Verdict</th>
                    <th scope="col">Signal change</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Conf</th>
                    <th scope="col">Risk</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Momentum</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Gate</th>
                    <th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ ticker, quote, latest, diff }) => (
                    <tr key={ticker}>
                      <td>
                        <Link
                          href={`/terminal/analyze?ticker=${ticker}`}
                          className="mono"
                          style={{ fontWeight: 600, textDecoration: 'none', color: 'var(--text)' }}
                        >
                          {ticker}
                        </Link>
                      </td>
                      <td className="num" style={{ textAlign: 'right' }}>
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
                      <td>
                        {diff?.verdictChanged ? (
                          <span
                            className={`badge ${diff.direction === 'upgrade' ? 'badge--pos' : 'badge--neg'}`}
                            style={{ height: 19, fontSize: '0.625rem' }}
                            title={`Confidence ${diff.confidenceDelta >= 0 ? '+' : ''}${diff.confidenceDelta}pp`}
                          >
                            {diff.direction === 'upgrade' ? '▲ upgrade' : '▼ downgrade'}
                          </span>
                        ) : latest ? (
                          <span style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>unchanged</span>
                        ) : null}
                      </td>
                      <td className="num" style={{ textAlign: 'right' }}>
                        {latest ? `${latest.confidence}%` : '—'}
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                        {latest?.riskLevel?.toLowerCase() ?? '—'}
                      </td>
                      <td className="num" style={{ textAlign: 'right' }}>
                        {latest?.momentumScore !== null && latest?.momentumScore !== undefined
                          ? latest.momentumScore.toFixed(2) : '—'}
                      </td>
                      <td className="num" style={{ textAlign: 'right' }}>
                        {latest?.macroGate !== null && latest?.macroGate !== undefined
                          ? latest.macroGate.toFixed(2) : '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          aria-label={`Remove ${ticker} from ${active.name}`}
                          onClick={() => removeTicker(active.id, ticker)}
                          style={{ height: 24, padding: '0 8px', color: 'var(--faint)' }}
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
            Verdict columns come from your own analysis runs (stored in this browser); run
            Analyze on a ticker to populate them. Quotes via the provider fallback chain.
          </p>
        </>
      )}
    </div>
  )
}
