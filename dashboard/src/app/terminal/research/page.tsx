import type { Metadata } from 'next'
import Link from 'next/link'

import Workbench from '@/components/system/Workbench'
import PipelineFigure from '@/components/marketing/PipelineFigure'
import AgentObservatory from '@/components/terminal/observatory/AgentObservatory'
import ArchitectureFigure from '@/components/terminal/system/ArchitectureFigure'
import SystemHealthBoard from '@/components/terminal/system/SystemHealthBoard'
import { Grid, Panel, Prose, Status } from '@/components/system'

export const metadata: Metadata = {
  title: 'Architecture',
  description: 'Evidence, quantitative authority and governed research in one inspectable workspace.',
}

const pillars = [
  {
    title: 'Evidence OS', state: 'recorded' as const,
    body: 'Provenance, freshness, source independence, conflicts and citations stay attached to the claim.',
    href: '/terminal/evidence', action: 'Inspect evidence',
  },
  {
    title: 'Quant Engine', state: 'experimental' as const,
    body: 'Signals, risk and portfolio mathematics remain deterministic. The agent layer cannot rewrite them.',
    href: '/terminal/signals', action: 'Inspect signals',
  },
  {
    title: 'Research Lab', state: 'blocked' as const,
    body: 'Datasets, experiments, model cards and holdout governance preserve negative and blocked results.',
    href: '/terminal/lab', action: 'Open Quant Lab',
  },
]

export default function ResearchOSPage() {
  return (
    <Workbench
      title="Architecture"
      subtitle="inspect → understand → audit"
      rail={[
        { label: 'Evidence', state: 'recorded', detail: 'provenance first' },
        { label: 'Decision', state: 'experimental', detail: 'quant authority' },
        { label: 'Governance', state: 'blocked', detail: 'holdout sealed' },
      ]}
      context={(
        <>
          <Panel title="Authority boundary">
            <Prose>The quantitative engine decides. Agents retrieve, reconcile and explain. A narrative never becomes a signal.</Prose>
          </Panel>
          <Panel title="Current research state">
            <Status state="blocked" label="FINAL HOLDOUT NOT READY" />
            <Prose size="tight">EXP-011 revenue mapping requires a formal replication decision. EXP-012 has not been preregistered or fitted.</Prose>
          </Panel>
        </>
      )}
    >
      <Panel title="Request path" subtitle="how a research request reaches the private API">
        <ArchitectureFigure />
      </Panel>
      <Panel title="Authority boundary" subtitle="the signal is fixed before the narrative is written">
        <PipelineFigure />
      </Panel>
      <Panel title="OmniSignal" subtitle="three accountable layers">
        <Grid variant="halves">
          {pillars.map((pillar) => (
            <Panel key={pillar.title} title={pillar.title} state={pillar.state} seam>
              <Prose size="tight">{pillar.body}</Prose>
              <Link href={pillar.href} className="sys-btn">{pillar.action} →</Link>
            </Panel>
          ))}
        </Grid>
      </Panel>
      <SystemHealthBoard compact />
      <AgentObservatory />
    </Workbench>
  )
}
