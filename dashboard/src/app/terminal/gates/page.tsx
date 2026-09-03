import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import GateMatrix from '@/components/terminal/models/GateMatrix'
import ValidationLadder from '@/components/terminal/models/ValidationLadder'
import HoldoutPreflight from '@/components/terminal/models/HoldoutPreflight'
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
          <Panel title="Who decides">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Promotion is evaluated by <code className="sys-mono">ModelRegistry.promote()</code>,
              which refuses a transition whose evidence is absent as well as one
              whose numbers fail. This page renders that decision. It never makes
              it, and nothing measured here can change it.
            </p>
          </Panel>
          <Panel title="Two kinds of gate on this page">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Promotion gates ask whether a model earned production. The
              preflight asks whether the study is clean enough for its holdout to
              mean anything — and clearing it opens nothing. Spending the holdout
              is an explicit human run under the contract.
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
      <ValidationLadder />
      <GateMatrix />
      {/* A different question from the two above: not whether a model earned
          production, but whether the study underneath it is clean enough for
          its holdout to mean anything. A study that fails here cannot be
          rescued by a better model. */}
      <HoldoutPreflight />
    </Workbench>
  )
}
