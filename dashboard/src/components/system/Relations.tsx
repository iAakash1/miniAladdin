/**
 * Nearby objects, shown on the masthead.
 *
 * A count turns a name into a node. "Used by 4 models" is the difference
 * between a feature that is a row in a catalogue and one that is load-bearing,
 * and a feature used by nothing is worth seeing too — it is either new or
 * abandoned, and both matter before building on it.
 *
 * Nothing is rendered where the registry could not be read. A count of zero
 * from a failed fetch would be a lie, and this is the kind of number a reader
 * would take at face value.
 */
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { KINDS, type ResearchObject } from '@/lib/research/objects'
import { cachedGraph, loadGraph, relationsFor, type Relation } from '@/lib/research/relations'

export function Relations({ object }: { object: ResearchObject }) {
  const [relations, setRelations] = useState<Relation[] | null>(
    () => (cachedGraph() ? relationsFor(object, cachedGraph()) : null),
  )

  useEffect(() => {
    let alive = true
    loadGraph().then((g) => { if (alive) setRelations(g ? relationsFor(object, g) : []) })
    return () => { alive = false }
  }, [object])

  if (!relations?.length) return null

  return (
    <div className="sys-relations">
      {relations.map((r) => (
        <Link
          key={`${r.kind}-${r.verb}`}
          href={r.href}
          className="sys-relation"
          title={r.sample.length ? `${r.sample.join(', ')}${r.count > r.sample.length ? `, and ${r.count - r.sample.length} more` : ''}` : undefined}
        >
          <span className="sys-relation__verb">{r.verb}</span>
          <span className="sys-relation__count">{r.count}</span>
          <span className="sys-relation__kind">
            {r.count === 1 ? KINDS[r.kind].plural.replace(/s$/, '') : KINDS[r.kind].plural}
          </span>
        </Link>
      ))}
    </div>
  )
}
