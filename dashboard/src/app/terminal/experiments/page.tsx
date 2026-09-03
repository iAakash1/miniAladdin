import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ExperimentRegistry from '@/components/terminal/experiments/ExperimentRegistry'
import SearchLab from '@/components/terminal/experiments/SearchLab'
import ExperimentRelations from '@/components/terminal/experiments/ExperimentRelations'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Experiments — miniAladdin',
  description: 'The research record: every experiment, its dataset sources and their point-in-time classification.',
}

export default function ExperimentsPage() {
  return (
    <Workbench
      title="Experiments"
      subtitle="the research record"
      rail={[
        { label: 'Record', state: 'recorded', detail: 'immutable' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What evidence actually exists, and what each piece of it was measured on.
            </p>
          </Panel>
          <Panel title="Void experiments are shown">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              An invalidated experiment is a fact about the record. A registry that
              quietly omits its failures is not a registry, and the count of
              attempts is what the multiple-testing correction is applied to.
            </p>
          </Panel>
        </>
      }
    >
      <ExperimentRegistry />
      {/* The search that produced the candidates above: 873 configurations of
          worker time, and what spending them cost the study in significance.
          A wide search always finds an impressive statistic; the only question
          is whether it beat what noise gives away for free. */}
      <SearchLab />
      <ExperimentRelations />
    </Workbench>
  )
}
