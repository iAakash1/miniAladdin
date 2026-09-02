import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Handbook from '@/components/terminal/methodology/Handbook'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Handbook — miniAladdin',
  description: 'Every reported measure with its unit, annualisation, inputs and failure conditions, generated from the engine.',
}

export default function HandbookPage() {
  return (
    <Workbench
      title="Handbook"
      subtitle="how every number is computed"
      rail={[{ label: 'Source', state: 'recorded', detail: 'generated from the engine' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              How a number was computed, in what unit, and what would make it wrong.
            </p>
          </Panel>
          <Panel title="Derived, not written">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Units, annualisation, inputs and applicability are read from the risk
              engine&apos;s methodology table. A handbook maintained by hand is wrong
              the first time a convention changes, and a wrong handbook is worse
              than none.
            </p>
          </Panel>
          <Panel title="Fails when">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The field that earns its place. A list of assumptions helps only a
              reader who is told what breaks them.
            </p>
          </Panel>
        </>
      }
    >
      <Handbook />
    </Workbench>
  )
}
