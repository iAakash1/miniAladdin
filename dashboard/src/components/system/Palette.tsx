'use client'

/**
 * Search and command, in one surface.
 *
 * Typing a ticker or a company name looks it up; a phrase ("AI chip
 * suppliers") runs the web-grounded theme search and says so. Commands for
 * the company in view, every destination, and indexed research objects are
 * ranked alongside. ⌘K or `/` opens it from anywhere.
 */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { usePathname, useRouter } from 'next/navigation'

import Icon, { type IconName } from '@/components/shell/Icon'
import CompanyMark from '@/components/ui/CompanyMark'
import { Status, type ResearchState } from './index'
import { ALL_DESTINATIONS, ALL_VIEWS } from '@/lib/destinations'
import { companyFromPath, companyHref, contextCommands } from '@/lib/context-commands'
import { buildRows, selectableRows, type PaletteSection } from '@/lib/palette-rows'
import { loadCatalogue } from '@/lib/research/catalogue'
import { recordVisit, usePinnedObjects, useRecentObjects } from '@/lib/research/history'
import { KIND_ORDER, KINDS, href as objectHref, score, type ObjectKind, type ResearchObject } from '@/lib/research/objects'
import { describeQuery, matchesStructure, parseQuery } from '@/lib/research/query'
import { localMatches } from '@/lib/search'
import { looksLikeSymbol, screenQuery, type ScreenAnswer } from '@/lib/security'
import { emptySnapshot, recentSnapshot, rememberSymbol, subscribeSymbols } from '@/lib/symbols'
import { listsContaining, unwatchSymbol, useWatchedSymbols, useWatchlists, watchSymbol } from '@/lib/watchlists'

const OPEN_EVENT = 'omni:palette'

/** Open the palette from anywhere, optionally pre-filled. */
export function openPalette(query = ''): void {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { query } }))
}

const DENSITY_KEY = 'ma.density'

export function applyStoredDensity(): void {
  try {
    const d = window.localStorage.getItem(DENSITY_KEY)
    if (d) document.documentElement.setAttribute('data-density', d)
  } catch {
    /* storage unavailable; the default density applies */
  }
}

function cycleDensity(): void {
  const order = ['compact', 'default', 'comfortable']
  const current = document.documentElement.getAttribute('data-density') ?? 'default'
  const next = order[(order.indexOf(current) + 1) % order.length]
  document.documentElement.setAttribute('data-density', next)
  try { window.localStorage.setItem(DENSITY_KEY, next) } catch { /* ignore */ }
}

const STATE_MAP: Record<string, ResearchState> = {
  live: 'live', recorded: 'recorded', stale: 'stale', waking: 'waking',
  unavailable: 'unavailable', blocked: 'blocked', experimental: 'experimental',
  production_candidate: 'candidate', validated: 'candidate',
  production: 'production', retired: 'unavailable',
}

type Item =
  | { type: 'company'; symbol: string; name: string | null; detail: string | null }
  | { type: 'command'; id: string; label: string; note?: string; hint?: string; icon: IconName; run: () => void }
  | { type: 'object'; object: ResearchObject }

interface Settled {
  for: string
  answer?: ScreenAnswer
  error?: string
}

const itemKey = (item: Item): string =>
  item.type === 'company' ? item.symbol : item.type === 'command' ? item.id : `${item.object.kind}:${item.object.id}`

