import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ModelWorkbench from '@/components/terminal/models2/ModelWorkbench'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Models — miniAladdin',
  description: 'What each model is, what it learned, and how much of the training fit survived out of sample.',
}

export default function LabPage() {
  return (
    <Workbench
      title="Models"
      subtitle="what was learned, and what survived"
      rail={[
        { label: 'Study', state: 'recorded', detail: 'recorded artifact' },
        { label: 'Production', state: 'unavailable', detail: 'none armed' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What a model is and what it learned. Whether it can be trusted is a
              separate question, answered in Evidence.
            </p>
          </Panel>
          <Panel title="The gap is the headline">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A training IC of 0.19 against a validation IC of 0.03 is not a good
              model with a caveat. Roughly a sixth of the fit survived; the rest
              was memorisation, and the validation figure is the model&apos;s real
              signal.
            </p>
          </Panel>
          <Panel title="Why this is not a ranking">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The best model on a label is the best of the ones tried, which is a
              statement about the search as much as about the model. The
              multiple-testing account lives in Signals.
            </p>
          </Panel>
        </>
      }
    >
      <ModelWorkbench />
    </Workbench>
  )
}
