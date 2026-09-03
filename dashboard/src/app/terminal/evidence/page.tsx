import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import CommandCenter from '@/components/terminal/command/CommandCenter'
import ResearchContext from '@/components/terminal/command/ResearchContext'
import EvidenceChain from '@/components/terminal/models/EvidenceChain'
import SelectionPopulation from '@/components/terminal/models/SelectionPopulation'
import { Panel, Provenance, Section } from '@/components/system'

export const metadata: Metadata = {
  title: 'Evidence — miniAladdin',
  description: 'The model registry as an evidence chain: validation geometry, costs, multiple-testing correction and the gates standing between a model and promotion.',
}

export default function EvidencePage() {
  return (
    <Workbench
      title="Evidence"
      subtitle="model registry and promotion gates"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Not which model ranks highest. Whether a given model has earned the
              right to be trusted, and if not, exactly which piece of evidence is
              missing.
            </p>
          </Panel>
          <Panel title="Why a leaderboard is not enough">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A rank orders models by a number. It cannot say whether that number
              survived costs, whether it was the best of a thousand tries, or
              whether the holdout that would settle it has been spent. Those are
              separate gates and each can fail on its own.
            </p>
          </Panel>
          <Panel title="The chain">
            <Provenance steps={[
              { label: 'Data', value: 'dataset version, training window' },
              { label: 'Label', value: 'horizon and geometry' },
              { label: 'Validation', value: 'folds, purge, embargo' },
              { label: 'Signal', value: 'IC and its Newey-West t' },
              { label: 'Portfolio', value: 'net of the declared cost' },
              { label: 'Multiple testing', value: 'trials, DSR, PBO' },
              { label: 'Holdout', value: 'spent or sealed' },
              { label: 'Promotion', value: 'gates met or unmet' },
            ]} />
          </Panel>
          <Panel title="Reading a gate">
            <Section title="not recorded">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Counts as unmet. Absent evidence is not passing evidence — treating
                it as such is how an unmeasured model reaches production.
              </p>
            </Section>
          </Panel>
        </>
      }
    >
      {/* Why nothing is promoted, the deployment state, the firewall and the
          holdout. This led the terminal until the terminal had a front door;
          it belongs in the archive, where a reader has come specifically to
          ask whether any of it can be believed. */}
      <CommandCenter />
      {/* What the research was run against: universe, point-in-time status,
          coverage. */}
      <ResearchContext />
      <EvidenceChain />
      {/* Whether the winner is skill or selection. A sorted leaderboard read
          on its own is an argument for its own top row, so the losers and the
          distribution the winner was drawn from go on the same page. */}
      <SelectionPopulation />
    </Workbench>
  )
}