export default function Palette() {
  const router = useRouter()
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursorFor, setCursorFor] = useState({ query: '', index: 0 })
  const [objects, setObjects] = useState<ResearchObject[]>([])
  const [settled, setSettled] = useState<Settled | null>(null)
  const recentObjects = useRecentObjects()
  const pinned = usePinnedObjects()
  const recentSymbols = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const watched = useWatchedSymbols()
  const lists = useWatchlists()
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Global keys: ⌘K toggles; `/` opens when the reader is not typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((v) => !v)
        return
      }
      const el = document.activeElement as HTMLElement | null
      const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
      if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        setOpen(true)
      }
    }
    const onOpen = (e: Event) => {
      const q = (e as CustomEvent<{ query?: string }>).detail?.query ?? ''
      setQuery(q)
      setOpen(true)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener(OPEN_EVENT, onOpen)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener(OPEN_EVENT, onOpen)
    }
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const t = window.setTimeout(() => inputRef.current?.focus(), 0)
    loadCatalogue()
      .then((c) => setObjects(c.objects))
      .catch(() => { /* the catalogue reports its own failures */ })
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => { window.clearTimeout(t); window.removeEventListener('keydown', onKey) }
  }, [open])

  // One in-flight screen request; each keystroke cancels the last.
  const q = query.trim()
  useEffect(() => {
    if (!open || !q) return undefined
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      screenQuery(q, controller.signal)
        .then((answer) => setSettled({ for: q, answer }))
        .catch((e: Error) => {
          if (e.name !== 'AbortError') setSettled({ for: q, error: e.message })
        })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [q, open])

  const current = settled?.for === q ? settled : null
  const symbolHere = companyFromPath(pathname)

  const commands: Array<Extract<Item, { type: 'command' }>> = useMemo(() => {
    const contextual = contextCommands({
      pathname,
      params: {},
      recent: recentSymbols,
      watched: symbolHere ? listsContaining(symbolHere, lists).length > 0 : false,
    }).map((c) => ({
      type: 'command' as const,
      id: `ctx:${c.id}`,
      label: c.label,
      note: c.note,
      icon: (c.act ? 'star' : 'chevronRight') as IconName,
      run: c.href
        ? () => router.push(c.href as string)
        : () => {
          if (!c.symbol) return
          if (c.act === 'unwatch') unwatchSymbol(c.symbol)
          else void watchSymbol(c.symbol)
        },
    }))
    return [
      ...contextual,
      {
        type: 'command' as const, id: 'density', label: 'Cycle information density',
        hint: 'compact · default · comfortable', icon: 'panel' as IconName, run: cycleDensity,
      },
    ]
  }, [pathname, recentSymbols, symbolHere, lists, router])

  const navigation: Array<Extract<Item, { type: 'command' }>> = useMemo(() => ALL_VIEWS.map((v) => ({
    type: 'command' as const,
    id: `go:${v.href}`,
    label: v.label === v.destination.label ? v.label : `${v.destination.label} · ${v.label}`,
    note: v.answers,
    hint: v.href === v.destination.href ? `g ${v.destination.key}` : undefined,
    icon: v.destination.icon,
    run: () => router.push(v.href),
  })), [router])

  const sections: PaletteSection<Item>[] = useMemo(() => {
    const companyItem = (symbol: string, name: string | null, detail: string | null): Item =>
      ({ type: 'company', symbol, name, detail })

    if (!q) {
      return [
        {
          key: 'recent-companies', label: 'Recent companies', itemKey,
          items: recentSymbols.slice(0, 5).map((s) => companyItem(s, null, watched.includes(s) ? 'on a watchlist' : null)),
        },
        { key: 'actions', label: 'Actions', itemKey, items: commands.filter((c) => c.id.startsWith('ctx:')) },
        {
          key: 'goto', label: 'Go to', itemKey,
          items: navigation.filter((n) => ALL_DESTINATIONS.some((d) => `go:${d.href}` === n.id)),
        },
        { key: 'pinned', label: 'Pinned', itemKey, items: pinned.slice(0, 4).map((o) => ({ type: 'object' as const, object: o })) },
        { key: 'recent-objects', label: 'Recent research', itemKey, items: recentObjects.slice(0, 5).map((o) => ({ type: 'object' as const, object: o })) },
      ]
    }

    // Companies: the backend answer when it has landed, otherwise what this
    // browser already knows so the list is never empty while typing.
    const out: PaletteSection<Item>[] = []
    const answer = current?.answer
    if (answer) {
      const rows = answer.results.slice(0, 8).map((r) => companyItem(
        r.symbol, r.name, answer.mode === 'thematic' ? (r.via ?? null) : null,
      ))
      out.push({
        key: 'companies',
        label: answer.mode === 'thematic' ? 'Theme results' : 'Companies',
        note: answer.mode === 'thematic' ? 'tickers named in ranked web sources, validated against symbol databases' : undefined,
        itemKey,
        items: rows,
      })
      if (!rows.length && answer.suggestions.length) {
        out.push({
          key: 'suggestions', label: 'Did you mean', itemKey,
          items: answer.suggestions.slice(0, 5).map((s) => companyItem(s.symbol, s.name, null)),
        })
      }
    } else {
      const local = localMatches(q, recentSymbols, watched).map((m) => companyItem(m.symbol, null, m.context))
      out.push({ key: 'companies', label: 'Companies', note: current?.error ? 'search unavailable' : 'searching…', itemKey, items: local })
    }
    if (looksLikeSymbol(q) && !(answer?.results ?? []).some((r) => r.symbol === q.toUpperCase())) {
      out.push({
        key: 'open-ticker', label: 'Open directly', itemKey,
        items: [companyItem(q.toUpperCase(), null, 'open as a ticker')],
      })
    }

    const rank = <T extends { label: string; note?: string }>(items: T[], limit: number) => items
      .map((c) => ({ c, s: Math.max(score(q, c.label), score(q, c.note ?? '') * 0.3) }))
      .filter((r) => r.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, limit)
      .map((r) => r.c)

    out.push({ key: 'actions', label: 'Actions', itemKey, items: rank(commands, 5) })
    out.push({ key: 'goto', label: 'Go to', itemKey, items: rank(navigation, 5) })
    if (q.split(/\s+/).length >= 2 || !looksLikeSymbol(q)) {
      out.push({
        key: 'screen', label: 'Screen', itemKey,
        items: [{
          type: 'command', id: 'screen', icon: 'screen',
          label: `Screen for “${q}”`, note: 'lookup or web-grounded theme search, with sources',
          run: () => router.push(`/explore?q=${encodeURIComponent(q)}`),
        }],
      })
    }

    // Research objects: a query may name a kind or a state ("blocked
    // models"); what is left is matched against names.
    const states = new Set(objects.map((o) => o.state).filter((s): s is string => Boolean(s)))
    const parsed = parseQuery(q, states)
    const eligible = objects.filter((o) => matchesStructure(o, parsed))
    const ranked = parsed.structural
      ? eligible.slice(0, 24)
      : eligible
        .map((o) => ({ o, s: Math.max(score(parsed.text, o.label), score(parsed.text, o.detail ?? '') * 0.4) }))
        .filter((r) => r.s > 0)
        .sort((a, b) => b.s - a.s)
        .slice(0, 24)
        .map((r) => r.o)
    const grouped = new Map<ObjectKind, ResearchObject[]>()
    for (const o of ranked) {
      if (o.kind === 'security') continue
      const list = grouped.get(o.kind) ?? []
      if (list.length < 4) list.push(o)
      grouped.set(o.kind, list)
    }
    const described = describeQuery(parsed)
    for (const kind of KIND_ORDER) {
      const items = grouped.get(kind)
      if (items?.length) {
        out.push({
          key: `obj-${kind}`, label: KINDS[kind].plural, note: described ?? undefined, itemKey,
          items: items.map((o) => ({ type: 'object' as const, object: o })),
        })
      }
    }
    return out
  }, [q, current, recentSymbols, watched, commands, navigation, objects, pinned, recentObjects, router])

  const rows = useMemo(() => buildRows(sections), [sections])
  const selectable = useMemo(() => selectableRows(rows), [rows])
  const cursor = cursorFor.query === query ? Math.min(cursorFor.index, Math.max(selectable.length - 1, 0)) : 0
  const setCursor = (next: number) => setCursorFor({ query, index: next })

  useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  if (!open) return null

  const close = () => { setOpen(false); setQuery('') }

  const activate = (index: number) => {
    const row = selectable.find((r) => r.index === index)
    if (!row) return
    const item = row.value
    if (item.type === 'company') {
      rememberSymbol(item.symbol)
      router.push(companyHref(item.symbol))
    } else if (item.type === 'command') {
      item.run()
    } else {
      recordVisit(item.object)
      router.push(objectHref(item.object))
    }
    close()
  }

  const optionId = (index: number) => `pal-opt-${index}`

  return (
    <div
      className="pal-backdrop"
      onMouseDown={(e) => { if (e.target === e.currentTarget) close() }}
    >
      <div className="pal" role="dialog" aria-modal="true" aria-label="Search and commands">
        <div className="pal-input-row">
          <Icon name="search" size={16} className="pal-input-icon" />
          <input
            ref={inputRef}
            className="pal-input"
            value={query}
            placeholder="Search companies, tickers, themes, or type a command"
            role="combobox"
            aria-expanded="true"
            aria-controls="pal-list"
            aria-activedescendant={selectable.length ? optionId(cursor) : undefined}
            aria-label="Search"
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(Math.min(cursor + 1, selectable.length - 1)) }
              if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(Math.max(cursor - 1, 0)) }
              if (e.key === 'Enter') { e.preventDefault(); activate(cursor) }
            }}
          />
          <kbd className="pal-esc">esc</kbd>
        </div>

        <div className="pal-body" id="pal-list" role="listbox" aria-label="Results" ref={listRef}>
          {rows.map((row) => {
            if (row.type === 'header') {
              return (
                <div key={row.key} className="pal-section" role="presentation">
                  <span>{row.label}</span>
                  {row.note ? <span className="pal-section__note">{row.note}</span> : null}
                </div>
              )
            }
            const active = cursor === row.index
            const item = row.value
            return (
              <div
                key={row.key}
                id={optionId(row.index)}
                role="option"
                aria-selected={active}
                data-active={active}
                className="pal-row"
                onMouseMove={() => { if (!active) setCursor(row.index) }}
                onMouseDown={(e) => { e.preventDefault(); activate(row.index) }}
              >
                {item.type === 'company' ? (
                  <>
                    <CompanyMark ticker={item.symbol} name={item.name} size={20} />
                    <span className="pal-sym">{item.symbol}</span>
                    <span className="pal-label">{item.name ?? ''}</span>
                    {item.detail ? <span className="pal-note">{item.detail}</span> : null}
                    <span className="pal-kind">Company</span>
                  </>
                ) : item.type === 'command' ? (
                  <>
                    <Icon name={item.icon} size={14} className="pal-icon" />
                    <span className="pal-label">{item.label}</span>
                    {item.note ? <span className="pal-note">{item.note}</span> : null}
                    {item.hint ? <kbd className="pal-hint">{item.hint}</kbd> : null}
                  </>
                ) : (
                  <>
                    <span className="pal-glyph" aria-hidden>{KINDS[item.object.kind].glyph}</span>
                    <span className="pal-label">{item.object.label}</span>
                    {item.object.detail ? <span className="pal-note">{item.object.detail}</span> : null}
                    {item.object.state && STATE_MAP[item.object.state]
                      ? <Status state={STATE_MAP[item.object.state]} label={item.object.state} />
                      : null}
                    <span className="pal-kind">{KINDS[item.object.kind].workspace}</span>
                  </>
                )}
              </div>
            )
          })}

          {q && !selectable.length ? (
            <p className="pal-empty">
              {current ? `Nothing matches “${q}”.` : 'Searching…'}
            </p>
          ) : null}
        </div>

        <div className="pal-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> move <kbd>↵</kbd> open <kbd>esc</kbd> close</span>
          <span>{current?.answer ? (current.answer.mode === 'thematic' ? 'theme search' : 'symbol lookup') : null}</span>
        </div>
      </div>
    </div>
  )
}
