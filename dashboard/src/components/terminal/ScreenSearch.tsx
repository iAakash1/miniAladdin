'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import Skeleton from '@/components/ui/Skeleton'
import { useAllHistory } from '@/lib/history'
import { highlightSegments, localMatches } from '@/lib/search'
import { useWatchlists } from '@/lib/watchlists'

interface ScreenResult {
  symbol: string
  name: string
  via: string
  snippet: string | null
  url: string | null
}

interface ScreenResponse {
  query: string
  mode: 'lookup' | 'thematic'
  results: ScreenResult[]
  suggestions: ScreenResult[]
  note: string
}

interface ScreenSearchProps {
  /** Header placement is narrower than the full-width dashboard slot. */
  maxWidth?: number
}

/**
 * Phase 7 search: tickers, company names, or natural language ("AI
 * companies", "largest banks"). Search-fix pass additions:
 *   - Portfolio/watchlist/history matches surface instantly, client-side,
 *     with no network round trip (see lib/search.ts) — this alone fixes
 *     the reported "NVDA -> Nothing Found" case whenever NVDA is already
 *     being tracked, regardless of backend vendor health.
 *   - The server-side waterfall (src/services/screen_service.py) now
 *     retries the other strategy on a miss in either direction and never
 *     fully dead-ends; when it still comes up empty, `suggestions` offers
 *     fuzzy "did you mean" alternatives.
 *   - Arrow-key navigation and matched-substring highlighting.
 * Mounted once, globally, in TerminalHeader — available on every
 * /terminal/* page, not just Market.
 */
