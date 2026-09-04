'use client'

/**
 * Who the company is, and what it has filed — loaded after the price.
 *
 * This reads /api/research, which takes between twenty-five and forty-five
 * seconds because it fans out across every configured vendor. That is far too
 * slow to sit on the path to first paint, and far too useful to leave out.
 *
 * So it loads on its own, below a page that is already usable, and says
 * plainly that it is still working. Nothing above it waits, and if it never
 * arrives the security page is exactly as useful as it was a second after
 * opening.
 *
 * Only fields the payload actually returned are rendered. A company with no
 * recorded employee count has no employees row — not a row reading zero, and
 * not a row reading "N/A" in the position a number would occupy.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { fetchResearch } from '@/lib/research-cache'

interface Profile {
  name?: string
  exchange?: string
  sector?: string
  industry?: string
  country?: string
  currency?: string
  website?: string
  employees?: number
  market_cap?: number
  beta?: number
  ipo_date?: string
  description?: string
  providers?: string[]
}

interface Filing {
  accession?: string
  form?: string
  meaning?: string
  filed_at?: string
  report_date?: string
  url?: string
  items?: string
}

interface NewsSummary {
  collected?: number
  unique?: number
  corroborated?: number
  providers?: string[]
  sentiment?: number | string
  categories?: Record<string, number>
}

interface Research {
  profile?: Profile
  filings?: Filing[]
  news_stream?: NewsSummary
}

export default function SecurityProfile({ symbol }: { symbol: string }) {
  /* Tagged with the symbol it answers. Loading is derived from the tag not
     matching, rather than written into state when the effect starts — which
     keeps the effect free of synchronous state writes and makes a slow answer
     for a previous symbol structurally incapable of landing on a new one. */
  const [settled, setSettled] = useState<
    { for: string; d?: Research; error?: string } | null
  >(null)

  useEffect(() => {
    let alive = true
    // Shared with the fundamentals panel below, which needs the same payload.
    // Three fan-outs for one company would be three sets of vendor rate limit
    // spent on facts that arrive at three different times.
    fetchResearch(symbol)
      // The cache returns the whole response; this panel reads one part of
      // it. The narrowing is here, at the boundary, rather than inside the
      // shared fetch — which has no business knowing who wants what.
      .then((d) => { if (alive) setSettled({ for: symbol, d: d as unknown as Research }) })
      .catch((e: Error) => { if (alive) setSettled({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const current = settled?.for === symbol ? settled : null
  const state = current === null
    ? { s: 'loading' as const }
    : current.error
      ? { s: 'failed' as const, detail: current.error }
      : { s: 'ready' as const, for: symbol, d: current.d ?? {} }

  if (state.s === 'loading') {
    return (
      <Panel title="Company" state="waking">
        <StateBlock
          state="waking"
          title="Reading the company profile"
          detail="This fans out across every configured vendor and takes half a minute. The price and history above did not wait for it."
        />
      </Panel>
    )
  }

  if (state.s === 'failed') {
    return (
      <Panel title="Company" state="unavailable">
        <StateBlock
          state="unavailable"
          title="No company profile was returned"
          detail={`${state.detail}. The market data above is unaffected — it comes from a different provider path.`}
        />
      </Panel>
    )
  }

  if (state.for !== symbol) return null

  const p = state.d.profile ?? {}
  const filings = state.d.filings ?? []
  const news = state.d.news_stream

  /* Only what came back. A row per field the vendor actually reported. */
  const rows: { k: string; v: React.ReactNode }[] = []
  const add = (k: string, v: React.ReactNode | null | undefined) => { if (v !== null && v !== undefined && v !== '') rows.push({ k, v }) }
  add('Name', p.name)
  add('Exchange', p.exchange)
  add('Sector', p.sector)
  add('Industry', p.industry)
  add('Country', p.country)
  add('Currency', p.currency)
  if (typeof p.market_cap === 'number') add('Market cap', <Value value={p.market_cap} kind="currency" digits={0} />)
  if (typeof p.employees === 'number') add('Employees', <Value value={p.employees} kind="count" />)
  if (typeof p.beta === 'number') add('Beta', <Value value={p.beta} kind="ratio" />)
  add('Listed', p.ipo_date)

  return (
    <>
      <Panel
        title="Company"
        subtitle={p.name ?? undefined}
        state={rows.length ? 'live' : 'unavailable'}
        source={p.providers?.length ? p.providers.join(', ') : undefined}
      >
        {rows.length ? (
          <table className="sys-table sys-table--compact">
            <tbody>
              {rows.map((r) => (
                <tr key={r.k}>
                  <td style={{ width: '11rem', color: 'var(--ink-muted)' }}>{r.k}</td>
                  <td>{r.v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <StateBlock
            state="unavailable"
            title="No profile fields were returned for this symbol"
            detail="The vendors answered without identity data. Nothing is shown in place of it."
          />
        )}
        {p.description ? <Prose size="tight">{p.description}</Prose> : null}
      </Panel>

      {filings.length ? (
        <Panel title="Filings" subtitle={`${filings.length} most recent`} state="live" source="SEC EDGAR" flush>
          <table className="sys-table sys-table--compact">
            <thead>
              <tr><th>Form</th><th>Filed</th><th>Period</th><th>Meaning</th><th /></tr>
            </thead>
            <tbody>
              {filings.slice(0, 10).map((f, i) => (
                <tr key={`${f.accession ?? f.url ?? i}`}>
                  <td className="sys-mono">{f.form ?? '—'}</td>
                  <td className="sys-mono">{f.filed_at ?? '—'}</td>
                  <td className="sys-mono">{f.report_date ?? '—'}</td>
                  <td><span className="sys-meta">{f.meaning ?? '—'}</span></td>
                  <td className="num">
                    {f.url ? (
                      <a className="sys-btn sys-btn--micro" href={f.url} target="_blank" rel="noopener noreferrer">
                        open
                      </a>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}

      {news && typeof news.collected === 'number' ? (
        <Panel title="Coverage" subtitle="what the news vendors returned" state="live">
          {/* A count of what was collected, not a summary of what it said. The
              vendors return headlines; nothing here paraphrases them, because a
              generated summary of financial news is a claim nobody checked. */}
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td style={{ width: '11rem', color: 'var(--ink-muted)' }}>Articles collected</td>
                  <td><Value value={news.collected} kind="count" /></td></tr>
              {typeof news.unique === 'number' ? (
                <tr><td style={{ color: 'var(--ink-muted)' }}>Distinct stories</td>
                    <td><Value value={news.unique} kind="count" /></td></tr>
              ) : null}
              {typeof news.corroborated === 'number' ? (
                <tr><td style={{ color: 'var(--ink-muted)' }}>Reported by more than one vendor</td>
                    <td><Value value={news.corroborated} kind="count" /></td></tr>
              ) : null}
              {news.providers?.length ? (
                <tr><td style={{ color: 'var(--ink-muted)' }}>Vendors</td>
                    <td><span className="sys-meta">{news.providers.join(', ')}</span></td></tr>
              ) : null}
            </tbody>
          </table>
          {news.categories && Object.keys(news.categories).length ? (
            <div className="sec-cats">
              {Object.entries(news.categories).map(([k, v]) => (
                <span key={k} className="sys-meta">
                  <Status state="recorded" label={k} /> <Value value={v} kind="count" />
                </span>
              ))}
            </div>
          ) : null}
        </Panel>
      ) : null}
    </>
  )
}
