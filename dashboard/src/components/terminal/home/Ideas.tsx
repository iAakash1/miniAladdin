'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { StateBlock } from '@/components/system'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import SectorMark from '@/components/visual/SectorMark'
import { readerError } from '@/lib/failure'
import { type ExploreRow, type RecommendationsResponse, freshness } from '@/lib/explore'
import { readResource } from '@/lib/resource'

type View = 'ranked' | 'conviction' | 'performance'

const VIEWS: Array<{ key: View; label: string; note: string }> = [
  { key: 'ranked', label: 'Top ranked', note: 'signal strength weighted by confidence, risk and evidence completeness' },
  { key: 'conviction', label: 'High conviction', note: 'every conviction condition met at once — often empty by design' },
  { key: 'performance', label: 'Performance leaders', note: 'risk-adjusted history against the benchmark, not the current view' },
]

function Signal({ value }: { value: string | null }) {
  if (!value) return <span className="sys-null">—</span>
  const tone = /buy/i.test(value) ? 'pos' : /sell/i.test(value) ? 'neg' : 'muted'
  return <span className="sig-verdict sig-verdict--sm" data-tone={tone}>{value}</span>
}

function num(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(digits)
}

export default function Ideas() {
  const [view, setView] = useState<View>('ranked')
  const [answer, setAnswer] = useState<{ d?: RecommendationsResponse; error?: string } | null>(null)

  useEffect(() => {
    let alive = true
    readResource<RecommendationsResponse>('/api/recommendations?limit=8', 'snapshot')
      .then((d) => { if (alive) setAnswer({ d }) })
      .catch((e: Error) => { if (alive) setAnswer({ error: e.message }) })
    return () => { alive = false }
  }, [])

  const d = answer?.d
  const rows: ExploreRow[] = !d ? [] : view === 'ranked' ? d.top_ranked
    : view === 'conviction' ? d.high_conviction : d.performance_leaders
  const note = VIEWS.find((v) => v.key === view)?.note

  return (
    <section className="sys-panel home-ideas" aria-label="Ideas from the ranked universe">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Ranked universe</h2>
          <span className="sys-panel-sub">
            {d ? `${d.eligible_count} of ${d.count} eligible${d.generated_at ? ` · ${freshness(d.generated_at) ?? ''}` : ''}` : null}
          </span>
        </div>
        <Link className="cw-more" href="/explore">Open screener</Link>
      </header>
      <div className="sys-tabs home-ideas__tabs" role="tablist" aria-label="Idea lists">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            role="tab"
            className="sys-tab"
            aria-selected={view === v.key}
            onClick={() => setView(v.key)}
          >
            {v.label}
            {d ? <span className="sys-tab__count">{(v.key === 'ranked' ? d.top_ranked : v.key === 'conviction' ? d.high_conviction : d.performance_leaders).length}</span> : null}
          </button>
        ))}
      </div>
      {answer === null ? (
        <StateBlock state="waking" title="Reading the ranked universe" />
      ) : answer.error ? (
        <StateBlock state="unavailable" title="Rankings unavailable" detail={`${readerError(answer.error)}.`} />
      ) : rows.length ? (
        <div className="sys-scroll-x">
          <table className="sys-table">
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col"><span className="visually-hidden">Sector</span></th>
                <th scope="col">Signal</th>
                <th scope="col" className="num">{view === 'performance' ? 'Excess 6m' : 'Rank score'}</th>
                <th scope="col" className="num">Confidence</th>
                <th scope="col">Risk</th>
                <th scope="col" className="num">Price</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 8).map((r) => (
                <tr key={r.symbol}>
                  <td>
                    <CompanyIdentity symbol={r.symbol} name={r.company_name} size="sm" href={`/company/${encodeURIComponent(r.symbol)}`} />
                  </td>
                  <td className="home-ideas__sector"><SectorMark sector={r.sector} size={18} /></td>
                  <td><Signal value={r.model_signal} /></td>
                  <td className="num">
                    {view === 'performance'
                      ? (r.excess_return_6m === null ? '—' : `${r.excess_return_6m >= 0 ? '+' : ''}${(r.excess_return_6m * 100).toFixed(1)}%`)
                      : (
                        <span className="home-rank">
                          <span className="home-rank__bar" aria-hidden><span style={{ width: `${Math.max(0, Math.min(100, r.overall_rank ?? 0))}%` }} /></span>
                          {num(r.overall_rank, 1)}
                        </span>
                      )}
                  </td>
                  <td className="num">{num(r.confidence)}</td>
                  <td className="home-dim">{r.risk_level ? r.risk_level.toLowerCase() : '—'}</td>
                  <td className="num">{r.price === null ? '—' : r.price.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="cw-muted cw-pad">
          {view === 'conviction'
            ? `No security meets every conviction condition right now${d?.near_conviction.length ? ` — the closest is ${d.near_conviction[0].symbol}, missing ${d.near_conviction[0].conviction_blocked_by.length}` : ''}.`
            : 'Nothing to list in this view.'}
        </p>
      )}
      <footer className="sys-panel-foot"><span>{note}</span></footer>
    </section>
  )
}
