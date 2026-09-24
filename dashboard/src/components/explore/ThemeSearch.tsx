'use client'

import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

import { StateBlock } from '@/components/system'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import EntityMark from '@/components/visual/EntityMark'
import { sourceDomain } from '@/lib/identity'
import { type ScreenAnswer, screenQuery } from '@/lib/security'

function host(url: string | null): string | null {
  if (!url) return null
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return null }
}

/**
 * Search the universe by company or by theme. The answer says how the query
 * was read — a lookup resolved against symbol databases, or a theme matched
 * in ranked web sources and then validated — and every thematic result keeps
 * the source that mentioned it. Runs only when a query is submitted.
 */
export default function ThemeSearch({ companyHref }: { companyHref: (symbol: string) => string }) {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const q = (params.get('q') ?? '').trim()
  const [draft, setDraft] = useState(q)
  const [answer, setAnswer] = useState<{ for: string; data?: ScreenAnswer; error?: string } | null>(null)

  useEffect(() => {
    if (!q) return undefined
    const ctrl = new AbortController()
    screenQuery(q, ctrl.signal)
      .then((data) => setAnswer({ for: q, data }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setAnswer({ for: q, error: e.message }) })
    return () => ctrl.abort()
  }, [q])

  const current = answer?.for === q ? answer : null

  return (
    <section className="sys-panel xs" aria-label="Search by company or theme">
      <form
        className="xs-form"
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          const next = draft.trim()
          const sp = new URLSearchParams(params.toString())
          if (next) sp.set('q', next)
          else sp.delete('q')
          router.replace(`${pathname}${sp.toString() ? `?${sp}` : ''}`, { scroll: false })
        }}
      >
        <label htmlFor="xs-q" className="visually-hidden">Company, ticker or theme</label>
        <input
          id="xs-q"
          className="sys-input xs-input"
          placeholder="A company, a ticker, or a theme such as “grid-scale batteries”"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="sys-btn sys-btn--primary" disabled={!draft.trim()}>Search</button>
      </form>

      {!q ? null : !current ? (
        <StateBlock state="waking" title={`Reading “${q}”`} detail="resolving symbols, or searching sources for a theme" />
      ) : current.error ? (
        <StateBlock state="unavailable" title="The search did not complete" detail="The screen service did not answer. The rankings below are unaffected." />
      ) : current.data ? (
        <div className="xs-answer">
          <p className="xs-read">
            <span className="ev-tag" data-tone="info">{current.data.mode === 'lookup' ? 'company lookup' : 'theme'}</span>
            {current.data.mode === 'lookup'
              ? `Read as a company or ticker lookup — ${current.data.results.length} match${current.data.results.length === 1 ? '' : 'es'}.`
              : `Read as a theme — ${current.data.results.length} listed compan${current.data.results.length === 1 ? 'y' : 'ies'} named in ranked sources, each validated against symbol databases.`}
            {current.data.note ? <span className="xs-note"> {current.data.note}</span> : null}
          </p>
          {current.data.results.length ? (
            <ul className="xs-results">
              {current.data.results.slice(0, 12).map((r) => {
                const h = host(r.url)
                return (
                  <li key={r.symbol}>
                    <CompanyIdentity symbol={r.symbol} name={r.name} size="sm" href={companyHref(r.symbol)} />
                    {r.snippet ? <p className="xs-snippet">{r.snippet}</p> : <span />}
                    <span className="xs-src">
                      {h && r.url ? (
                        <a href={r.url} target="_blank" rel="noopener noreferrer">
                          <EntityMark domain={sourceDomain(h, r.url)} label={h} size={14} />{h}
                        </a>
                      ) : null}
                      <Link className="sys-btn sys-btn--ghost" href={companyHref(r.symbol)}>Research</Link>
                    </span>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="cw-muted">No listed company matched this query.</p>
          )}
          {current.data.suggestions.length ? (
            <p className="xs-suggest">
              Did you mean{' '}
              {current.data.suggestions.slice(0, 5).map((s, i) => (
                <span key={s.symbol}>
                  {i ? ', ' : ''}
                  <Link href={companyHref(s.symbol)}>{s.symbol}{s.name ? ` (${s.name})` : ''}</Link>
                </span>
              ))}
              ?
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
