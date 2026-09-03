'use client'

/**
 * Type a ticker. Open a company. From anywhere.
 *
 * The terminal had lost this. Every security surface ran through the research
 * panel, so when that dataset went stale the way in went with it — and a
 * financial terminal without effortless ticker discovery is not a financial
 * terminal.
 *
 * It sits in the shell rather than inside a workspace, because the workflow it
 * serves is the first thing a user does and should never require arriving
 * somewhere first.
 *
 * Deliberate behaviours:
 *
 * **Cancellation, not just debouncing.** A search box fires a request per
 * keystroke. Without cancelling the previous one, the answer to "AAP" can
 * arrive after the answer to "AAPL" and overwrite it — the results flicker
 * back to something the reader has already finished typing past.
 *
 * **The provider's order is not our order.** "AAP" must reach AAPL before
 * Apple Hospitality REIT. Ranking is ours; the rows are theirs.
 *
 * **Recents are symbols, not research rows.** They survive the research
 * dataset entirely, which is the point.
 */

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'

import { Status } from '@/components/system'
import {
  rankSecurities, searchSecurities, type SecurityIdentity,
} from '@/lib/security'
import {
  emptySnapshot, recentSnapshot, rememberSymbol, subscribeSymbols,
} from '@/lib/symbols'

/**
 * A settled answer, tagged with the query it answers.
 *
 * Held rather than a status flag so the display state can be derived at
 * render: an answer whose tag no longer matches what is in the box is simply
 * not current, and the box reads as searching again. That removes every
 * synchronous state write from the effect, and it makes the stale-answer case
 * — "AAP" landing after "AAPL" — structurally impossible rather than merely
 * cancelled.
 */
interface Settled {
  for: string
  rows?: SecurityIdentity[]
  error?: string
}

export default function SecuritySearch() {
  const router = useRouter()
  const [query, setQuery] = useState('')
  const [settled, setSettled] = useState<Settled | null>(null)
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  // Subscribed rather than copied into state on mount: a write anywhere — here
  // or in another tab — updates every reader without an effect.
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const box = useRef<HTMLInputElement>(null)
  const abort = useRef<AbortController | null>(null)

  /* One in-flight request. Each keystroke cancels the last, so a slow answer
     to a shorter prefix can never land on top of a newer one. */
  useEffect(() => {
    const q = query.trim()
    abort.current?.abort()
    if (!q) return

    const controller = new AbortController()
    abort.current = controller
    const timer = window.setTimeout(() => {
      searchSecurities(q, controller.signal)
        .then((rows) => setSettled({ for: q, rows: rankSecurities(q, rows) }))
        .catch((e: Error) => {
          if (e.name === 'AbortError') return
          setSettled({ for: q, error: e.message })
        })
    }, 160)

    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query])

  const openSymbol = useCallback((symbol: string) => {
    rememberSymbol(symbol)
    setQuery('')
    setSettled(null)
    setOpen(false)
    router.push(`/terminal/security?symbol=${encodeURIComponent(symbol)}`)
  }, [router])

  // `/` focuses the box from anywhere, unless the reader is already typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
        || (el as HTMLElement | null)?.isContentEditable
      if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        box.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /* Derived, never stored. An answer tagged with a different query is not
     current, so the box reads as searching rather than showing a result the
     reader has typed past. */
  const q = query.trim()
  const current = settled?.for === q ? settled : null
  const rows = current?.rows ?? []
  const showing = open && (q.length > 0 || recent.length > 0)

  return (
    <div className="sec-search" role="search">
      <input
        ref={box}
        className="sec-search__input"
        type="search"
        value={query}
        placeholder="Search securities, tickers, companies"
        aria-label="Search securities"
        autoComplete="off"
        spellCheck={false}
        onFocus={() => setOpen(true)}
        onBlur={() => { window.setTimeout(() => setOpen(false), 140) }}
        onChange={(e) => { setQuery(e.target.value); setCursor(0); setOpen(true) }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') { setQuery(''); setOpen(false); box.current?.blur(); return }
          const list = query.trim() ? rows.map((r) => r.symbol) : recent
          if (!list.length) return
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(list.length - 1, c + 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)) }
          if (e.key === 'Enter') {
            e.preventDefault()
            // A query that is already a ticker opens directly, even where the
            // symbol database has not answered yet.
            openSymbol(list[cursor] ?? query.trim().toUpperCase())
          }
        }}
      />
      <kbd className="sec-search__hint">/</kbd>

      {showing ? (
        <div className="sec-search__panel" role="listbox" aria-label="Securities">
          {q ? (
            current === null ? (
              <div className="sec-search__note">searching the symbol database…</div>
            ) : current.error ? (
              <div className="sec-search__note">
                <Status state="unavailable" label="SEARCH UNAVAILABLE" />
                <span>{current.error}. Press Enter to open {q.toUpperCase()} anyway.</span>
              </div>
            ) : rows.length ? (
              rows.slice(0, 8).map((s, i) => (
                <button
                  key={s.symbol}
                  type="button"
                  role="option"
                  aria-selected={i === cursor}
                  className={`sec-search__row${i === cursor ? ' is-active' : ''}`}
                  onMouseDown={(e) => { e.preventDefault(); openSymbol(s.symbol) }}
                  onMouseEnter={() => setCursor(i)}
                >
                  <span className="sec-search__sym">{s.symbol}</span>
                  <span className="sec-search__name">{s.name ?? '—'}</span>
                  {s.via ? <span className="sec-search__via">{s.via}</span> : null}
                </button>
              ))
            ) : (
              <div className="sec-search__note">
                No security matches “{q}”. Press Enter to try it as a
                ticker anyway — the symbol database does not cover every venue.
              </div>
            )
          ) : (
            <>
              <div className="sec-search__head">Recent</div>
              {recent.slice(0, 8).map((sym, i) => (
                <button
                  key={sym}
                  type="button"
                  role="option"
                  aria-selected={i === cursor}
                  className={`sec-search__row${i === cursor ? ' is-active' : ''}`}
                  onMouseDown={(e) => { e.preventDefault(); openSymbol(sym) }}
                  onMouseEnter={() => setCursor(i)}
                >
                  <span className="sec-search__sym">{sym}</span>
                </button>
              ))}
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}
