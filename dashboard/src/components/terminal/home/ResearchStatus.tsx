'use client'

/**
 * The research programme, in one line.
 *
 * It used to be the hero of the terminal: PBO, deflated Sharpe, eight gates,
 * 873 configurations, a leaderboard of retired models. All of that is true and
 * none of it is what someone opening a terminal needs first.
 *
 * The honest summary is short. No production model is deployed, and the
 * archive records why. A reader who wants the eight gates can follow the link;
 * a reader who wants a price should not have to read past them to get one.
 *
 * Nothing here is softened. The verdict comes from the selection artifact and
 * says exactly what it says.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Panel, Prose, Status } from '@/components/system'
import { readResource } from '@/lib/resource'

interface Selection {
  experiment?: string
  verdict?: { status?: string; passed?: boolean; gates?: { passed: boolean }[] }
}

export default function ResearchStatus() {
  const [state, setState] = useState<
    { s: 'reading' } | { s: 'ready'; d: Selection } | { s: 'unavailable' }
  >({ s: 'reading' })

  useEffect(() => {
    let alive = true
    readResource<Selection>('/api/quant/selection/EXP-007', 'artifact')
      .then((d) => { if (alive) setState({ s: 'ready', d }) })
      .catch(() => { if (alive) setState({ s: 'unavailable' }) })
    return () => { alive = false }
  }, [])

  const verdict = state.s === 'ready' ? state.d.verdict : undefined
  const unmet = verdict?.gates?.filter((g) => !g.passed).length ?? null

  return (
    <Panel
      title="Research"
      /* Not `passed ? candidate : blocked`. A failed read has no verdict, and
         rendering one from an absent fetch is the error this product's own
         sweep exists to catch — it caught this line. */
      state={
        state.s === 'ready' && verdict
          ? (verdict.passed ? 'candidate' : 'blocked')
          : state.s === 'reading' ? 'waking' : 'unavailable'
      }
    >
      <div className="home-research">
        <Status
          state={state.s === 'unavailable' ? 'unavailable' : verdict?.passed ? 'candidate' : 'blocked'}
          label={
            state.s === 'reading' ? 'reading'
              : state.s === 'unavailable' ? 'status unavailable'
                : verdict?.status ?? 'no production candidate'
          }
        />
        <span className="sys-meta">
          {state.s === 'ready' && unmet !== null
            ? `${unmet} of ${verdict?.gates?.length ?? 0} promotion gates unmet on ${state.d.experiment ?? 'EXP-007'}`
            : state.s === 'unavailable'
              ? 'the selection artifact could not be read'
              : 'reading the selection artifact'}
        </span>
        <Link href="/terminal/evidence" className="sys-meta sys-meta--strong">
          open the research archive →
        </Link>
      </div>
      <Prose size="fine">
        No model is deployed, so nothing here scores a security. The archive
        keeps the experiments, the gates and the reasons intact.
      </Prose>
    </Panel>
  )
}
