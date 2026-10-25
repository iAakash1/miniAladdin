'use client'

/**
 * The tracker: the account's watchlists, with live data on every row.
 *
 * Lists, their order, notes and tags are stored on the server under the
 * signed-in account. Prices come from `/api/tracker`: each row shows the
 * provider that answered, the quote's own timestamp and a freshness class, so a
 * delayed or stale price is never mistaken for a live one, and a missing quote
 * says so (with the last close shown as a close). Period returns are on daily
 * closes and are blank where the history does not reach.
 *
 * A row's research verdict is context with its confidence and evidence grade.
 * The paper action opens a ticket — prefilled, never submitted.
 */

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import AlertEditor from '@/components/terminal/alerts/AlertEditor'
import Drawer from '@/components/shell/Drawer'
import { EmptyLine, StateBlock, Status, Value } from '@/components/system'
import SymbolSpark from '@/components/visual/SymbolSpark'
import { alertCounts, useAlerts } from '@/lib/alerts'
import { signalCaution, useLatestResearch } from '@/lib/research-context'
import {
  FRESHNESS_LABEL, PERIODS, filterTracker, periodValue, sortTracker, useTracker,
  type Period, type SortInput, type TrackerRow, type TrackerSort,
} from '@/lib/tracker'
import {
  addTicker, createWatchlist, deleteWatchlist, itemsOf, moveTicker, removeTicker, renameWatchlist,
  setDefaultWatchlist, shiftTicker, shiftWatchlist, updateItem, useWatchlists, useWatchlistsStatus,
  type Watchlist,
} from '@/lib/watchlists'

const PAGE = 25
const SORTS: Array<{ key: TrackerSort; label: string }> = [
  { key: 'manual', label: 'My order' },
  { key: 'symbol', label: 'Symbol' },
  { key: 'change_pct', label: 'Change %' },
  { key: 'change', label: 'Change' },
  { key: 'perf', label: 'Period return' },
  { key: 'updated', label: 'Last update' },
  { key: 'alerts', label: 'Active alerts' },
  { key: 'signal', label: 'Signal confidence' },
]

export default function TrackerWorkspace() {
  const lists = useWatchlists()
  const status = useWatchlistsStatus()
  const params = useSearchParams()
  const router = useRouter()
  const selectedId = params.get('list')
  const current = lists.find((l) => l.id === selectedId) ?? lists.find((l) => l.isDefault) ?? lists[0] ?? null

  const select = (id: string) => router.replace(`/terminal/watchlists?list=${encodeURIComponent(id)}`, { scroll: false })

  if (status === 'idle' || status === 'loading') {
    if (!lists.length) return <StateBlock state="waking" title="Loading your watchlists" />
  }
  if (status === 'unauthenticated') return <StateBlock state="blocked" title="Sign in to use watchlists" detail="Lists are stored with your account." />
  if (status === 'error' && !lists.length) {
    return <StateBlock state="unavailable" title="Watchlists are unavailable right now" detail="The persistence service did not answer. Your lists are stored on the server and are unaffected." />
  }

  return (
    <div className="trk">
      <ListNav lists={lists} currentId={current?.id ?? null} onSelect={select} />
      {current ? <ListView key={current.id} list={current} lists={lists} /> : <NoLists />}
    </div>
  )
}

function NoLists() {
  return (
    <EmptyLine label="Watchlists">
      No watchlists yet. Create one on the left — for example Core Holdings, Earnings Watch or High-Risk Ideas.
    </EmptyLine>
  )
}

/* ── list navigation ─────────────────────────────────────────────────────── */

