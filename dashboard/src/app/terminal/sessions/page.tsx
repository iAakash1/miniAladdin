import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SessionsView from '@/components/terminal/SessionsView'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Sessions — miniAladdin',
  description: 'Previous research sessions and what was looked at in each.',
}

export default function Page() {
  return (
    <Workbench title="Sessions" subtitle="what you did before"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What you looked at in earlier sessions, so a line of enquiry can be picked back up rather than restarted.
            </p>
          </Panel>
          <Panel title="Stored in this browser">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Sessions are local to this browser. They do not follow you to another machine, and clearing site data clears them.
            </p>
          </Panel>
        </>
      }
    >
      <SessionsView />
    </Workbench>
  )
}
