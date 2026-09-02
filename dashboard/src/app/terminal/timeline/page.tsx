import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ResearchTimeline from '@/components/terminal/timeline/ResearchTimeline'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Timeline — miniAladdin',
  description: 'What was recorded, when: model registrations, status changes and research memos.',
}

export default function TimelinePage() {
  return (
    <Workbench
      title="Timeline"
      subtitle="what was recorded, and when"
      rail={[{ label: 'Record', state: 'recorded', detail: 'recorded timestamps only' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What has happened in the research programme recently, and in what
              order.
            </p>
          </Panel>
          <Panel title="Gaps are real">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Nothing is synthesised to fill a quiet stretch. Where the artifacts
              carry no event timestamp the event is absent, because an inferred
              timestamp on a research record is a fact the record does not
              contain — and a timeline that guesses is worse than one with holes.
            </p>
          </Panel>
        </>
      }
    >
      <ResearchTimeline />
    </Workbench>
  )
}
