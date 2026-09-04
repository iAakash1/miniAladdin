'use client'

/**
 * What actually moved.
 *
 * The band above says the market is up and breadth is 73%. This says which
 * parts of it, which is the difference between knowing the index closed green
 * and knowing the day was energy and healthcare while industrials fell six
 * per cent — the same close, two entirely different mornings.
 *
 * Eleven rows, ordered by the shorter horizon, each carrying its own ninety
 * sessions as a line. The sparkline is not decoration: a sector up four per
 * cent that has been falling for two months is not the same object as one up
 * four per cent that has been rising, and the number alone cannot tell them
 * apart.
 *
 * Reads the same market snapshot the band does, through the shared cache, so
 * the two cannot disagree and the page issues one request for both.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Value } from '@/components/system'
import { Sparkline } from '@/components/system/charts'
import { readResource } from '@/lib/resource'

interface Sector {
  symbol: string
  name?: string | null
  strength_21d?: number | null
  momentum_63d?: number | null
  above_50d?: boolean | null
  history?: number[] | null
}

type Answer = { sectors: Sector[] } | { error: string }

export default function SectorMovers() {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    readResource<{ sectors?: Sector[] }>('/api/dashboard', 'snapshot')
      .then((d) => { if (alive) setAnswer({ sectors: d.sectors ?? [] }) })
      .catch((e: Error) => { if (alive) setAnswer({ error: e.message }) })
    return () => { alive = false }
  }, [])

  const sectors = answer && 'sectors' in answer ? answer.sectors : []
  const failed = answer && 'error' in answer ? answer.error : null

  // Ordered by the near horizon, strongest first. A sector with no 21-day
  // reading sorts last rather than as a zero.
  const rows = [...sectors].sort((a, b) => {
    const x = typeof a.strength_21d === 'number' ? a.strength_21d : -Infinity
    const y = typeof b.strength_21d === 'number' ? b.strength_21d : -Infinity
    return y - x
  })

  if (failed || (answer && !rows.length)) return null

  return (
    <section className="movers" aria-label="Sector movement">
      <div className="movers__head">
        <h2 className="band__title">Sectors</h2>
        <span className="band__when">
          {answer ? '11 SPDR sector funds · 21 and 63 sessions · lines rebased to 100' : 'reading…'}
        </span>
      </div>

      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact movers__t">
          <thead>
            <tr>
              <th>Sector</th>
              <th className="num">21d</th>
              <th className="num">63d</th>
              <th className="movers__spark">90 sessions</th>
              <th className="num">50-day</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.symbol}>
                <td>
                  <Link
                    href={`/terminal/security?symbol=${encodeURIComponent(s.symbol)}`}
                    className="wl__sym"
                  >
                    {s.symbol}
                  </Link>
                  <span className="movers__name">{s.name ?? ''}</span>
                </td>
                <td className="num">
                  <Value value={s.strength_21d ?? null} kind="percent" digits={1} signed tone />
                </td>
                <td className="num">
                  <Value value={s.momentum_63d ?? null} kind="percent" digits={1} signed tone />
                </td>
                <td className="movers__spark">
                  <Sparkline values={s.history ?? []} width={132} height={20} />
                </td>
                <td className="num">
                  {/* Above or below, never a tick and a cross: the words say
                      which side of the average it is on without needing a key. */}
                  {s.above_50d == null
                    ? <span className="sys-null">—</span>
                    : <span className={s.above_50d ? 'movers__above' : 'movers__below'}>
                      {s.above_50d ? 'above' : 'below'}
                    </span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
