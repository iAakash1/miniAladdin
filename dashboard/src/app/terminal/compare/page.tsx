import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ModelCompare from '@/components/terminal/compare/ModelCompare'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Compare — miniAladdin',
  description: 'Side-by-side model comparison, with differences coloured only where the metric declares a direction.',
}

export default function ComparePage() {
  return (
    <Workbench
      title="Compare"
      subtitle="side by side"
      rail={[{ label: 'Registry', state: 'recorded', detail: '103 entries' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              How two or more models differ, field by field, against a baseline.
            </p>
          </Panel>
          <Panel title="Why most deltas are grey">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A difference is coloured only where the metric declares a direction.
              Turnover of 18× is not worse than 6× without knowing the strategy,
              and colouring it red would be an opinion dressed as a measurement.
            </p>
          </Panel>
          <Panel title="Not comparable">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Where one side did not record a field, the cell says n/c. An absent
              value is not a match and not a zero: a model with no deflated Sharpe
              has not tied one that recorded a failing value.
            </p>
          </Panel>
        </>
      }
    >
      <ModelCompare />
    </Workbench>
  )
}
