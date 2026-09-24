'use client'

import { useMemo, useState } from 'react'

import { factorName } from './derive'
import { profileRef } from './profileRef'
import { Inspectable } from '@/components/system'
import Thumb from '@/components/visual/Thumb'
import Timeline, { type TimelineItem, type TimelineKind } from '@/components/visual/Timeline'
import { filingItems } from '@/lib/filings'
import { diffSnapshots, useHistory, type AnalysisSnapshot } from '@/lib/history'
import type { Analysis, CompanyProfile, Headline, SecFiling } from '@/lib/types'

/* ── building the timeline ─────────────────────────────────────────────── */

const INSIDER_FORMS = new Set(['3', '4', '5', '144', '3/A', '4/A', '5/A'])

function filingKind(f: SecFiling): TimelineKind {
  if (INSIDER_FORMS.has(f.form)) return 'insider'
  // An 8-K carrying item 2.02 is the results release itself.
  if (f.form.startsWith('8-K') && f.items && /\b2\.02\b/.test(f.items)) return 'earnings'
  return 'filing'
}

function filingItem(f: SecFiling): TimelineItem {
  const kind = filingKind(f)
  const detail = [
    f.report_date ? `period ${f.report_date}` : null,
    filingItems(f.items),
    'SEC EDGAR',
  ].filter(Boolean).join(' · ')
  return {
    id: `f-${f.accession}`,
    date: f.filed_at,
    kind,
    tag: f.form,
    title: f.meaning || `Form ${f.form}`,
    detail,
    href: f.url,
    external: true,
  }
}

/** Opening the article itself is a Pro feature, as the pricing page states. */
export function newsItem(h: Headline, { linked = false, thumbs = true }: { linked?: boolean; thumbs?: boolean } = {}): TimelineItem {
  const carried = h.corroboratedBy.length > 1 ? `carried by ${h.corroboratedBy.length} vendors` : null
  // Tone is shown only with the vendor that scored it; unscored is not neutral.
  const tone = h.sentimentLabel && h.sentimentSource ? `${h.sentimentLabel.toLowerCase()} per ${h.sentimentSource}` : null
  return {
    id: `n-${h.url || h.title}`,
    date: h.publishedAt,
    kind: 'news',
    title: h.title,
    detail: [h.source, carried, tone].filter(Boolean).join(' · '),
    href: linked && h.url ? h.url : undefined,
    external: true,
    media: thumbs ? <Thumb src={h.imageUrl} source={h.source} url={h.url} width={72} ratio="16 / 10" /> : undefined,
  }
}

function runDetail(run: AnalysisSnapshot, older: AnalysisSnapshot | undefined): string {
  if (!older) return 'first run recorded in this browser'
  const d = diffSnapshots(older, run)
  const parts: string[] = []
  if (d.verdictChanged) parts.push(`${older.verdict} → ${run.verdict}`)
  if (d.confidenceDelta) parts.push(`confidence ${d.confidenceDelta > 0 ? '+' : ''}${d.confidenceDelta}`)
  const top = d.topDrivers[0]
  if (top && Math.abs(top.delta) >= 0.005) {
    parts.push(`${factorName(top.name)} ${top.delta > 0 ? 'strengthened' : 'weakened'} ${top.delta > 0 ? '+' : ''}${top.delta.toFixed(3)}`)
  }
  for (const r of d.regimesEntered) parts.push(`entered ${r.replace(/_/g, ' ')}`)
  return parts.length ? parts.join(' · ') : 'no material change from the previous run'
}

function runItems(runs: AnalysisSnapshot[]): TimelineItem[] {
  // Stored oldest first.
  return runs.map((run, i) => ({
    id: `r-${run.ts}`,
    date: run.ts,
    kind: 'research' as const,
    tag: 'RUN',
    title: `${run.verdict} · confidence ${run.confidence}${run.riskLevel ? ` · ${run.riskLevel.toLowerCase()} risk` : ''}`,
    detail: runDetail(run, runs[i - 1]),
    tone: /buy/i.test(run.verdict) ? 'pos' as const : /sell/i.test(run.verdict) ? 'neg' as const : 'muted' as const,
  }))
}

export function activityItems(a: Analysis, runs: AnalysisSnapshot[], linked = false): TimelineItem[] {
  return [
    ...(a.filings?.filings ?? []).map(filingItem),
    ...a.headlines.map((h) => newsItem(h, { linked })),
    ...runItems(runs),
  ]
}

/* ── the panels ────────────────────────────────────────────────────────── */

const FILTERS: Array<{ key: 'all' | TimelineKind | 'filings'; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'filings', label: 'Filings' },
  { key: 'news', label: 'News' },
  { key: 'research', label: 'Research' },
]

function matches(item: TimelineItem, key: (typeof FILTERS)[number]['key']): boolean {
  if (key === 'all') return true
  if (key === 'filings') return item.kind === 'filing' || item.kind === 'insider' || item.kind === 'earnings'
  return item.kind === key
}

