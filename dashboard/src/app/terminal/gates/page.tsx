import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import GateMatrix from '@/components/terminal/models/GateMatrix'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Gates — miniAladdin',
  description: 'Every registered model against every promotion threshold, and which gates nothing has cleared.',
}

export default function GatesPage() {
  return (
    <Workbench
      title="Gates"
      subtitle="what blocks everything"
      rail={[
        { label: 'Registry', state: 'recorded', detail: '103 entries' },
        { label: 'Production', state: 'unavailable', detail: 'none armed' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Not why one model is blocked — which gate blocks all of them.
            </p>
          </Panel>
          <Panel title="Why the column totals matter">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A gate no model has ever cleared is a statement about the research
              programme, not about any model in it. More search cannot move a
              threshold that nothing has met; either the measurement is missing or
              the bar is where it should be and the answer is no.
            </p>
          </Panel>
          <Panel title="Failed against never measured">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Both count as unmet, and they call for different work. A recorded
              value that missed needs a better model. A value never recorded needs
              a measurement — and treating the second as passing is how an
              unmeasured model reaches production.
            </p>
          </Panel>
        </>
      }
    >
      <GateMatrix />
    </Workbench>
  )
}