export default function ScreenSearch({ maxWidth = 520 }: ScreenSearchProps) {
  const router = useRouter()
  const lists = useWatchlists()
  const history = useAllHistory()

  const [value, setValue] = useState('')
  const [query, setQuery] = useState('') // debounced, drives fetch
  const [data, setData] = useState<ScreenResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  const local = useMemo(() => localMatches(value, lists, history), [value, lists, history])

  useEffect(() => {
    if (!query) {
      queueMicrotask(() => {
        setData(null)
        setLoading(false)
        setActiveIndex(-1)
      })
      return undefined
    }
    const controller = new AbortController()
    let alive = true
    queueMicrotask(() => {
      if (alive) {
        setLoading(true)
        setFailed(false)
      }
    })
    fetch(`/api/screen?q=${encodeURIComponent(query)}`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((json: ScreenResponse) => {
        if (alive) {
          setData(json)
          setActiveIndex(-1)
        }
      })
      .catch((error: unknown) => {
        if (alive && (error as Error).name !== 'AbortError') setFailed(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [query])

  /* Close on outside click / Escape */
  useEffect(() => {
    function onPointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const onChange = (next: string) => {
    setValue(next)
    setOpen(true)
    setActiveIndex(-1)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setQuery(next.trim()), 350)
  }

  const serverRows = data && data.results.length > 0 ? data.results : []
  const suggestionRows = data && data.results.length === 0 ? (data.suggestions ?? []) : []
  const flatSymbols = [
    ...local.map((match) => match.symbol),
    ...serverRows.map((row) => row.symbol),
    ...suggestionRows.map((row) => row.symbol),
  ]
  const showPanel = open && (loading || failed || Boolean(data) || local.length > 0)

  const onSelect = () => setOpen(false)

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!showPanel || flatSymbols.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => Math.min(index + 1, flatSymbols.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault()
      setOpen(false)
      router.push(`/company/${flatSymbols[activeIndex]}`)
    }
  }

  return (
    <div ref={rootRef} style={{ position: 'relative', maxWidth, width: '100%' }}>
      <label htmlFor="screen-q" className="visually-hidden">
        Search tickers, companies or themes
      </label>
      <input
        id="screen-q"
        className="input"
        type="search"
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="screen-results"
        aria-activedescendant={activeIndex >= 0 ? `screen-hit-${activeIndex}` : undefined}
        autoComplete="off"
        placeholder='Search anything — "NVDA", "largest banks", "AI companies"…'
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />

      {showPanel && (
        <div
          id="screen-results"
          role="listbox"
          aria-label="Search results"
          className="panel fade-in"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            right: 0,
            zIndex: 60,
            maxHeight: 420,
            overflowY: 'auto',
            background: 'var(--surface-3)',
            boxShadow: 'var(--shadow-dialog)',
            padding: '6px',
          }}
        >
          {local.length > 0 && (
            <>
              <p className="label" style={{ padding: '6px 10px 4px' }}>In your portfolio</p>
              {local.map((match, index) => (
                <ResultRow
                  key={`local-${match.symbol}`}
                  id={`screen-hit-${index}`}
                  active={index === activeIndex}
                  symbol={match.symbol}
                  name={match.context}
                  via={null}
                  snippet={null}
                  query={value}
                  onSelect={onSelect}
                />
              ))}
            </>
          )}

          {loading && (
            <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }} aria-label="Searching">
              <Skeleton height={34} />
              <Skeleton height={34} />
              <Skeleton height={34} />
            </div>
          )}

          {failed && !loading && (
            <p style={{ padding: 14, fontSize: '0.8125rem', color: 'var(--muted)' }}>
              Search is unreachable right now — try again shortly.
            </p>
          )}

          {!loading && !failed && data && serverRows.length > 0 && (
            <>
              {serverRows.map((result, i) => (
                <ResultRow
                  key={result.symbol}
                  id={`screen-hit-${local.length + i}`}
                  active={local.length + i === activeIndex}
                  symbol={result.symbol}
                  name={result.name}
                  via={result.via}
                  snippet={result.snippet}
                  query={value}
                  onSelect={onSelect}
                />
              ))}
              <p style={{ padding: '8px 10px 6px', fontSize: '0.625rem', color: 'var(--faint)', borderTop: '1px solid var(--line)', marginTop: 4 }}>
                {data.note}
              </p>
            </>
          )}

          {!loading && !failed && data && serverRows.length === 0 && (
            <>
              <p style={{ padding: '14px 14px 6px', fontSize: '0.8125rem', color: 'var(--muted)' }}>
                Nothing found for “{data.query}”{local.length > 0 ? ' beyond your portfolio' : ''}.
              </p>
              {suggestionRows.length > 0 && (
                <>
                  <p className="label" style={{ padding: '4px 10px' }}>Did you mean</p>
                  {suggestionRows.map((result, i) => (
                    <ResultRow
                      key={`sugg-${result.symbol}`}
                      id={`screen-hit-${local.length + i}`}
                      active={local.length + i === activeIndex}
                      symbol={result.symbol}
                      name={result.name}
                      via={result.via}
                      snippet={null}
                      query={value}
                      onSelect={onSelect}
                    />
                  ))}
                </>
              )}
              {suggestionRows.length === 0 && local.length === 0 && (
                <p style={{ padding: '0 14px 14px', fontSize: '0.75rem', color: 'var(--faint)' }}>
                  Try a ticker, a company name, or a broader theme.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function Highlighted({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlightSegments(text, query).map((segment, i) =>
        segment.match ? <mark key={i}>{segment.text}</mark> : <span key={i}>{segment.text}</span>,
      )}
    </>
  )
}

function ResultRow({
  id, active, symbol, name, via, snippet, query, onSelect,
}: {
  id: string
  active: boolean
  symbol: string
  name: string
  via: string | null
  snippet: string | null
  query: string
  onSelect: () => void
}) {
  return (
    <Link
      id={id}
      role="option"
      aria-selected={active}
      href={`/company/${symbol}`}
      onClick={onSelect}
      style={{ display: 'block', padding: '9px 10px', borderRadius: 'var(--r-md)', textDecoration: 'none' }}
      className={`screen-hit${active ? ' screen-hit--active' : ''}`}
    >
      <span style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
        <span className="mono" style={{ fontWeight: 600, color: 'var(--text)', width: 62, flexShrink: 0 }}>
          <Highlighted text={symbol} query={query} />
        </span>
        <span style={{ fontSize: '0.8125rem', color: 'var(--muted)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <Highlighted text={name} query={query} />
        </span>
        {via && <span style={{ fontSize: '0.625rem', color: 'var(--faint)', flexShrink: 0 }}>{via}</span>}
      </span>
      {snippet && (
        <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 3, paddingLeft: 72 }}>
          {snippet}
        </span>
      )}
    </Link>
  )
}
