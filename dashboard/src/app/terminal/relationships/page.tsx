import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Relationships from '@/components/terminal/relationships/Relationships'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Relationships — miniAladdin',
  description: 'Typed relationships between companies, industries and entities, with provider and confidence on every edge.',
}

export default async function RelationshipsPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>
}) {
  const p = await searchParams
  return (
    <Workbench
      title="Relationships"
      subtitle="what connects to what"
      rail={[
        { label: 'Edges', state: 'recorded', detail: 'provider assertions' },
        { label: 'Confidence', state: 'stale', detail: 'not a measurement' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What a company connects to — its industry, its peers, the entities
              around it — and how strongly each connection is asserted.
            </p>
          </Panel>
          <Panel title="Assertions, not measurements">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Every edge is a provider&apos;s claim carrying a confidence and a
              validity window. A relationship asserted at 0.5 by one source is not
              the same claim as one at 0.95 from three, so both travel with the
              edge and confidence is a query filter rather than a display option.
            </p>
          </Panel>
          <Panel title="Why rings, not physics">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The layout is radial by hop distance. A force simulation looks
              impressive and draws the same graph differently every time, so
              nothing can be remembered or pointed at. Here position carries
              information and the same query always draws the same picture.
            </p>
          </Panel>
        </>
      }
    >
      <Relationships initialSymbol={(p.symbol ?? 'AAPL').toUpperCase()} />
    </Workbench>
  )
}
