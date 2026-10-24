import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ProviderConsole from '@/components/terminal/providers/ProviderConsole'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Providers',
  description: 'Every data vendor: what it can answer, how it is configured, and what it has actually done.',
}

export default function ProvidersPage() {
  return (
    <Workbench
      title="Providers"
      subtitle="who supplies what"
      rail={[{ label: 'Registry', state: 'live', detail: 'introspected' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Which vendor can supply which capability, and which of them are
              currently answering.
            </p>
          </Panel>
          <Panel title="Configured is not healthy">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A key being present says nothing about whether the vendor accepts
              it. Healthy means it answered inside the health window; a vendor
              nothing has asked is idle, and one not asked recently is stale.
              There is no quality rank: no vendor is called cheapest or best
              without a measurement behind it.
            </p>
          </Panel>
          <Panel title="Introspected">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The registry is built on the server from the vendor clients
              themselves and the provider catalog, so a newly added provider
              appears without anyone editing a list on this page.
            </p>
          </Panel>
        </>
      }
    >
      <ProviderConsole />
    </Workbench>
  )
}
