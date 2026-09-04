'use client'

/**
 * The market in one panel.
 *
 * The home screen embedded the entire market workspace — breadth history, the
 * sector map, the events table, leadership, the ninety-day chart — which is a
 * good workspace and far too much for a screen whose job is to say what
 * matters right now.
 *
 * This is the summary: the major indices with their moves, breadth, and the
 * regime. Everything else is one click away on Market, where a reader has
 * gone specifically to look at the market.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Panel, StateBlock, Status, Strip, Value } from '@/components/system'
import { readResource } from '@/lib/resource'

interface Index {
  symbol: string
  price?: number | null
  change_1d?: number | null
  change_1w?: number | null
  source?: string | null
}

interface Dashboard {
  breadth?: {
    breadth_score?: number | null
    sectors_above_50d?: number | null
    sector_count?: number | null
    leadership?: string | null
    laggard?: string | null
    indexes?: Index[]
  }
  macro?: { regime?: { status?: string; available?: boolean } | string | null }
  generated_at?: string
  cached?: boolean
}

export default function MarketSummary() {
  const [state, setState] = useState<{ d?: Dashboard; error?: string } | null>(null)

  useEffect(() => {
    let alive = true
    readResource<Dashboard>('/api/dashboard', 'snapshot')
      .then((d) => { if (alive) setState({ d }) })
      .catch((e: Error) => { if (alive) setState({ error: e.message }) })
    return () => { alive = false }
  }, [])

  const b = state?.d?.breadth
  const regimeRaw = state?.d?.macro?.regime
  const regime = typeof regimeRaw === 'string'
    ? regimeRaw
    : regimeRaw?.available === false ? null : regimeRaw?.status ?? null

  return (
    <Panel
      title="Market"
      subtitle={state?.d?.generated_at ? `as of ${state.d.generated_at.slice(0, 16).replace('T', ' ')}` : undefined}
      state={state?.error ? 'unavailable' : state ? 'live' : 'waking'}
      actions={<Link href="/terminal/market" className="sys-btn">open market</Link>}
    >
      {state?.error ? (
        <StateBlock
          state="unavailable"
          title="The market snapshot could not be read"
          detail={`${state.error}. Nothing is shown in its place.`}
        />
      ) : !state ? (
        <StateBlock state="waking" title="Reading the market snapshot" />
      ) : (
        <>
          <Strip metrics={[
            { label: 'Breadth', value: b?.breadth_score ?? null, kind: 'percent', digits: 0,
              title: 'Share of the tracked sector ETFs above their 50-day average' },
            { label: 'Above 50d', value: b?.sectors_above_50d ?? null, kind: 'count' },
            { label: 'Sectors', value: b?.sector_count ?? null, kind: 'count' },
            { label: 'Leading', value: b?.leadership ?? null },
            { label: 'Lagging', value: b?.laggard ?? null },
            { label: 'Regime', value: regime },
          ]} />

          {b?.indexes?.length ? (
            <div className="sys-scroll-x" style={{ marginTop: 'var(--d-3)' }}>
              <table className="sys-table sys-table--compact wl">
                <thead>
                  <tr>
                    <th>Index</th>
                    <th className="num">Last</th>
                    <th className="num">1 day</th>
                    <th className="num">1 week</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {b.indexes.map((i) => (
                    <tr key={i.symbol}>
                      <td>
                        <Link href={`/terminal/security?symbol=${encodeURIComponent(i.symbol)}`} className="wl__sym">
                          {i.symbol}
                        </Link>
                      </td>
                      <td className="num"><Value value={i.price ?? null} kind="currency" /></td>
                      <td className="num"><Value value={i.change_1d ?? null} kind="percent" digits={2} signed tone /></td>
                      <td className="num"><Value value={i.change_1w ?? null} kind="percent" digits={2} signed tone /></td>
                      <td>{i.source ? <Status state="live" label={i.source} /> : <span className="sys-meta">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <StateBlock
              state="unavailable"
              title="No index quotes were returned"
              detail="The breadth reading above is unaffected; only the index tape is missing."
            />
          )}
        </>
      )}
    </Panel>
  )
}
