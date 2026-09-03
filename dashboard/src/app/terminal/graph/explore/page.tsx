import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import GraphExplorer from '@/components/terminal/GraphExplorer'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Explore — miniAladdin',
  description: 'Walk the relationship graph outward from a starting entity.',
}

export default function Page() {
  return (
    <Workbench title="Explore" subtitle="walk outward from one thing"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What sits one, two or three hops from a given entity, and by which relationships.
            </p>
          </Panel>
          <Panel title="Distance is not influence">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Hop count measures how the graph was assembled, not how much one company affects another. A close neighbour may matter less than a distant one.
            </p>
          </Panel>
        </>
      }
    >
      <GraphExplorer />
    </Workbench>
  )
}
