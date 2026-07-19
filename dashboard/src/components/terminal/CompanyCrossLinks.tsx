'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { TYPE_LABELS, type Entity } from '@/lib/intelligence/entities'
import { relatedLearnTopics, relatedResearch, relatedWatchlists } from '@/lib/intelligence/related'
import { recordRecent } from '@/lib/intelligence/registry'
import { useWatchlists } from '@/lib/watchlists'
import type { Analysis } from '@/lib/types'

/**
 * Related — the no-dead-ends section. A client of the Intelligence OS:
 * every chip is an Entity (same contract, same recents recording as ⌘K),
 * composed from the report's own contents. Renders nothing when there is
 * genuinely nothing related, rather than inventing links.
 */
export default function CompanyCrossLinks({ analysis }: { analysis: Analysis }) {
  const lists = useWatchlists()
  const [research, setResearch] = useState<Entity[]>([])

  useEffect(() => {
    let alive = true
    relatedResearch(analysis.ticker).then((entities) => {
      if (alive) setResearch(entities)
    })
    return () => {
      alive = false
    }
  }, [analysis.ticker])

  const learn = relatedLearnTopics(
    (analysis.technicalIntelligence?.indicators ?? []).map((row) => row.key),
    analysis.streetIntelligence !== null,
  )
  const memberOf = relatedWatchlists(analysis.ticker, lists)

  const groups: Array<{ label: string; items: Entity[] }> = [
    { label: 'Your research', items: research },
    { label: 'Your lists', items: memberOf },
    { label: 'Learn the concepts in this report', items: learn },
  ].filter((group) => group.items.length > 0)

  if (groups.length === 0) return null

  return (
    <section aria-label="Related" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <h3 className="h-panel" style={{ marginBottom: 14 }}>Related</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {groups.map((group) => (
          <div key={group.label}>
            <p className="label" style={{ fontSize: '0.625rem', marginBottom: 8 }}>{group.label}</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {group.items.map((entity) => (
                <Link
                  key={entity.id}
                  href={entity.route}
                  onClick={() => recordRecent(entity)}
                  title={entity.description}
                  className="btn btn--ghost btn--xs"
                  style={{ border: '1px solid var(--line)', textDecoration: 'none' }}
                >
                  {entity.title}
                  <span className="label" style={{ fontSize: '0.5625rem', color: 'var(--faint)' }}>
                    {TYPE_LABELS[entity.type]}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
