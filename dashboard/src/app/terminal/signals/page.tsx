import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SignalLab from '@/components/terminal/signals/SignalLab'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Signals — miniAladdin',
  description: 'Does the idea work: the multiple-testing account, the finalists that survived the search, and their deflated Sharpe.',
}

export default function SignalsPage() {
  return (
    <Workbench
      title="Signals"
      subtitle="does the idea work"
      rail={[
        { label: 'Search', state: 'recorded', detail: '1,029 cumulative trials' },
        { label: 'Holdout', state: 'blocked', detail: 'sealed' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Whether a signal has predictive power that survives the number of
              ideas tried before it.
            </p>
          </Panel>
          <Panel title="Why trials come first">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The thing that most often makes the answer no is not the idea. It is
              the search. The best of a thousand zero-skill configurations reaches
              a t-statistic near 3.4 by chance alone, so a result of 2.8 is not
              evidence — it is what the search was expected to produce.
            </p>
          </Panel>
          <Panel title="IC is not a return">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              An information coefficient is a cross-sectional rank correlation.
              Predictive power and profitability are kept in separate sections
              here and never in the same row.
            </p>
          </Panel>
        </>
      }
    >
      <SignalLab />
    </Workbench>
  )
}
