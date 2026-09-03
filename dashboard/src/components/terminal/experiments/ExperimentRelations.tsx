'use client'

/**
 * What an experiment is connected to, from its own artifact.
 *
 * The edges are the features it trained on, the datasets it read and the models
 * it evaluated — each named by the recorded run rather than inferred from it.
 * An experiment that names none of them shows that, because an experiment with
 * no recorded lineage is a different and more interesting fact than one whose
 * lineage failed to load.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock } from '@/components/system'
import { KINDS } from '@/lib/research/objects'
import { experimentRelations, type ExperimentEdges, type Relation } from '@/lib/research/relations'

type State =
  | { status: 'reading' }
  | { status: 'ready'; relations: Relation[] }
  | { status: 'unavailable'; detail: string }

export default function ExperimentRelations({ experimentId = 'EXP-006' }: { experimentId?: string }) {
  const [state, setState] = useState<State>({ status: 'reading' })

  useEffect(() => {
    let alive = true
    fetch(`/api/quant/experiments/${encodeURIComponent(experimentId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`the artifact request returned ${r.status}`))))
      .then((d: ExperimentEdges) => {
        if (alive) setState({ status: 'ready', relations: experimentRelations(d) })
      })
      .catch((e: Error) => { if (alive) setState({ status: 'unavailable', detail: e.message }) })
    return () => { alive = false }
  }, [experimentId])

  return (
    <Panel
      title="Related objects"
      subtitle={experimentId}
      state={state.status === 'ready' ? 'recorded' : state.status === 'reading' ? 'waking' : 'unavailable'}
    >
      {state.status === 'reading' ? (
        <StateBlock state="waking" title="Reading the experiment artifact" />
      ) : state.status === 'unavailable' ? (
        <StateBlock
          state="unavailable"
          title="The lineage could not be read"
          detail={`${state.detail}. No counts are shown, because a zero here would be indistinguishable from a measured one.`}
        />
      ) : state.relations.length === 0 ? (
        <StateBlock
          state="recorded"
          title="This experiment records no lineage"
          detail="The artifact was read and names neither the features it trained on, the datasets it read, nor the models it evaluated. That is a gap in the record, not a gap in the display."
        />
      ) : (
        <>
          <ul className="sys-related">
            {state.relations.map((r) => (
              <li key={`${r.kind}-${r.verb}`}>
                <Link href={r.href} className="sys-related__link">
                  <span className="sys-related__kind">
                    {r.count === 1 ? KINDS[r.kind].plural.replace(/s$/, '') : KINDS[r.kind].plural}
                  </span>
                  <span className="sys-related__count">{r.count}</span>
                  <span className="sys-related__verb">{r.verb}</span>
                </Link>
                {r.sample.length ? (
                  <span className="sys-related__sample">
                    {r.sample.join(', ')}
                    {r.count > r.sample.length ? `, and ${r.count - r.sample.length} more` : ''}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <Prose size="fine">
            Each edge is named by the experiment&rsquo;s own recorded run. Nothing
            here is connected because it seemed like it should be.
          </Prose>
        </>
      )}
    </Panel>
  )
}
