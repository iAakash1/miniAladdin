import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import GraphWorkspace from '@/components/terminal/GraphWorkspace'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Graph — miniAladdin',
  description: 'The relationship graph: what connects to what, and on whose authority.',
}

export default function Page() {
  return (
    <Workbench title="Graph" subtitle="how things connect"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Which entities are linked to which, by what kind of relationship, and where that link came from.
            </p>
          </Panel>
          <Panel title="An edge is a claim">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Every edge carries a provider and a confidence. A relationship asserted by one vendor and unconfirmed by another is drawn, but it is not the same fact as one both agree on.
            </p>
          </Panel>
        </>
      }
    >
      <GraphWorkspace />
    </Workbench>
  )
}
