/**
 * Filings and headlines, as research inputs rather than a news feed.
 *
 * Two capabilities absorbed from the legacy security report, and the reason to
 * keep both is that they answer the same question from opposite directions:
 * what has this company said about itself, and what has been said about it.
 *
 * Restatements get their own panel. A later filing that revised an earlier
 * number is the single most consequential thing in a filing history for anyone
 * building point-in-time features — it is direct evidence that the value known
 * at the time differs from the value known now, which is exactly the trap
 * point-in-time discipline exists to avoid.
 *
 * Headlines carry corroboration. A story one vendor ran is a different object
 * from one three ran independently, and that count is the closest thing a
 * headline feed has to verification.
 */
'use client'

import { useMemo, useState } from 'react'

import { Panel, Prose, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'

export interface SecFiling {
  form: string
  meaning?: string
  filed_at: string
  report_date?: string | null
  accession?: string
  url?: string
  items?: string | null
}

export interface Restatement {
  label: string
  concept?: string
  period_start?: string | null
  period_end: string
  unit?: string
  form?: string
  original_value: number
  original_filed?: string
  revised_value?: number
  revised_filed?: string
}

export interface FilingsBlock {
  filings?: SecFiling[]
  restatements?: Restatement[]
  by_form?: Record<string, number>
  latest?: SecFiling | null
  source?: string
}

export interface Headline {
  title: string
  score?: number
  label?: 'Bullish' | 'Bearish' | 'Neutral'
  source?: string
  url?: string
  publishedAt?: string
  corroboratedBy?: string[]
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function toneState(label?: string): ResearchState {
  if (label === 'Bullish') return 'candidate'
  if (label === 'Bearish') return 'blocked'
  return 'recorded'
}

export default function Disclosure({
  filings, headlines, symbol,
}: {
  filings?: FilingsBlock | null
  headlines?: Headline[] | null
  symbol: string
}) {
  const [tab, setTab] = useState<'filings' | 'headlines'>('filings')

  const rows = useMemo(() => filings?.filings ?? [], [filings])
  const restatements = useMemo(() => filings?.restatements ?? [], [filings])
  const news = useMemo(() => headlines ?? [], [headlines])

  const filingColumns: DataColumn<SecFiling>[] = useMemo(() => [
    { key: 'form', header: 'Form', width: '10%', sort: (f) => f.form, text: (f) => f.form, render: (f) => <span className="sys-mono">{f.form}</span> },
    { key: 'filed', header: 'Filed', width: '13%', sort: (f) => f.filed_at, render: (f) => <span className="sys-num">{f.filed_at?.slice(0, 10)}</span> },
    {
      key: 'report', header: 'Period end', unit: 'covered', width: '13%', sort: (f) => f.report_date ?? null,
      render: (f) => f.report_date ? <span className="sys-num">{f.report_date.slice(0, 10)}</span> : <span className="sys-null">—</span>,
    },
    {
      key: 'lag', header: 'Filing lag', unit: 'days', numeric: true,
      sort: (f) => (f.report_date && f.filed_at ? (Date.parse(f.filed_at) - Date.parse(f.report_date)) / 86_400_000 : null),
      render: (f) => (
        <Value
          value={f.report_date && f.filed_at ? Math.round((Date.parse(f.filed_at) - Date.parse(f.report_date)) / 86_400_000) : null}
          digits={0}
          title="Days between the period a filing covers and the day it became public. This is the availability lag any point-in-time feature built from it must respect."
        />
      ),
    },
    { key: 'meaning', header: 'What it is', text: (f) => `${f.meaning ?? ''} ${f.items ?? ''}`, render: (f) => <span style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>{f.meaning ?? '—'}</span> },
    {
      key: 'link', header: '', width: '58px',
      render: (f) => f.url
        ? <a className="sys-btn" href={f.url} target="_blank" rel="noreferrer noopener">open</a>
        : <span className="sys-null">—</span>,
    },
  ], [])

  const headlineColumns: DataColumn<Headline>[] = useMemo(() => [
    { key: 'when', header: 'Published', width: '15%', sort: (h) => h.publishedAt ?? null, render: (h) => <span className="sys-num">{h.publishedAt?.slice(0, 16).replace('T', ' ') ?? '—'}</span> },
    {
      key: 'title', header: 'Headline', text: (h) => h.title,
      render: (h) => h.url
        ? <a href={h.url} target="_blank" rel="noreferrer noopener" style={{ color: 'inherit' }}>{h.title}</a>
        : h.title,
    },
    { key: 'src', header: 'Source', width: '13%', sort: (h) => h.source ?? null, text: (h) => h.source ?? '', render: (h) => <span className="sys-meta sys-meta--strong">{h.source ?? '—'}</span> },
    {
      key: 'corr', header: 'Corroborated', unit: 'vendors', numeric: true,
      sort: (h) => h.corroboratedBy?.length ?? 0,
      render: (h) => (
        <Value
          value={h.corroboratedBy?.length ?? 0}
          digits={0}
          title={h.corroboratedBy?.length ? `Also carried by: ${h.corroboratedBy.join(', ')}` : 'Carried by one vendor only'}
        />
      ),
    },
    {
      key: 'tone', header: 'Tone', width: '12%', sort: (h) => h.label ?? null,
      render: (h) => h.label ? <Status state={toneState(h.label)} label={h.label.toLowerCase()} /> : <span className="sys-null">—</span>,
    },
  ], [])

  const worstLag = useMemo(() => {
    const lags = rows
      .filter((f) => f.report_date && f.filed_at)
      .map((f) => (Date.parse(f.filed_at) - Date.parse(f.report_date!)) / 86_400_000)
    return lags.length ? Math.max(...lags) : null
  }, [rows])

  return (
    <>
      <Strip metrics={[
        { label: 'Filings', value: rows.length || null, digits: 0 },
        { label: 'Restatements', value: restatements.length, digits: 0, title: 'Later filings that revised an earlier number' },
        { label: 'Longest filing lag', value: worstLag, digits: 0, unit: 'd', title: 'The availability lag any point-in-time feature built from these must respect' },
        { label: 'Headlines', value: news.length || null, digits: 0 },
        { label: 'Multi-vendor stories', value: news.filter((h) => (h.corroboratedBy?.length ?? 0) > 1).length || null, digits: 0 },
      ]} />

      {restatements.length ? (
        <Panel title="Restatements" subtitle={`${restatements.length} figures were later revised`} state="blocked">
          <p style={{ margin: '0 0 var(--d-3)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            A later filing revised each of these. That is direct evidence that the
            value knowable at the time differs from the value knowable now — which
            is precisely the trap point-in-time discipline exists to avoid. A
            feature built from the current figure would be using information that
            did not exist on the date it claims to describe.
          </p>
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr>
                  <th>Concept</th><th>Period</th><th className="num">Originally</th>
                  <th>Filed</th><th className="num">Revised to</th><th>Revised</th><th className="num">Change</th>
                </tr>
              </thead>
              <tbody>
                {restatements.map((r, i) => {
                  const delta = n(r.revised_value) !== null && n(r.original_value) !== null
                    ? (r.revised_value as number) - r.original_value
                    : null
                  return (
                    <tr key={`${r.concept ?? r.label}-${r.period_end}-${i}`}>
                      <td style={{ fontFamily: 'var(--font-mono)' }} title={r.concept}>{r.label}</td>
                      <td className="num">{r.period_end?.slice(0, 10)}</td>
                      <td className="num"><Value value={n(r.original_value)} digits={0} unit={r.unit ?? undefined} /></td>
                      <td className="num">{r.original_filed?.slice(0, 10) ?? '—'}</td>
                      <td className="num"><Value value={n(r.revised_value)} digits={0} /></td>
                      <td className="num">{r.revised_filed?.slice(0, 10) ?? '—'}</td>
                      <td className="num"><Value value={delta} digits={0} signed tone /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      <Panel
        title="Disclosure"
        subtitle={tab === 'filings' ? filings?.source : `${news.length} headlines`}
        flush
        actions={
          <div className="sys-seg">
            {(['filings', 'headlines'] as const).map((t) => (
              <button key={t} className="sys-btn" aria-pressed={tab === t} onClick={() => setTab(t)}>{t}</button>
            ))}
          </div>
        }
      >
        {tab === 'filings' ? (
          rows.length ? (
            <DataTable
              columns={filingColumns} rows={rows} rowKey={(f) => f.accession ?? `${f.form}-${f.filed_at}`}
              density="compact" filterPlaceholder="filter filings"
              initialSort={{ key: 'filed', direction: 'desc' }}
            />
          ) : (
            <StateBlock
              state="unavailable"
              title={`No filings recorded for ${symbol}`}
              detail="The filing source returned nothing for this name. No rows are shown in place of that."
            />
          )
        ) : news.length ? (
          <DataTable
            columns={headlineColumns} rows={news} rowKey={(h) => h.url ?? h.title}
            density="compact" filterPlaceholder="filter headlines"
            initialSort={{ key: 'when', direction: 'desc' }}
          />
        ) : (
          <StateBlock
            state="unavailable"
            title={`No headlines recorded for ${symbol}`}
            detail="No vendor returned a story for this name in the window queried."
          />
        )}
      </Panel>

      {filings?.by_form && Object.keys(filings.by_form).length ? (
        <Panel title="Filing activity" subtitle="by form">
          <Section title="Counts">
            <table className="sys-table sys-table--compact">
              <tbody>
                {Object.entries(filings.by_form).sort((a, b) => b[1] - a[1]).map(([form, count]) => (
                  <tr key={form}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{form}</td>
                    <td className="num"><Value value={count} digits={0} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </Panel>
      ) : null}

      {news.length ? (
        <Panel title="Reading headlines">
          <Prose>
            The corroboration count is the useful column. A story one vendor ran is
            a different object from one three ran independently, and that count is
            the closest thing a headline feed has to verification. Tone is a
            vendor&apos;s classification, not a measurement, and no factor in this
            product is built from it.
          </Prose>
        </Panel>
      ) : null}
    </>
  )
}
