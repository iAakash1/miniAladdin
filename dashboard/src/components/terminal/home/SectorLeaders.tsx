'use client'

/**
 * Sector leaders: the engine's best-ranked eligible name in each sector.
 *
 * A reading of the same deterministic ordering as the ranked universe, one
 * sector at a time — so a reader sees ideas across the market rather than
 * eight names from whichever sector is leading this month. Nothing here is
 * chosen by a model's prose: the rank, signal, confidence and risk are the
 * engine's, and the two reasons are the factors that contributed most for and
 * against. A sector's best name keeps its own signal, Hold included.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { StateBlock } from '@/components/system'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import SectorMark from '@/components/visual/SectorMark'
import { readerError } from '@/lib/failure'
import { type ExploreRow, type RecommendationsResponse, freshness } from '@/lib/explore'
import { fmtPrice } from '@/lib/format'
import { FACTOR_LABELS } from '@/lib/history'
import { readResource } from '@/lib/resource'

/** "r63 (momentum)" → "63-day momentum"; the family is shown separately. */
function factor(reason: string | null): { label: string; family: string | null } | null {
  if (!reason) return null
  const m = /^(.*?)\s*\(([^)]+)\)\s*$/.exec(reason)
  const key = (m ? m[1] : reason).trim()
  return { label: FACTOR_LABELS[key] ?? key.replace(/_/g, ' '), family: m ? m[2] : null }
}

function tone(signal: string | null): 'pos' | 'neg' | 'muted' {
  if (!signal) return 'muted'
  return /buy/i.test(signal) ? 'pos' : /sell/i.test(signal) ? 'neg' : 'muted'
}

function Tile({ r }: { r: ExploreRow }) {
  const plus = factor(r.top_positive)
  const minus = factor(r.top_caution)
  const rank = r.overall_rank
  return (
    <Link href={`/company/${encodeURIComponent(r.symbol)}`} className="sl-tile" data-stale={r.stale ? '' : undefined}>
      <span className="sl-tile__head">
        <SectorMark sector={r.sector} size={14} />
        <span className="sl-tile__sector">{r.sector}</span>
      </span>
      <CompanyIdentity symbol={r.symbol} name={r.company_name} size="sm" />
      <span className="sl-tile__sig">
        <span className="sig-verdict sig-verdict--sm" data-tone={tone(r.model_signal)}>{r.model_signal ?? '—'}</span>
        <span className="sl-rank" title="Rank score: signal strength weighted by confidence, risk and evidence completeness">
          <span className="sl-rank__bar" aria-hidden><span style={{ width: `${Math.max(0, Math.min(100, rank ?? 0))}%` }} /></span>
          <span className="sys-num">{rank === null ? '—' : rank.toFixed(1)}</span>
        </span>
      </span>
      <span className="sl-tile__figs">
        <span><span className="sl-k">conf</span> <span className="sys-num">{r.confidence ?? '—'}</span></span>
        <span><span className="sl-k">risk</span> {r.risk_level ? r.risk_level.toLowerCase() : '—'}</span>
        <span className="sl-price sys-num" title={r.price_as_of ? `close ${r.price_as_of}${r.stale ? ' · stale' : ''}` : undefined}>
          {fmtPrice(r.price)}
        </span>
      </span>
      {plus || minus ? (
        <span className="sl-tile__why">
          {plus ? <span data-tone="pos"><i aria-hidden>+</i><span className="visually-hidden">Strongest support: </span>{plus.label}</span> : null}
          {minus ? <span data-tone="neg"><i aria-hidden>−</i><span className="visually-hidden">Main caution: </span>{minus.label}</span> : null}
        </span>
      ) : null}
    </Link>
  )
}

export default function SectorLeaders() {
  const [answer, setAnswer] = useState<{ d?: RecommendationsResponse; error?: string } | null>(null)

  useEffect(() => {
    let alive = true
    // The same resource the ranked-universe panel reads, so Home asks once.
    readResource<RecommendationsResponse>('/api/recommendations?limit=8', 'snapshot')
      .then((d) => { if (alive) setAnswer({ d }) })
      .catch((e: Error) => { if (alive) setAnswer({ error: e.message }) })
    return () => { alive = false }
  }, [])

  const d = answer?.d
  const rows = d?.across_sectors ?? []
  const buys = rows.filter((r) => tone(r.model_signal) === 'pos').length

  return (
    <section className="sys-panel sl" aria-label="Sector leaders">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Sector leaders</h2>
          <span className="sys-panel-sub">
            {d && rows.length
              ? `the engine's best-ranked name in ${rows.length} sectors · ${buys} rated buy${d.generated_at ? ` · ${freshness(d.generated_at) ?? ''}` : ''}`
              : 'the engine’s best-ranked name in each sector'}
          </span>
        </div>
        <Link className="cw-more" href="/explore">Open screener</Link>
      </header>
      {answer === null ? (
        <div className="sl-grid sl-grid--loading" aria-busy="true">
          {Array.from({ length: 5 }, (_, i) => (
            <div className="sl-tile" key={i} aria-hidden>
              <span className="sys-skeleton" style={{ width: 90, height: 8 }} />
              <span className="sys-skeleton" style={{ width: '70%', height: 14 }} />
              <span className="sys-skeleton" style={{ width: '55%', height: 10 }} />
              <span className="sys-skeleton" style={{ width: '80%', height: 8 }} />
            </div>
          ))}
        </div>
      ) : answer.error ? (
        <StateBlock state="unavailable" title="Sector leaders are unavailable" detail={`${readerError(answer.error)}. The ranking is rebuilt from the screener universe; nothing is listed in its place.`} />
      ) : rows.length ? (
        <div className="sl-grid">
          {rows.map((r) => <Tile key={r.symbol} r={r} />)}
        </div>
      ) : (
        <StateBlock
          state="unknown"
          title="No sector has an eligible name right now"
          detail="Eligibility is a gate, not a ranking: a security without fresh prices or enough evidence is left out rather than filled in."
        />
      )}
      <footer className="sys-panel-foot">
        <span>Deterministic ranking of the screener universe · one name per sector, ordered by rank · not personalised advice</span>
        {d?.stale ? <span>stale snapshot{d.stale_reason ? ` — ${d.stale_reason}` : ''}</span> : null}
      </footer>
    </section>
  )
}
