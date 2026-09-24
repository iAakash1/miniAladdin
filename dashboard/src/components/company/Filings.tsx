'use client'

import { useState } from 'react'

import { filingItems } from '@/lib/filings'
import type { FilingsBlock, SecFiling } from '@/lib/types'

type Group = 'periodic' | 'current' | 'ownership' | 'other'

const GROUPS: Array<{ key: Group; label: string; note: string }> = [
  { key: 'periodic', label: 'Periodic reports', note: 'annual and quarterly statements' },
  { key: 'current', label: 'Current reports', note: 'material events, results releases' },
  { key: 'ownership', label: 'Ownership', note: 'insider transactions and large stakes' },
  { key: 'other', label: 'Other filings', note: 'registrations, proxies and the rest' },
]

function groupOf(form: string): Group {
  const f = form.toUpperCase()
  if (/^10-[KQ]/.test(f) || /^20-F|^40-F/.test(f)) return 'periodic'
  if (/^8-K|^6-K/.test(f)) return 'current'
  if (/^[345](\/A)?$/.test(f) || /^SC 13[DG]|^144/.test(f)) return 'ownership'
  return 'other'
}

function daysAgo(iso: string): number | null {
  const t = Date.parse(iso)
  return Number.isFinite(t) ? Math.floor((Date.now() - t) / 86_400_000) : null
}

function compact(v: number): string {
  return v.toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 2 })
}

export function FilingDoc({ f }: { f: SecFiling }) {
  return (
    <a className="fl-doc" href={f.url} target="_blank" rel="noopener noreferrer" data-group={groupOf(f.form)}>
      <span className="fl-doc__sheet" aria-hidden>
        <span className="fl-doc__form">{f.form}</span>
        <span className="fl-doc__lines"><i /><i /><i /></span>
      </span>
      <span className="fl-doc__text">
        <span className="fl-doc__title">{f.meaning || `Form ${f.form}`}</span>
        <span className="fl-doc__meta">
          filed {f.filed_at}
          {f.report_date ? ` · period ${f.report_date}` : ''}
          {f.items ? ` · ${filingItems(f.items)}` : ''}
        </span>
      </span>
    </a>
  )
}

/**
 * The filings themselves — primary sources, not a vendor's reading of them.
 * Each opens the document on EDGAR. The form mix reads before any single row:
 * a burst of Form 4s is insider activity, an 8-K a material event.
 */
export default function Filings({ block, recorded = false }: {
  block: FilingsBlock
  /** A recorded run: state the latest filing's date rather than an age that
   *  keeps growing after the run. */
  recorded?: boolean
}) {
  const [all, setAll] = useState(false)
  const recency = block.latest && !recorded ? daysAgo(block.latest.filed_at) : null
  const forms = Object.entries(block.by_form).sort((a, b) => b[1] - a[1])
  const total = forms.reduce((s, [, n]) => s + n, 0)
  const grouped = GROUPS.map((g) => ({ ...g, items: block.filings.filter((f) => groupOf(f.form) === g.key) }))
    .filter((g) => g.items.length)
  const trend = block.xbrl_trend ?? []
  const maxAbs = Math.max(1, ...trend.map((t) => Math.abs(t.change_pct)))

  return (
    <div className="cw-stack">
      <section className="sys-panel">
        <header className="sys-panel-head">
          <div className="sys-panel-head__title">
            <h2 className="sys-panel-title">Regulatory filings</h2>
            <span className="sys-panel-sub">
              {block.source} · {block.filings.length} recent
              {recency !== null ? ` · last filed ${recency === 0 ? 'today' : `${recency}d ago`}` : ''}
              {recorded && block.latest ? ` · latest filed ${block.latest.filed_at}` : ''}
            </span>
          </div>
        </header>
        {total ? (
          <div className="fl-mix">
            <div className="fl-mix__bar" role="img" aria-label={forms.map(([f, n]) => `${n} ${f}`).join(', ')}>
              {forms.map(([form, n]) => (
                <span key={form} className="fl-mix__seg" data-group={groupOf(form)} style={{ flex: n }} title={`${form}: ${n}`} />
              ))}
            </div>
            <div className="fl-mix__legend">
              {forms.map(([form, n]) => (
                <span key={form} className="fl-mix__key" data-group={groupOf(form)}>
                  <i aria-hidden />{form}<b className="sys-num">{n}</b>
                </span>
              ))}
            </div>
          </div>
        ) : null}
        <div className="fl-groups">
          {grouped.map((g) => (
            <div key={g.key} className="fl-group">
              <h3 className="fl-group__title">{g.label}<span>{g.note}</span></h3>
              <div className="fl-docs">
                {(all ? g.items : g.items.slice(0, 6)).map((f) => <FilingDoc key={f.accession} f={f} />)}
              </div>
            </div>
          ))}
          {!all && grouped.some((g) => g.items.length > 6) ? (
            <button type="button" className="sys-btn sys-btn--ghost" onClick={() => setAll(true)}>Show every filing</button>
          ) : null}
        </div>
      </section>

      {trend.length ? (
        <section className="sys-panel">
          <header className="sys-panel-head">
            <div className="sys-panel-head__title">
              <h2 className="sys-panel-title">Reported year over year</h2>
              <span className="sys-panel-sub">XBRL facts the company tagged, consecutive fiscal years of the same concept</span>
            </div>
          </header>
          <ul className="fl-trend">
            {trend.slice(0, 8).map((t) => (
              <li key={t.concept}>
                <span className="fl-trend__name">{t.concept}</span>
                <span className="fl-trend__vals sys-num">{compact(t.prior_value)} → {compact(t.latest_value)} {t.unit !== 'USD' ? t.unit : ''}</span>
                <span className="fl-trend__bar" aria-hidden>
                  <span data-tone={t.change_pct >= 0 ? 'pos' : 'neg'} style={{ width: `${(Math.abs(t.change_pct) / maxAbs) * 100}%` }} />
                </span>
                <span className={`fl-trend__pct sys-num ${t.change_pct > 0 ? 'sys-pos' : t.change_pct < 0 ? 'sys-neg' : ''}`}>
                  {t.change_pct > 0 ? '+' : ''}{t.change_pct.toFixed(1)}%
                </span>
                <span className="fl-trend__src">FY{t.prior_year}→FY{t.latest_year} · {t.form} filed {t.filed}</span>
              </li>
            ))}
          </ul>
          <footer className="sys-panel-foot">
            <span>A concept with one year of data shows no trend rather than a zero.</span>
          </footer>
        </section>
      ) : null}

      {block.restatements?.length ? (
        <section className="sys-panel">
          <header className="sys-panel-head">
            <div className="sys-panel-head__title">
              <h2 className="sys-panel-title">Restated after first filing</h2>
              <span className="sys-panel-sub">same concept, same exact period, reported differently later</span>
            </div>
          </header>
          <ul className="fl-restate">
            {block.restatements.slice(0, 8).map((r) => (
              <li key={`${r.concept}-${r.period_end}`}>
                <span className="fl-restate__name">{r.label}</span>
                <span className="sys-num">{r.period_start ? `${r.period_start} → ${r.period_end}` : r.period_end}</span>
                <span className="sys-num">{compact(r.original_value)} → {compact(r.revised_value)}</span>
                <span className={`sys-num ${r.change_pct > 0 ? 'sys-pos' : 'sys-neg'}`}>{r.change_pct > 0 ? '+' : ''}{r.change_pct.toFixed(1)}%</span>
                <span className="fl-restate__filed">filed {r.original_filed}, revised {r.revised_filed}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
