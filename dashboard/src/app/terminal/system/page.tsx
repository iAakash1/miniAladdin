import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SystemHealthBoard from '@/components/terminal/system/SystemHealthBoard'
import { Panel, Prose } from '@/components/system'

export const metadata: Metadata = {
  title: 'System health',
  description: 'Canonical readiness across providers, agents, data, models and governance.',
}

export default function SystemPage() {
  return (
    <Workbench
      title="System health"
      subtitle="what is ready, blocked, degraded or absent"
      context={(
        <>
          <Panel title="What this answers">
            <Prose>Can each layer support the claim being made right now?</Prose>
          </Panel>
          <Panel title="Liveness is not readiness">
            <Prose size="tight">The API may answer while a provider, graph, model register or research gate remains blocked. Those states stay separate here.</Prose>
          </Panel>
        </>
      )}
    >
      <SystemHealthBoard />
    </Workbench>
  )
}