/** Filings, news and this browser's research runs on one dated line. */
export function Activity({ a, limit = 12, linked = false }: { a: Analysis; limit?: number; linked?: boolean }) {
  const runs = useHistory(a.ticker)
  const items = useMemo(() => activityItems(a, runs, linked), [a, runs, linked])
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('all')
  const [more, setMore] = useState(false)
  const shown = items.filter((i) => matches(i, filter))
  const count = (key: (typeof FILTERS)[number]['key']) => items.filter((i) => matches(i, key)).length

  return (
    <section className="sys-panel cw-activity" aria-label="Company activity">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Activity</h2>
          <span className="sys-panel-sub">SEC filings, news and research runs, newest first</span>
        </div>
      </header>
      <div className="sys-tabs cw-activity__filters" role="tablist" aria-label="Activity type">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            className="sys-tab"
            aria-selected={filter === f.key}
            onClick={() => { setFilter(f.key); setMore(false) }}
          >
            {f.label}<span className="sys-tab__count">{count(f.key)}</span>
          </button>
        ))}
      </div>
      <div className="cw-activity__body">
        <Timeline
          items={shown}
          limit={more ? undefined : limit}
          empty={<p className="cw-muted">Nothing of this kind was returned for this company.</p>}
        />
        {!more && shown.length > limit ? (
          <button type="button" className="sys-btn sys-btn--ghost cw-activity__more" onClick={() => setMore(true)}>
            Show {shown.length - limit} more
          </button>
        ) : null}
      </div>
      {runs.length ? (
        <footer className="sys-panel-foot">
          <span>Research runs are the ones recorded in this browser; the full record is in the Research log.</span>
        </footer>
      ) : null}
    </section>
  )
}

function formatCap(v: number | null, currency: string): string | null {
  if (v === null || !Number.isFinite(v) || v <= 0) return null
  const [div, unit] = v >= 1e12 ? [1e12, 'T'] : v >= 1e9 ? [1e9, 'B'] : [1e6, 'M']
  return `${currency === 'USD' || !currency ? '$' : `${currency} `}${(v / div).toFixed(2)}${unit}`
}

/** What the company is, from whichever vendors answered — with its sources. */
export function Profile({ profile }: { profile: CompanyProfile | null }) {
  const [open, setOpen] = useState(false)
  if (!profile) return null
  // [label, payload field, rendered value]; a field the payload did not return has no row.
  const rows: Array<[string, string, string | null]> = [
    ['Sector', 'sector', profile.sector || null],
    ['Industry', 'industry', profile.industry && profile.industry !== profile.sector ? profile.industry : null],
    ['Exchange', 'exchange', profile.exchange || null],
    ['Country', 'country', profile.country || null],
    ['Market cap', 'market_cap', formatCap(profile.market_cap, profile.currency)],
    ['Employees', 'employees', profile.employees && profile.employees > 0 ? profile.employees.toLocaleString('en-US') : null],
    ['Chief executive', 'ceo', profile.ceo || null],
    ['Listed', 'ipo_date', profile.ipo_date || null],
    ['Beta', 'beta', profile.beta !== null && Number.isFinite(profile.beta) ? profile.beta.toFixed(2) : null],
  ]
  const known = rows.filter((r): r is [string, string, string] => Boolean(r[2]))
  const long = (profile.description ?? '').length > 360

  return (
    <section className="sys-panel cw-profile" aria-label="Company profile">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Company profile</h2>
          {profile.providers?.length ? <span className="sys-panel-sub">from {profile.providers.join(', ')}</span> : null}
        </div>
      </header>
      <div className="sys-panel-body">
        {profile.description ? (
          <>
            <p className="cw-profile__desc" data-open={open || !long ? '' : undefined}>{profile.description}</p>
            {long ? (
              <button type="button" className="cw-link-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
                {open ? 'Show less' : 'Read the full description'}
              </button>
            ) : null}
          </>
        ) : <p className="cw-muted">No vendor returned a business description.</p>}
        {known.length ? (
          <dl className="cw-kv cw-kv--tight cw-profile__facts">
            {known.map(([k, field, v]) => {
              const ref = profileRef(profile, field, k, v)
              return <div key={k}><dt>{k}</dt><dd>{ref ? <Inspectable refValue={ref}>{v}</Inspectable> : v}</dd></div>
            })}
          </dl>
        ) : null}
        {profile.conflicts?.length ? (
          <ul className="cw-profile__conflicts">
            {profile.conflicts.map((c) => (
              <li key={c.field}>
                Vendors disagree on {c.field.replace(/_/g, ' ')} by {c.spread_pct.toFixed(1)}%:{' '}
                {c.observations.map((o) => `${o.provider} ${o.value.toLocaleString('en-US')}`).join(' vs ')}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  )
}
