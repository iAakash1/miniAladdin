import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import RiskWorkbench from '@/components/terminal/risk/RiskWorkbench'
import { Panel, Section } from '@/components/system'

export const metadata: Metadata = {
  title: 'Risk — miniAladdin',
  description: 'Dispersion, tail, drawdown and risk-adjusted measures, grouped by the question each answers.',
}

export default function RiskPage() {
  return (
    <Workbench
      title="Risk"
      subtitle="where the risk is"
      rail={[
        { label: 'Book', state: 'recorded', detail: 'research allocation' },
        { label: 'Production', state: 'unavailable', detail: 'none armed' },
        { label: 'Cost', state: 'recorded', detail: '1 bp + 5 bp half-spread' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Where the risk is, and how much the answer depends on which
              definition of risk you use.
            </p>
          </Panel>
          <Panel title="Why measures are grouped">
            <Section title="Tail">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                VaR is a quantile, CVaR the average beyond it, EVaR the tightest
                bound above that. The ordering holds for every sample, so the
                spread between them describes the tail better than any one of them.
              </p>
            </Section>
            <Section title="Drawdown">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Depth alone cannot separate a brief plunge from a long grind to the
                same trough. Ulcer and the drawdown-at-risk family measure the path.
              </p>
            </Section>
            <Section title="Dispersion">
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                Standard deviation is a complete description only if returns are
                normal. Mean absolute deviation and the Gini mean difference assume
                less; a large gap between them says how much of the risk figure
                rests on a handful of periods.
              </p>
            </Section>
          </Panel>
          <Panel title="Suppression">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A measure that presupposes a return scale is not applied to a series
              in rank units. Compounding a rank once produced a +6,553% equity
              curve, which is why the unit travels with every number here.
            </p>
          </Panel>
        </>
      }
    >
      <RiskWorkbench />
    </Workbench>
  )
}
