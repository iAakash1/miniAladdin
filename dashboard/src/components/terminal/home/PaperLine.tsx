'use client'

/**
 * The paper account, on one line, on the way in.
 *
 * Home's job is to say what matters now. A simulated account with three
 * positions matters; a rectangle apologising that no broker is configured
 * does not. So this is a line either way — the figures when there is an
 * account, one sentence when there is not.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { EmptyLine, Value } from '@/components/system'
import { fetchPaperAccount, fetchPaperPositions, fetchPaperStatus, money } from '@/lib/paper'

interface Loaded {
  equity: number | null
  dayChange: number | null
  positions: number | null
}

type State =
  | { s: 'reading' }
  | { s: 'unconfigured'; reason: string | null }
  | { s: 'ready'; d: Loaded }
  | { s: 'unavailable'; reason: string }

export default function PaperLine() {
  const [state, setState] = useState<State>({ s: 'reading' })

  useEffect(() => {
    let alive = true
    fetchPaperStatus()
      .then(async (status) => {
        if (!alive) return
        if (!status.configured) {
          setState({ s: 'unconfigured', reason: status.reason })
          return
        }
        const [acct, pos] = await Promise.all([fetchPaperAccount(), fetchPaperPositions()])
        if (!alive) return
        const equity = money(acct.account.equity)
        const last = money(acct.account.last_equity)
        setState({
          s: 'ready',
          d: {
            equity,
            // The broker gives today's equity and yesterday's close; the
            // difference is the only arithmetic here, and only because it
            // does not send it directly.
            dayChange: equity !== null && last !== null ? equity - last : null,
            positions: pos.positions.length,
          },
        })
      })
      .catch((e: Error) => { if (alive) setState({ s: 'unavailable', reason: e.message }) })
    return () => { alive = false }
  }, [])

  if (state.s === 'reading') return null

  if (state.s === 'unconfigured') {
    return (
      <EmptyLine label="Paper">
        {state.reason ?? 'Alpaca paper credentials are not configured.'} Market
        data, search and research do not depend on it.
      </EmptyLine>
    )
  }

  if (state.s === 'unavailable') {
    return (
      <EmptyLine label="Paper">
        The broker could not be reached — {state.reason}. Your watchlist and
        research are unaffected.
      </EmptyLine>
    )
  }

  return (
    <section className="pline" aria-label="Paper account">
      <h2 className="pline__k">Paper</h2>
      <div className="pline__v">
        <span className="pline__eq"><Value value={state.d.equity} kind="currency" /></span>
        <span className="pline__d"><Value value={state.d.dayChange} kind="currency" signed tone /></span>
        <span className="pline__n">
          {state.d.positions} {state.d.positions === 1 ? 'position' : 'positions'}
        </span>
      </div>
      <Link href="/terminal/paper" className="band__more">open paper account</Link>
    </section>
  )
}
