import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import AgentObservatory from '@/components/terminal/observatory/AgentObservatory'
import EvidenceAudit from '@/components/terminal/admin/EvidenceAudit'
import { Panel, Prose } from '@/components/system'

export const metadata: Metadata = {
  title: 'Agent runs — miniAladdin',
  description: 'Measured specialist execution, reconciliation and claim validation.',
}

export default function AgentRunsPage() {
  return (
    <Workbench
      title="Agent runs"
      subtitle="the pipeline as it actually executed"
      context={(
        <>
          <Panel title="What this answers">
            <Prose>Which specialists ran, what they measured, what degraded and which claims survived validation.</Prose>
          </Panel>
          <Panel title="No simulated activity">
            <Prose size="tight">Every status, count and latency is returned by a real analysis graph invocation.</Prose>
          </Panel>
        </>
      )}
    >
      <AgentObservatory />
      <EvidenceAudit />
    </Workbench>
  )
}