function ListNav({ lists, currentId, onSelect }: { lists: Watchlist[]; currentId: string | null; onSelect: (id: string) => void }) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const create = async () => {
    const clean = name.trim()
    if (!clean) return
    const created = await createWatchlist(clean)
    if (created) { setName(''); setError(null); onSelect(created.id) } else setError('The list was not created (limit reached or service unavailable).')
  }
  return (
    <nav className="trk-nav" aria-label="Watchlists">
      <ol>
        {lists.map((l, i) => (
          <li key={l.id} data-current={l.id === currentId ? 'true' : undefined}>
            <button type="button" className="trk-nav__item" aria-current={l.id === currentId ? 'page' : undefined} onClick={() => onSelect(l.id)}>
              <span className="trk-nav__name">{l.name}</span>
              <span className="trk-nav__meta">{l.tickers.length}{l.isDefault ? ' · default' : ''}</span>
            </button>
            <span className="trk-nav__move">
              <button type="button" className="sys-btn sys-btn--micro" aria-label={`Move ${l.name} up`} disabled={i === 0} onClick={() => shiftWatchlist(l.id, -1)}>↑</button>
              <button type="button" className="sys-btn sys-btn--micro" aria-label={`Move ${l.name} down`} disabled={i === lists.length - 1} onClick={() => shiftWatchlist(l.id, 1)}>↓</button>
            </span>
          </li>
        ))}
      </ol>
      <form className="trk-nav__new" onSubmit={(e) => { e.preventDefault(); void create() }}>
        <label className="visually-hidden" htmlFor="trk-new-list">New watchlist name</label>
        <input id="trk-new-list" className="sys-input" maxLength={40} placeholder="New list name" value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className="sys-btn" disabled={!name.trim()}>Create</button>
      </form>
      {error ? <p className="trk-error" role="alert">{error}</p> : null}
    </nav>
  )
}

/* ── one list ────────────────────────────────────────────────────────────── */

