import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import CommandCenter from '@/components/terminal/command/CommandCenter'
import ResearchContext from '@/components/terminal/command/ResearchContext'
import { Panel, Provenance } from '@/components/system'

export const metadata: Metadata = {
  title: 'Command — miniAladdin',
  description: 'What deserves attention: blockers, research state, holdout, firewall and recorded experiments.',
}

export default function CommandPage() {
  return (
    <Workbench
      title="Command"
      subtitle="what deserves attention"
      rail={[
        { label: 'Production', state: 'unavailable', detail: 'none armed' },
        { label: 'Holdout', state: 'blocked', detail: 'sealed' },
        { label: 'Registry', state: 'recorded', detail: '103 entries' },
        { label: 'Cost', state: 'recorded', detail: '1 bp + 5 bp half-spread' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What is standing between the current research and a promoted model,
              stated before any headline figure.
            </p>
          </Panel>
          <Panel title="Why blockers come first">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A net Sharpe placed above the reason it does not count is an
              invitation to read the Sharpe and stop. The gate that failed is the
              more important number, so it is the one at the top.
            </p>
          </Panel>
          <Panel title="Where to go next">
            <Provenance steps={[
              { label: 'Evidence', value: 'the full gate chain', href: '/terminal/evidence' },
              { label: 'Experiments', value: 'the registry', href: '/terminal/experiments' },
              { label: 'Risk', value: 'what can hurt the book', href: '/terminal/risk' },
              { label: 'Data', value: 'where the numbers came from', href: '/terminal/data' },
            ]} />
          </Panel>
        </>
      }
    >
      <CommandCenter />
      <ResearchContext />
    </Workbench>
  )
}
