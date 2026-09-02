import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ProviderMatrix from '@/components/terminal/providers/ProviderMatrix'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Providers — miniAladdin',
  description: 'Which vendor supplies which capability, and what each one is currently doing.',
}

export default function ProvidersPage() {
  return (
    <Workbench
      title="Providers"
      subtitle="who supplies what"
      rail={[{ label: 'Matrix', state: 'live', detail: 'introspected' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Which vendor can supply which capability, and which of them are
              currently answering.
            </p>
          </Panel>
          <Panel title="Nothing is scored">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              There is no provider quality rank here. A capability is declared
              available or it is not, and an unavailable one carries the reason
              the backend gives — &quot;no key configured&quot; and &quot;the vendor does not
              offer this&quot; are different facts and are not merged into one blank cell.
            </p>
          </Panel>
          <Panel title="Introspected">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The matrix is derived from the vendor clients themselves, so a
              newly added provider appears without anyone editing a list.
            </p>
          </Panel>
        </>
      }
    >
      <ProviderMatrix />
    </Workbench>
  )
}