function ListView({ list, lists }: { list: Watchlist; lists: Watchlist[] }) {
  const items = itemsOf(list)
  const symbols = items.map((i) => i.ticker)
  const { rows, at, loading, error, refresh } = useTracker(symbols)
  const alerts = useAlerts()
  const counts = useMemo(() => alertCounts(alerts), [alerts])
  const research = useLatestResearch(symbols)

  const [period, setPeriod] = useState<Period>('1M')
  const [sort, setSort] = useState<TrackerSort>('manual')
  const [descending, setDescending] = useState(true)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [adding, setAdding] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [alertFor, setAlertFor] = useState<string | null>(null)

  const notes = useMemo(() => Object.fromEntries(items.map((i) => [i.ticker, { note: i.note, tags: i.tags }])), [items])
  const sortable: SortInput[] = items.map((i, position) => ({
    ticker: i.ticker, row: rows[i.ticker], alerts: counts[i.ticker] ?? 0, position,
    signalConfidence: research[i.ticker]?.confidence ?? null,
  }))
  const ordered = sortTracker(filterTracker(sortable, query, notes), sort, period, descending)
  const pages = Math.max(1, Math.ceil(ordered.length / PAGE))
  const visible = ordered.slice(page * PAGE, page * PAGE + PAGE)
  useEffect(() => { if (page >= pages) setPage(0) }, [page, pages])

  const add = () => {
    const symbol = adding.trim().toUpperCase().replace(/[^A-Z.^-]/g, '')
    if (!symbol) return
    addTicker(list.id, symbol)
    setAdding('')
  }

  return (
    <section className="trk-main" aria-label={`Watchlist ${list.name}`}>
      <header className="trk-head">
        {renaming !== null ? (
          <form onSubmit={(e) => { e.preventDefault(); renameWatchlist(list.id, renaming); setRenaming(null) }} className="trk-rename">
            <label className="visually-hidden" htmlFor="trk-rename">List name</label>
            <input id="trk-rename" className="sys-input" maxLength={40} value={renaming} onChange={(e) => setRenaming(e.target.value)} autoFocus />
            <button type="submit" className="sys-btn">Save</button>
            <button type="button" className="sys-btn" onClick={() => setRenaming(null)}>Cancel</button>
          </form>
        ) : (
          <h2 className="trk-title">{list.name}{list.isDefault ? <span className="trk-default">default</span> : null}</h2>
        )}
        <div className="trk-head__acts">
          <button type="button" className="sys-btn sys-btn--xs" onClick={() => setRenaming(list.name)}>Rename</button>
          {!list.isDefault ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => setDefaultWatchlist(list.id)}>Make default</button> : null}
          {confirmDelete ? (
            <>
              <button type="button" className="sys-btn sys-btn--xs" onClick={() => { deleteWatchlist(list.id); setConfirmDelete(false) }}>Delete {list.tickers.length} symbols and the list</button>
              <button type="button" className="sys-btn sys-btn--xs" onClick={() => setConfirmDelete(false)}>Keep</button>
            </>
          ) : <button type="button" className="sys-btn sys-btn--xs" onClick={() => setConfirmDelete(true)}>Delete…</button>}
        </div>
      </header>

      <div className="trk-tools">
        <form className="trk-add" onSubmit={(e) => { e.preventDefault(); add() }}>
          <label className="visually-hidden" htmlFor="trk-add">Add a symbol</label>
          <input id="trk-add" className="sys-input" placeholder="Add symbol, e.g. MSFT" value={adding} onChange={(e) => setAdding(e.target.value)} autoComplete="off" />
          <button type="submit" className="sys-btn sys-btn--primary" disabled={!adding.trim()}>Add</button>
        </form>
        <div className="sys-seg" role="group" aria-label="Performance period">
          {PERIODS.map((p) => (
            <button key={p} type="button" className={`sys-btn${p === period ? ' is-active' : ''}`} aria-pressed={p === period} onClick={() => setPeriod(p)}>{p}</button>
          ))}
        </div>
        <label className="trk-sort">
          <span className="visually-hidden">Sort by</span>
          <select className="sys-input" value={sort} onChange={(e) => setSort(e.target.value as TrackerSort)}>
            {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
        {sort !== 'manual' && sort !== 'symbol' ? (
          <button type="button" className="sys-btn" onClick={() => setDescending(!descending)} aria-label={descending ? 'Highest first' : 'Lowest first'}>{descending ? 'High → low' : 'Low → high'}</button>
        ) : null}
        <label className="trk-filter">
          <span className="visually-hidden">Filter symbols, notes or tags</span>
          <input className="sys-input" placeholder="Filter" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <span className="sys-meta trk-updated" aria-live="polite">
          {loading ? 'updating…' : at ? `prices read ${at.toLocaleTimeString()}` : ''}
        </span>
        <button type="button" className="sys-btn" onClick={refresh} disabled={loading}>Refresh</button>
      </div>

      {error ? <p className="trk-error" role="alert">Market data did not answer ({error}). The list itself is unaffected; showing the last prices read, if any.</p> : null}

      {!items.length ? (
        <EmptyLine label={list.name}>This list is empty. Add a symbol above, or press Watch on any company page.</EmptyLine>
      ) : !ordered.length ? (
        <EmptyLine label="Filter">No symbol, note or tag matches “{query}”.</EmptyLine>
      ) : (
        <div className="sys-scroll-x">
          <table className="sys-table sys-table--compact trk-table">
            <caption className="visually-hidden">{list.name}: prices, freshness, period return and research context</caption>
            <thead>
              <tr>
                <th scope="col">Symbol</th>
                <th scope="col" className="num">Price</th>
                <th scope="col" className="num">Change</th>
                <th scope="col" className="num">{period}</th>
                <th scope="col">Trend (3M)</th>
                <th scope="col">Quote</th>
                <th scope="col">Research</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <Row
                  key={s.ticker} list={list} lists={lists} ticker={s.ticker} row={rows[s.ticker]} period={period}
                  alerts={s.alerts} research={research[s.ticker]} note={notes[s.ticker]}
                  manual={sort === 'manual' && !query} onAlert={() => setAlertFor(s.ticker)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 ? (
        <nav className="trk-pages" aria-label="Pages">
          <button type="button" className="sys-btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="sys-meta">page {page + 1} of {pages} · {ordered.length} symbols</span>
          <button type="button" className="sys-btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button>
        </nav>
      ) : null}

      <p className="sys-meta trk-foot">
        Prices refresh every minute while this page is open; the server caches quotes for a minute and daily history for five,
        so this is not tick-by-tick streaming. Period returns use daily closes through the last close. Quotes in USD.
      </p>

      <Drawer open={alertFor !== null} onClose={() => setAlertFor(null)} title={alertFor ? `Alert · ${alertFor}` : 'Alert'} meta="Evaluated on the server's schedule">
        {alertFor ? <AlertEditor ticker={alertFor} lastPrice={rows[alertFor]?.price ?? null} /> : null}
      </Drawer>
    </section>
  )
}

function Row({
  list, lists, ticker, row, period, alerts, research, note, manual, onAlert,
}: {
  list: Watchlist; lists: Watchlist[]; ticker: string; row?: TrackerRow; period: Period; alerts: number
  research?: ReturnType<typeof useLatestResearch>[string]; note?: { note: string | null; tags: string[] }
  manual: boolean; onAlert: () => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [moving, setMoving] = useState(false)
  const caution = signalCaution(research)
  const perf = periodValue(row, period)
  const others = lists.filter((l) => l.id !== list.id)

  return (
    <tr>
      <th scope="row" className="trk-sym">
        <Link href={`/company/${encodeURIComponent(ticker)}`} className="trk-sym__link">{ticker}</Link>
        {note?.tags.length ? <span className="trk-tags">{note.tags.map((t) => <span key={t} className="trk-tag">{t}</span>)}</span> : null}
        {editing !== null ? (
          <form className="trk-note-edit" onSubmit={(e) => { e.preventDefault(); updateItem(list.id, ticker, { note: editing.trim() || null }); setEditing(null) }}>
            <label className="visually-hidden" htmlFor={`note-${ticker}`}>Note for {ticker}</label>
            <input id={`note-${ticker}`} className="sys-input" maxLength={500} value={editing} onChange={(e) => setEditing(e.target.value)} autoFocus />
            <button type="submit" className="sys-btn sys-btn--micro">save</button>
          </form>
        ) : note?.note ? <span className="trk-note">{note.note}</span> : null}
      </th>
      <td className="num">
        {row?.price != null ? <Value value={row.price} kind="currency" />
          : row?.last_close != null ? <span title="No current quote; this is the last daily close">close <Value value={row.last_close} kind="currency" /></span>
            : <span className="sys-null">{row ? statusText(row) : '…'}</span>}
      </td>
      <td className="num">
        {row?.change_pct != null ? (
          <span className="trk-chg"><Value value={row.change} kind="currency" signed tone /> <Value value={row.change_pct} kind="percent" digits={2} signed tone /></span>
        ) : <span className="sys-null">—</span>}
      </td>
      <td className="num">{perf != null ? <Value value={perf} kind="percent" digits={2} signed tone /> : <span className="sys-null" title="Not enough daily history for this period">—</span>}</td>
      <td>{row?.spark && row.spark.length > 1 ? <SymbolSpark values={row.spark} /> : <span className="sys-null">—</span>}</td>
      <td className="trk-quote">
        {row?.freshness ? <span className="trk-fresh" data-fresh={row.freshness}>{FRESHNESS_LABEL[row.freshness]}</span> : null}
        <span className="sys-meta">{row?.source ?? ''}{row?.as_of ? ` · ${shortTime(row.as_of)}` : ''}</span>
        {alerts ? <span className="trk-alerts" title={`${alerts} active alert${alerts === 1 ? '' : 's'}`}>◆ {alerts}</span> : null}
      </td>
      <td className="trk-research">
        {research?.verdict ? (
          <>
            <span>{research.verdict}</span>
            <span className="sys-meta"> {research.confidence ?? '—'}/100</span>
            {caution ? <Status state="warning" label={research.evidence_grade === 'INSUFFICIENT' ? 'INSUFFICIENT EVIDENCE' : 'QUALIFIED'} title={caution} /> : null}
          </>
        ) : <span className="sys-null">not researched</span>}
      </td>
      <td className="trk-acts">
        <button type="button" className="sys-btn sys-btn--xs" onClick={onAlert}>Alert…</button>
        <Link className="sys-btn sys-btn--xs" href={`/terminal/paper?ticket=${encodeURIComponent(ticker)}&origin=watchlist`}>Paper order…</Link>
        <button type="button" className="sys-btn sys-btn--xs" onClick={() => setEditing(note?.note ?? '')}>Note</button>
        {moving ? (
          <select className="sys-input trk-move" aria-label={`Move ${ticker} to`} defaultValue="" onChange={(e) => { if (e.target.value) void moveTicker(list.id, e.target.value, ticker); setMoving(false) }}>
            <option value="" disabled>Move to…</option>
            {others.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        ) : others.length ? <button type="button" className="sys-btn sys-btn--xs" onClick={() => setMoving(true)}>Move…</button> : null}
        {manual ? (
          <>
            <button type="button" className="sys-btn sys-btn--micro" aria-label={`Move ${ticker} up`} onClick={() => shiftTicker(list.id, ticker, -1)}>↑</button>
            <button type="button" className="sys-btn sys-btn--micro" aria-label={`Move ${ticker} down`} onClick={() => shiftTicker(list.id, ticker, 1)}>↓</button>
          </>
        ) : null}
        <button type="button" className="sys-btn sys-btn--xs" aria-label={`Remove ${ticker} from ${list.name}`} onClick={() => removeTicker(list.id, ticker)}>Remove</button>
      </td>
    </tr>
  )
}

function statusText(row: TrackerRow): string {
  switch (row.quote_status) {
    case 'invalid': return 'not a valid symbol'
    case 'no_data': return 'no provider has this symbol'
    case 'unavailable': return 'providers unavailable'
    case 'error': return 'quote failed'
    default: return 'no quote'
  }
}

function shortTime(iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso)
  if (Number.isNaN(d.getTime())) return iso
  return iso.length === 10 ? iso : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
