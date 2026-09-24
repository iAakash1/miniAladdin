'use client'

import Link from 'next/link'
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

import { profileRef } from './profileRef'
import Icon from '@/components/shell/Icon'
import { Inspectable } from '@/components/system'
import CompanyMark from '@/components/ui/CompanyMark'
import { SectorGlyph, sectorKey } from '@/components/visual/SectorMark'
import { saveReport } from '@/lib/persistence'
import { format } from '@/lib/quantity'
import { quoteState, type Quote } from '@/lib/security'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'
import { venueLabel } from '@/lib/text'
import type { CompanyProfile } from '@/lib/types'
import {
  addTicker, listsContaining, removeTicker, unwatchSymbol, useWatchlists, useWatchlistsStatus, watchSymbol,
} from '@/lib/watchlists'

/** Quote changes arrive in percent units already (−0.80 means −0.80%), and a
 *  session move keeps two decimals: a −0.05% day is not a −0.1% day. */
function signedPct(v: number | null | undefined, digits = 2): string {
  const f = format(v ?? null, 'percent', { digits, signed: true })
  return f.absent ? '—' : `${f.text === '-0.00' ? '0.00' : f.text}%`
}

function WatchControl({ symbol }: { symbol: string }) {
  const lists = useWatchlists()
  const status = useWatchlistsStatus()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const menu = useRef<HTMLDivElement>(null)
  const holding = listsContaining(symbol, lists)
  const watched = holding.length > 0
  const unavailable = status === 'unauthenticated' || status === 'error'

  useEffect(() => {
    if (!open) return undefined
    const close = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    window.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); window.removeEventListener('keydown', esc) }
  }, [open])

  const toggle = async () => {
    if (lists.length > 1) { setOpen((v) => !v); return }
    if (watched) { unwatchSymbol(symbol); return }
    setBusy(true)
    await watchSymbol(symbol)
    setBusy(false)
  }

  return (
    <div className="cw-watch" ref={menu}>
      <button
        type="button"
        className={`sys-btn${watched ? ' is-active' : ''}`}
        onClick={() => void toggle()}
        disabled={busy || unavailable || status === 'loading'}
        aria-haspopup={lists.length > 1 ? 'menu' : undefined}
        aria-expanded={lists.length > 1 ? open : undefined}
        title={unavailable ? 'Watchlists are unavailable right now' : watched ? `On ${holding.map((l) => l.name).join(', ')}` : 'Add to a watchlist'}
      >
        <Icon name="star" size={13} />
        {watched ? 'Watching' : 'Watch'}
      </button>
      {open ? (
        <div className="cw-menu" role="menu" aria-label="Watchlists">
          {lists.map((l) => {
            const on = l.tickers.includes(symbol)
            return (
              <button
                key={l.id}
                type="button"
                role="menuitemcheckbox"
                aria-checked={on}
                className="cw-menu__item"
                onClick={() => (on ? removeTicker(l.id, symbol) : addTicker(l.id, symbol))}
              >
                <span className="cw-menu__check" aria-hidden>{on ? <Icon name="check" size={12} /> : null}</span>
                <span>{l.name}</span>
                <span className="cw-menu__count">{l.tickers.length}</span>
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function SaveControl({ historyId }: { historyId: string }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')
  return (
    <button
      type="button"
      className={`sys-btn${state === 'saved' ? ' is-active' : ''}`}
      disabled={state === 'saving' || state === 'saved'}
      onClick={async () => {
        setState('saving')
        setState((await saveReport(historyId)) ? 'saved' : 'failed')
      }}
      title="Keep this research run in your Research log"
    >
      {state === 'saved' ? 'Saved' : state === 'saving' ? 'Saving…' : state === 'failed' ? 'Retry save' : 'Save report'}
    </button>
  )
}

function compactMoney(v: number | null | undefined, currency = 'USD'): string | null {
  if (v === null || v === undefined || !Number.isFinite(v) || v <= 0) return null
  const unit = v >= 1e12 ? [1e12, 'T'] : v >= 1e9 ? [1e9, 'B'] : v >= 1e6 ? [1e6, 'M'] : [1, '']
  const sym = currency === 'USD' ? '$' : ''
  return `${sym}${(v / (unit[0] as number)).toFixed(v >= 1e12 ? 2 : 1)}${unit[1]}${sym ? '' : ` ${currency}`}`
}

/** Profile facts that were actually reported; an absent field is left out, not zeroed. */
function profileFacts(p: CompanyProfile | null | undefined): Array<[string, string, string]> {
  if (!p) return []
  const facts: Array<[string, string, string | null]> = [
    ['Market cap', 'market_cap', compactMoney(p.market_cap, p.currency || 'USD')],
    ['Employees', 'employees', p.employees && p.employees > 0 ? p.employees.toLocaleString('en-US') : null],
    ['Country', 'country', p.country || null],
    ['Listed', 'ipo_date', p.ipo_date ? p.ipo_date.slice(0, 4) : null],
    ['CEO', 'ceo', p.ceo || null],
  ]
  return facts.filter((f): f is [string, string, string] => Boolean(f[2]))
}

function siteLabel(p: CompanyProfile | null | undefined): { href: string; label: string } | null {
  const raw = p?.website?.trim()
  if (!raw) return null
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`)
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null
    return { href: url.toString(), label: url.hostname.replace(/^www\./, '') }
  } catch {
    return null
  }
}

export default function CompanyHeader({
  symbol, name, exchange, sector, industry, profile, quote, quoteError, historyId, onPaper, paperAvailable,
}: {
  symbol: string
  name: string | null
  exchange: string | null
  sector: string | null
  industry: string | null
  /** From the research run; absent until it lands. */
  profile?: CompanyProfile | null
  quote: Quote | null
  quoteError: string | null
  historyId: string | null
  onPaper: () => void
  paperAvailable: boolean
}) {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const against = recent.find((s) => s !== symbol)
  const state = quoteState(quote)
  const venue = venueLabel(exchange)
  const meta = [venue, sector, industry].filter(Boolean)
  const c1 = quote?.change_1d ?? null
  const c1w = quote?.change_1w ?? null
  const facts = profileFacts(profile)
  const site = siteLabel(profile)

  return (
    <header className="cw-head" data-sector={sector ? sectorKey(sector) : undefined}>
      {sector ? <SectorGlyph sector={sector} size={220} className="cw-head__art" /> : null}
      <div className="cw-id">
        <CompanyMark ticker={symbol} name={name} size={52} />
        <div className="cw-id__text">
          <div className="cw-id__line">
            <h1 className="cw-ticker">{symbol}</h1>
            <span className="cw-name">{name ?? '\u00a0'}</span>
          </div>
          <div className="cw-meta">
            {meta.length ? meta.map((m, i) => <span key={`${m}-${i}`}>{m}</span>) : <span>Identity loading…</span>}
            {site ? (
              <span>
                <a className="cw-site" href={site.href} target="_blank" rel="noreferrer">
                  {site.label}<Icon name="external" size={11} />
                </a>
              </span>
            ) : null}
          </div>
          {facts.length ? (
            <dl className="cw-facts">
              {facts.map(([k, field, v]) => {
                const ref = profile ? profileRef(profile, field, k, v) : null
                return <div key={k} className="cw-fact"><dt>{k}</dt><dd>{ref ? <Inspectable refValue={ref}>{v}</Inspectable> : v}</dd></div>
              })}
            </dl>
          ) : null}
        </div>
      </div>

      <div className="cw-quote" aria-live="polite">
        <div className="cw-price">
          {quote?.price !== null && quote?.price !== undefined
            ? <>${format(quote.price, 'currency').text}</>
            : <span className="sys-null">—</span>}
        </div>
        <div className="cw-change">
          <span className={c1 === null ? 'sys-null' : c1 >= 0 ? 'sys-pos' : 'sys-neg'}>{signedPct(quote?.change_1d, 2)}</span>
          <span className="cw-change__k">1D</span>
          <span className={c1w === null ? 'sys-null' : c1w >= 0 ? 'sys-pos' : 'sys-neg'}>{signedPct(quote?.change_1w, 2)}</span>
          <span className="cw-change__k">1W</span>
        </div>
        <div className="cw-asof">
          {quote ? (
            <>
              <span className="dot" data-tone={state === 'stale' ? 'warn' : 'muted'} aria-hidden />
              {quote.price_basis ?? 'last price'}
              {quote.as_of ? ` · ${quote.as_of.slice(0, 16).replace('T', ' ')}` : ''}
              {quote.source ? ` · ${quote.source}` : ''}
              {state === 'stale' ? ' · stale' : ''}
            </>
          ) : quoteError ? 'quote unavailable' : 'reading quote…'}
        </div>
      </div>

      <div className="cw-actions">
        <WatchControl symbol={symbol} />
        {historyId ? <SaveControl historyId={historyId} /> : null}
        {against ? (
          <Link className="sys-btn" href={`/terminal/compare?a=${encodeURIComponent(symbol)}&b=${encodeURIComponent(against)}`}>
            Compare with {against}
          </Link>
        ) : null}
        {paperAvailable ? (
          <button type="button" className="sys-btn" onClick={onPaper}>Paper trade</button>
        ) : null}
      </div>
    </header>
  )
}
