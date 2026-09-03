import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import FactorWorkbench from '@/components/terminal/factors2/FactorWorkbench'
import Ablation from '@/components/terminal/factors2/Ablation'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Factors — miniAladdin',
  description: 'Factor evaluations with the overlap correction made visible, and redundancy reported with its pair coverage.',
}

export default function FactorLabPage() {
  return (
    <Workbench
      title="Factors"
      subtitle="what explains returns"
      rail={[
        { label: 'Lab', state: 'recorded', detail: 'built on request' },
        { label: 'Universe', state: 'recorded', detail: 'point-in-time membership' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Whether a factor has predictive power that survives the correction
              for its own overlapping labels.
            </p>
          </Panel>
          <Panel title="Overlap inflation">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A 21-session label sampled every 5 sessions shares information with
              its four neighbours. A t-statistic that ignores that counts the same
              evidence more than once. Both figures are shown, so how close the
              naive reading came to a false positive is visible.
            </p>
          </Panel>
          <Panel title="Pair coverage">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A factor pair never observed together enters the eigenvalue
              calculation as zero correlation. That understates redundancy and so
              overstates independence — the flattering direction — which is why
              coverage travels with the number and the verdict is withheld below
              75%.
            </p>
          </Panel>
        </>
      }
    >
      <FactorWorkbench />
      {/* Which data families earn their place. The answer this study reached is
          that none of the added ones did, which is the most commercially
          inconvenient result in it and therefore the one that gets a panel
          rather than a footnote. */}
      <Ablation />
    </Workbench>
  )
}
