'use client'

/**
 * The option chain, to whatever depth the provider actually permits.
 *
 * Laid out around the strike because that is the axis a reader navigates: calls
 * to the left, puts to the right, strikes down the middle ascending. A flat
 * table of contracts sorted by symbol is a list of rows; this is a chain.
 *
 * Two rules govern every cell.
 *
 * A missing field is an em dash, never a zero. An option chain is mostly
 * holes — contracts that did not trade, contracts with no two-sided market,
 * contracts the provider declined to model — and a zero bid is a statement
 * about a market while a missing bid is the absence of one. The adapter
 * already refuses to substitute; this refuses to render one as the other.
 *
 * And the two zeros that *are* real are kept. Volume and open interest come
 * back as literal zeros for a contract that genuinely did not trade, and that
 * is an observation worth showing.
 *
 * Status is not "we have no data". Options are supported by one provider in
 * this stack, so an absent chain has three quite different explanations —
 * unconfigured, asked-and-refused, or genuinely no listed contracts — and the
 * endpoint distinguishes them.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { readResource } from '@/lib/resource'

interface Contract {
  contract: string
  expiration: string
  strike: number
  contract_type: string
  bid?: number | null
  ask?: number | null
  last_price?: number | null
  day_volume?: number | null
  open_interest?: number | null
  implied_volatility?: number | null
  delta?: number | null
  quote_timeframe?: string | null
}

interface Chain {
  ticker: string
  contracts: Contract[]
  expirations: string[]
  strikes: number[]
  source: string | null
  delayed?: boolean | null
  status: string
  reason?: string
  provider_configured?: boolean
}

/** A figure the provider declined to supply. Never a zero. */
function Cell({ value, kind = 'currency', digits }: {
  value: number | null | undefined
  kind?: 'currency' | 'count' | 'percent' | 'ratio'
  digits?: number
}) {
  if (value === null || value === undefined) {
    return <span className="sys-null" title="not returned by the provider">—</span>
  }
  return <Value value={value} kind={kind} digits={digits} />
}

export default function Options({ symbol, underlyingPrice }: {
  symbol: string
  /** The last price, used only to mark where the money is. */
  underlyingPrice?: number | null
}) {
  const [chain, setChain] = useState<{ for: string; d: Chain } | { for: string; error: string } | null>(null)
  const [expiry, setExpiry] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    readResource<Chain>(`/api/options/${encodeURIComponent(symbol)}`, 'snapshot')
      .then((d) => { if (alive) setChain({ for: symbol, d }) })
      .catch((e: Error) => { if (alive) setChain({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = chain?.for === symbol ? chain : null
  if (!settled) return <Panel title="Options" state="waking"><StateBlock state="waking" title="Reading the option chain" /></Panel>

  if ('error' in settled) {
    return (
      <Panel title="Options" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The option chain could not be read"
          detail={`${settled.error}. Nothing is shown in its place.`}
        />
      </Panel>
    )
  }

  const d = settled.d

  if (d.status !== 'live' || !d.contracts.length) {
    return (
      <EmptyLine label="Options">
        {d.reason ?? 'No option chain was returned for this security.'}
        {' '}
        {d.provider_configured === false
          ? 'This is a deployment configuration, not a statement that the security has no listed options.'
          : 'That is what the provider returned, not a claim that none are listed.'}
      </EmptyLine>
    )
  }

  const expirations = d.expirations
  const active = expiry && expirations.includes(expiry) ? expiry : expirations[0]
  const forExpiry = d.contracts.filter((c) => c.expiration === active)

  const calls = new Map(forExpiry.filter((c) => c.contract_type === 'call').map((c) => [c.strike, c]))
  const puts = new Map(forExpiry.filter((c) => c.contract_type === 'put').map((c) => [c.strike, c]))
  const strikes = [...new Set(forExpiry.map((c) => c.strike))].sort((a, b) => a - b)

  return (
    <Panel
      title="Options"
      subtitle={`${forExpiry.length} contracts · ${active}`}
      state={d.delayed ? 'stale' : 'live'}
      actions={
        <div className="sys-run">
          {expirations.slice(0, 8).map((e) => (
            <button
              key={e}
              type="button"
              className={`sys-btn sys-btn--micro${e === active ? ' is-active' : ''}`}
              aria-pressed={e === active}
              onClick={() => setExpiry(e)}
            >
              {e.slice(2)}
            </button>
          ))}
        </div>
      }
      flush
    >
      {d.delayed ? (
        <Prose size="fine">
          These quotes carry the provider&apos;s delayed timeframe, not real
          time. A chain is only as current as its least current contract.
        </Prose>
      ) : null}

      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact opt">
          <thead>
            <tr>
              <th scope="col" className="num">OI</th>
              <th scope="col" className="num">Vol</th>
              <th scope="col" className="num">IV</th>
              <th scope="col" className="num">Bid</th>
              <th scope="col" className="num">Ask</th>
              <th scope="col" className="num opt__strike">Strike</th>
              <th scope="col" className="num">Bid</th>
              <th scope="col" className="num">Ask</th>
              <th scope="col" className="num">IV</th>
              <th scope="col" className="num">Vol</th>
              <th scope="col" className="num">OI</th>
            </tr>
          </thead>
          <tbody>
            {strikes.map((k) => {
              const c = calls.get(k)
              const p = puts.get(k)
              // Where the underlying sits. Marked once, on the first strike at
              // or above the price, so the reader can see the money without
              // the product asserting moneyness per contract.
              const atMoney = underlyingPrice != null
                && k >= underlyingPrice
                && !strikes.some((s) => s >= underlyingPrice && s < k)
              return (
                <tr key={k} className={atMoney ? 'opt__atm' : undefined}>
                  <td className="num"><Cell value={c?.open_interest} kind="count" digits={0} /></td>
                  <td className="num"><Cell value={c?.day_volume} kind="count" digits={0} /></td>
                  <td className="num"><Cell value={c?.implied_volatility != null ? c.implied_volatility * 100 : null} kind="percent" digits={1} /></td>
                  <td className="num"><Cell value={c?.bid} /></td>
                  <td className="num"><Cell value={c?.ask} /></td>
                  <td className="num opt__strike">
                    <Inspectable refValue={{
                      label: `${symbol} ${active} ${k} strike`,
                      display: String(k),
                      source: d.source ?? undefined,
                      method: 'listed contracts at this strike, as the provider returned them',
                      status: d.delayed ? 'stale' : 'live',
                      freshness: d.delayed ? 'delayed quotes' : 'real-time quotes',
                      note: [c?.contract, p?.contract].filter(Boolean).join(' · '),
                    }}>
                      {k}
                    </Inspectable>
                  </td>
                  <td className="num"><Cell value={p?.bid} /></td>
                  <td className="num"><Cell value={p?.ask} /></td>
                  <td className="num"><Cell value={p?.implied_volatility != null ? p.implied_volatility * 100 : null} kind="percent" digits={1} /></td>
                  <td className="num"><Cell value={p?.day_volume} kind="count" digits={0} /></td>
                  <td className="num"><Cell value={p?.open_interest} kind="count" digits={0} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="opt__foot">
        <span>calls left · puts right</span>
        <Status state={d.delayed ? 'stale' : 'live'} label={d.source ?? 'provider'} />
      </div>
    </Panel>
  )
}
