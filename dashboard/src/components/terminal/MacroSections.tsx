'use client'

import { useMemo } from 'react'
import Card from '@/components/ui/Card'
import Section from '@/components/ui/Section'
import { groupMacroCards, MACRO_GROUP_TITLES, type MacroCard, type MacroGroupId } from '@/lib/dashboardInsights'
import { fmtNum } from '@/lib/format'

function CardGrid({ cards }: { cards: MacroCard[] }) {
  if (cards.length === 0) return null
  return (
    <div className="dash-grid">
      {cards.map((card) => (
        <Card
          key={card.id}
          title={card.label}
          value={fmtNum(card.value, 2)}
          unit={card.unit || undefined}
          change={card.change !== null ? `${card.change > 0 ? '+' : ''}${fmtNum(card.change, 2)}` : null}
          direction={card.direction}
          trend={card.trend}
          explain={card.explain}
          previous={card.previous !== null ? fmtNum(card.previous, 2) : null}
        />
      ))}
    </div>
  )
}

const GROUP_ORDER: MacroGroupId[] = ['economic', 'rates', 'inflation']

/**
 * The detailed macro board, reorganized from one flat 14-card wall into
 * three named, collapsed-by-default groups (Economic Conditions / Interest
 * Rates / Inflation). The hero already surfaces Fed/Inflation/SRM up
 * front, so everything here is deliberately progressive disclosure —
 * reference detail for whoever wants to drill in, not the first thing
 * anyone has to read.
 */
export default function MacroSections({ cards }: { cards: MacroCard[] }) {
  const groups = useMemo(() => groupMacroCards(cards), [cards])
  if (cards.length === 0) return null

  return (
    <>
      {GROUP_ORDER.map((groupId) => (
        groups[groupId].length > 0 && (
          <Section
            key={groupId}
            id={`macro-group-${groupId}`}
            title={MACRO_GROUP_TITLES[groupId]}
            summary={
              <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
                {groups[groupId].length} indicators
              </span>
            }
          >
            <CardGrid cards={groups[groupId]} />
          </Section>
        )
      ))}
    </>
  )
}
