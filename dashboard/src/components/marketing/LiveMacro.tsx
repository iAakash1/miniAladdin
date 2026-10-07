'use client'

import { useEffect, useState } from 'react'

import { fetchMacroClient } from '@/lib/api'
import type { Macro } from '@/lib/types'

function pct(v: number | null, digits = 2): string {
  return v === null || !Number.isFinite(v) ? '—' : `${v.toFixed(digits)}%`
}

/**
 * The macro regime the engine is reading now, from FRED. Fetched when the
 * page loads, unlike the recorded run above it — but FRED publishes daily and
 * monthly observations, so these are the latest published readings and not a
 * live feed. Each carries its observation date, and the strip disappears
 * rather than showing a stale reading as current.
 */
export default function LiveMacro() {
  const [state, setState] = useState<{ m?: Macro; failed?: boolean } | null>(null)

  useEffect(() => {
    let alive = true
    fetchMacroClient()
      .then((m) => { if (alive) setState(m ? { m } : { failed: true }) })
      .catch(() => { if (alive) setState({ failed: true }) })
    return () => { alive = false }
  }, [])

  if (state?.failed || state?.m?.status === 'UNAVAILABLE') return null
  const m = state?.m
  const dates = m?.observationDates ?? {}
  const cells: Array<[string, string, string | undefined]> = m ? [
    ['Regime', m.status.toLowerCase(), undefined],
    ['10y – 2y spread', pct(m.yieldSpread), dates.yield_spread],
    ['CPI, year over year', pct(m.cpi), dates.inflation_rate],
    ['Fed funds', pct(m.fedRate), dates.fed_funds_rate],
    ['Risk multiplier', m.srm === null ? '—' : m.srm.toFixed(2), undefined],
  ] : []

  return (
    <section className="lp-live" aria-label="Macro conditions the engine is reading now">
      <div className="lp-container lp-live__row">
        <span className="lp-live__k">
          <span className="dot" data-tone={m ? (m.stale ? 'warn' : 'pos') : 'muted'} aria-hidden />
          Macro regime · latest FRED observations{m?.stale ? ' · stale' : ''}
        </span>
        {m ? (
          <dl className="lp-live__cells">
            {cells.map(([k, v, d]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd><span className="sys-num">{v}</span>{d ? <small>{d}</small> : null}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <div className="lp-live__cells" aria-hidden>
            {[0, 1, 2, 3, 4].map((i) => <span key={i} className="sys-skeleton" style={{ width: 96, height: 30 }} />)}
          </div>
        )}
      </div>
    </section>
  )
}
