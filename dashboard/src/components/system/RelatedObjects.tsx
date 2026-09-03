'use client'

/**
 * The canonical "related objects" section.
 *
 * Every research object sits in a network: a feature is used by models, a model
 * reads datasets and was tested in experiments, a dataset feeds features. Those
 * edges exist in the artifacts — a registry entry names its features, its
 * datasets, its label — and inverting them is the only inference made here.
 *
 * Nothing is asserted that a record does not state. A model and a security are
 * not related because both mention momentum; they are related when a record
 * names both ends of the edge, and not otherwise.
 *
 * Three states, kept apart:
 *
 *  - **reading** — the registry has been asked and has not answered
 *  - **unavailable** — it was asked and refused, so no count is shown at all,
 *    because a zero here is the kind of number a reader takes at face value
 *  - **none recorded** — it answered, and this object has no edges. That is a
 *    finding: a feature used by nothing is either new or abandoned, and both
 *    are worth knowing before building on it.
 *
 * The compact strip on an object masthead is the same data in one line. This is
 * the section a reader navigates from.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock } from '@/components/system'
import { KINDS, type ResearchObject } from '@/lib/research/objects'
import {
  cachedGraph, graphFailure, loadGraph, relationsFor, type Relation,
} from '@/lib/research/relations'

type State =
  | { status: 'reading' }
  | { status: 'ready'; relations: Relation[] }
  | { status: 'unavailable'; detail: string }

export function RelatedObjects({ object }: { object: ResearchObject }) {
  const [state, setState] = useState<State>(() => {
    const g = cachedGraph()
    return g ? { status: 'ready', relations: relationsFor(object, g) } : { status: 'reading' }
  })

  useEffect(() => {
    let alive = true
    loadGraph().then((g) => {
      if (!alive) return
      setState(g
        ? { status: 'ready', relations: relationsFor(object, g) }
        : { status: 'unavailable', detail: graphFailure() ?? 'the registry could not be read' })
    })
    return () => { alive = false }
  }, [object])

  return (
    <Panel
      title="Related objects"
      subtitle={object.label}
      state={state.status === 'ready' ? 'recorded' : state.status === 'reading' ? 'waking' : 'unavailable'}
    >
      {state.status === 'reading' ? (
        <StateBlock state="waking" title="Reading the registry" />
      ) : state.status === 'unavailable' ? (
        <StateBlock
          state="unavailable"
          title="Relationships could not be read"
          detail={`${state.detail}. No counts are shown, because a zero here would be indistinguishable from a measured one.`}
        />
      ) : state.relations.length === 0 ? (
        <StateBlock
          state="recorded"
          title="No relationships are recorded for this object"
          detail="The registry was read and names no edges at either end. For a feature or a dataset that is itself a finding — it is either new or no longer used."
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
            Every edge here is named by a record — a registry entry listing its
            features, its datasets, its label. Nothing is related to anything
            because it seems like it should be.
          </Prose>
        </>
      )}
    </Panel>
  )
}
