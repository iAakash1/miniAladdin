import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import DataWorkbench from '@/components/terminal/data/DataWorkbench'
import { Panel, Provenance, Section } from '@/components/system'

export const metadata: Metadata = {
  title: 'Data — miniAladdin',
  description: 'Dataset and feature contracts: point-in-time classification, survivorship, lookback and availability lag.',
}

export default function DataPage() {
  return (
    <Workbench
      title="Data"
      subtitle="dataset and feature contracts"
      rail={[
        { label: 'Catalogue', state: 'recorded', detail: 'published contract' },
        { label: 'Holdout', state: 'blocked', detail: 'sealed' },
        { label: 'Production', state: 'unavailable', detail: 'none armed' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Where a number came from, when it could first have been known, and
              whether the dataset behind it is free of survivorship bias.
            </p>
          </Panel>
          <Panel title="Reading the contract">
            <Section title="Lookback">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Sessions of history a feature reads. The largest value across the
                registry sets the warm-up before any model can score its first row.
              </p>
            </Section>
            <Section title="Availability lag">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Sessions between an observation and the moment it could actually
                have been known. A lag of zero on a fundamental is the signature
                of a look-ahead.
              </p>
            </Section>
            <Section title="Survivorship">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Whether the universe includes names that later delisted. A dataset
                that does not is one where every backtest is measured on companies
                already known to have survived.
              </p>
            </Section>
          </Panel>
          <Panel title="Chain">
            <Provenance steps={[
              { label: 'Dataset', value: 'source, repository, table' },
              { label: 'Feature', value: 'lookback + availability lag' },
              { label: 'Label', value: 'horizon, purge, embargo' },
              { label: 'Model', value: 'folds, validation geometry' },
              { label: 'Experiment', value: 'gates, trials, verdict' },
            ]} />
          </Panel>
        </>
      }
    >
      <DataWorkbench />
    </Workbench>
  )
}
