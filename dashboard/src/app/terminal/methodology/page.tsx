import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import MethodologyView from '@/components/terminal/MethodologyView'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Methodology — miniAladdin',
  description: 'How each figure in the product is computed, and what it assumes.',
}

export default function Page() {
  return (
    <Workbench title="Methodology" subtitle="how the numbers are made"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              How a statistic is computed, on what data, under which assumptions.
            </p>
          </Panel>
          <Panel title="The handbook is generated">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The measure-by-measure handbook is generated from the engine itself, so it cannot drift from the code. This page is the longer prose account beside it.
            </p>
          </Panel>
        </>
      }
    >
      <MethodologyView />
    </Workbench>
  )
}
