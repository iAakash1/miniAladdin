/**
 * Portfolio workbench.
 *
 * Book, exposure, return, cost and attribution — with the cost section stated
 * on both bases, because the two figures published there sit on different ones
 * and multiplying the wrong pair understates the charge by exactly two.
 *
 * Risk lives in its own workspace and is linked to rather than duplicated here.
 * Two implementations of the same table eventually disagree.
 */
'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Panel, StateBlock, Status, Strip, Table, Value, type Column } from '@/components/system'

interface Weight { symbol: string; weight: number; side: string; signal?: number | null; risk_share: number | null }
interface Payload {
  status: string
  experiment_id?: string
  model_id?: string
  target?: string
  as_of?: string
  method?: string
  allocation?: Record<string, unknown>
  weights?: Weight[]
  risk?: { metrics?: Record<string, { value: number | null; method: string }> }
  risk_contributions_unavailable?: string | null
  cost?: {
    breakdown?: Record<string, number>
    waterfall?: Record<string, unknown>
    assumptions?: Record<string, unknown>
  }
  note?: string
}

export default function PortfolioWorkbench() {
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/portfolio')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Payload) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  if (error) {
    return (
      <Panel title="Book" state="unavailable">
        <StateBlock state="unavailable" title="No book is available" detail={`Request failed: ${error}. Nothing is shown in its place.`} />
      </Panel>
    )
  }
  if (!data) return <Panel title="Book" state="waking"><StateBlock state="waking" title="Constructing the book" /></Panel>

  const weights = data.weights ?? []
  const longs = weights.filter((w) => w.weight > 0)
  const shorts = weights.filter((w) => w.weight < 0)
  const gross = weights.reduce((s, w) => s + Math.abs(w.weight), 0)
  const net = weights.reduce((s, w) => s + w.weight, 0)
  const assumptions = (data.cost?.assumptions ?? {}) as Record<string, unknown>

  const columns: Column<Weight>[] = [
    {
      key: 'sym', header: 'Symbol', width: '18%',
      // Every holding is a link into its own workspace. This is the edge that
      // makes the book part of the object graph rather than a terminal list.
      render: (w) => (
        <Link href={`/terminal/security?symbol=${encodeURIComponent(w.symbol)}`} style={{ color: 'inherit', fontFamily: 'var(--font-mono)' }}>
          {w.symbol}
        </Link>
      ),
    },
    { key: 'side', header: 'Side', width: '12%', render: (w) => <Status state={w.weight >= 0 ? 'recorded' : 'experimental'} label={w.side} /> },
    { key: 'w', header: 'Weight', numeric: true, render: (w) => <Value value={w.weight} digits={6} signed tone /> },
    { key: 'sig', header: 'Signal', unit: 'rank', numeric: true, render: (w) => <Value value={w.signal ?? null} digits={6} signed /> },
    {
      key: 'rc', header: 'Risk share', numeric: true,
      render: (w) => <Value value={w.risk_share} digits={4} title={w.risk_share === null ? 'Not available: the covariance could not describe this book' : undefined} />,
    },
  ]

  return (
    <>
      <Strip metrics={[
        { label: 'Positions', value: weights.length, digits: 0 },
        { label: 'Long', value: longs.length, digits: 0 },
        { label: 'Short', value: shorts.length, digits: 0 },
        { label: 'Gross exposure', value: gross, digits: 4 },
        { label: 'Net exposure', value: net, digits: 4, signed: true, tone: true },
        { label: 'Method', value: data.method ?? null, digits: 0 },
      ]} />

      {data.risk_contributions_unavailable ? (
        <Panel title="Risk share" state="unavailable">
          <StateBlock
            state="unavailable"
            title="Risk contributions are not available for this book"
            detail={data.risk_contributions_unavailable}
          />
        </Panel>
      ) : null}

      <Panel
        title="Book"
        subtitle={[data.model_id, data.target, data.as_of].filter(Boolean).join(' · ')}
        state={data.status === 'ok' ? 'recorded' : 'unavailable'}
        flush
        actions={<Link href="/terminal/risk" className="sys-meta" style={{ color: 'var(--ink)' }}>Risk →</Link>}
      >
        <Table columns={columns} rows={weights} rowKey={(w) => w.symbol} density="compact" />
      </Panel>

      <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        <Panel title="Cost assumptions" state="recorded">
          <table className="sys-table sys-table--compact">
            <tbody>
              {Object.entries(assumptions)
                .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
                .map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ fontFamily: 'var(--font-mono)', width: '46%' }}>{k}</td>
                    <td className="num" style={{ whiteSpace: 'normal', textAlign: 'left' }}>
                      {typeof v === 'number'
                        ? <Value value={v} digits={2} />
                        : <span className="sys-meta" style={{ color: 'var(--ink)' }}>{String(v)}</span>}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            Costs are charged on the round-trip notional. Reported turnover is
            one-way, so the two differ by exactly two and only the round-trip
            figure reproduces the charge.
          </p>
        </Panel>

        <Panel title="Cost breakdown">
          {data.cost?.breakdown && Object.keys(data.cost.breakdown).length ? (
            <table className="sys-table sys-table--compact">
              <tbody>
                {Object.entries(data.cost.breakdown).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td>
                    <td className="num"><Value value={typeof v === 'number' ? v : null} digits={4} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <StateBlock state="unavailable" title="No breakdown recorded" />}
        </Panel>

        <Panel title="Allocation">
          {data.allocation && Object.keys(data.allocation).length ? (
            <table className="sys-table sys-table--compact">
              <tbody>
                {Object.entries(data.allocation)
                  .filter(([, v]) => typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean')
                  .map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ fontFamily: 'var(--font-mono)', width: '52%' }}>{k}</td>
                      <td className="num">
                        {typeof v === 'number' ? <Value value={v} digits={4} /> : <span className="sys-meta" style={{ color: 'var(--ink)' }}>{String(v)}</span>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : <StateBlock state="unavailable" title="No allocation diagnostics recorded" />}
        </Panel>
      </div>

      {data.note ? (
        <Panel title="Note">
          <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>{data.note}</p>
        </Panel>
      ) : null}
    </>
  )
}
