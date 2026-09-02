import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ExperimentDiff from '@/components/terminal/compare/ExperimentDiff'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Difference — miniAladdin',
  description: 'What changed between two experiments, and what a difference does not license you to conclude.',
}

export default function DiffPage() {
  return (
    <Workbench
      title="Difference"
      subtitle="what changed between two experiments"
      rail={[{ label: 'Record', state: 'recorded', detail: 'immutable artifacts' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              How two experiments differ in design, scale and inputs.
            </p>
          </Panel>
          <Panel title="What it does not answer">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Why a result moved. Two experiments differ in many ways at once, so
              attributing a change to any single one of them is not something a
              diff can support. Nothing here is labelled a cause.
            </p>
          </Panel>
          <Panel title="The trial count">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The field to read first. If it grew, every significance claim in the
              later experiment faces a higher bar — so an unchanged number can
              still mean weaker evidence.
            </p>
          </Panel>
        </>
      }
    >
      <ExperimentDiff />
    </Workbench>
  )
}
