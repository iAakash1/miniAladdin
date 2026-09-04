'use client'

/**
 * The morning read.
 *
 * Home used to open with two empty rectangles — "No securities on the
 * watchlist yet" and "Nothing opened yet in this browser" — because it was
 * built entirely around the reader's own state, and on a first morning there
 * is none. A terminal whose front page is an apology for being new is a
 * terminal nobody opens twice.
 *
 * The market is the one thing that is always there. It does not depend on
 * anyone having done anything, it is different every morning, and it is the
 * question a research terminal is actually opened to answer. So it leads, and
 * the reader's own names sit underneath it.
 *
 * Composed as a tape rather than a table in a panel: five instruments across,
 * each a column of level over move, then one rule and a single line of market
 * facts. The point is that the whole state of the market is one glance, not
 * one scroll.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Value } from '@/components/system'
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
}

/** Tagged with nothing: home reads one market, and there is only ever one. */
type Answer = { d: Dashboard } | { error: string }

export default function MarketBand() {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    readResource<Dashboard>('/api/dashboard', 'snapshot')
      .then((d) => { if (alive) setAnswer({ d }) })
      .catch((e: Error) => { if (alive) setAnswer({ error: e.message }) })
    return () => { alive = false }
  }, [])

  const d = answer && 'd' in answer ? answer.d : null
  const failed = answer && 'error' in answer ? answer.error : null
  const b = d?.breadth
  const regimeRaw = d?.macro?.regime
  const regime = typeof regimeRaw === 'string'
    ? regimeRaw
    : regimeRaw?.available === false ? null : regimeRaw?.status ?? null

  const indexes = b?.indexes ?? []

  return (
    <section className="band" aria-label="Market">
      <div className="band__head">
        <h2 className="band__title">Market</h2>
        <span className="band__when">
          {failed ? 'unavailable'
            : d?.generated_at ? `as of ${d.generated_at.slice(0, 16).replace('T', ' ')}`
              : 'reading…'}
        </span>
        <Link href="/terminal/market" className="band__more">open market</Link>
      </div>

      {failed ? (
        /* An outage is a sentence, not a box. The rest of home still works and
           putting a bordered rectangle here would suggest otherwise. */
        <p className="band__absent">
          The market snapshot could not be read — {failed}. Nothing is shown in
          its place; your names below are unaffected.
        </p>
      ) : (
        <>
          <div className="band__tape" role="list">
            {indexes.length
              ? indexes.map((i) => (
                <Link
                  role="listitem"
                  key={i.symbol}
                  href={`/terminal/security?symbol=${encodeURIComponent(i.symbol)}`}
                  className="tape"
                  title={i.source ? `via ${i.source}` : undefined}
                >
                  <span className="tape__sym">{i.symbol}</span>
                  <span className="tape__px"><Value value={i.price ?? null} kind="currency" /></span>
                  <span className="tape__chg">
                    <Value value={i.change_1d ?? null} kind="percent" digits={2} signed tone />
                  </span>
                </Link>
              ))
              /* Placeholders keep the tape's height so the line of facts below
                 does not jump when the quotes land. They carry the instrument
                 names, which are fixed, and an em dash where the number goes. */
              : ['SPY', 'QQQ', 'DIA', 'IWM', 'VIX'].map((s) => (
                <span role="listitem" key={s} className="tape tape--pending">
                  <span className="tape__sym">{s}</span>
                  <span className="tape__px">—</span>
                  <span className="tape__chg">—</span>
                </span>
              ))}
          </div>

          <dl className="band__facts">
            <Fact k="Breadth">
              <Value value={b?.breadth_score ?? null} kind="percent" digits={0} />
            </Fact>
            <Fact k="Above 50-day">
              {b?.sectors_above_50d != null && b?.sector_count != null
                ? <span className="band__num">{b.sectors_above_50d} of {b.sector_count}</span>
                : <span className="band__none">—</span>}
            </Fact>
            <Fact k="Leading">{b?.leadership ?? <span className="band__none">—</span>}</Fact>
            <Fact k="Lagging">{b?.laggard ?? <span className="band__none">—</span>}</Fact>
            <Fact k="Regime">{regime ?? <span className="band__none">not recorded</span>}</Fact>
          </dl>
        </>
      )}
    </section>
  )
}

function Fact({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="band__fact">
      <dt>{k}</dt>
      <dd>{children}</dd>
    </div>
  )
}
