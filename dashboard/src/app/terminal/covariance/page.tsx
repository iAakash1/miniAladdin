import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import CovarianceLab from '@/components/terminal/risk/CovarianceLab'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Covariance — miniAladdin',
  description: 'Four covariance estimators on one panel: conditioning, positive semi-definiteness, and the risk each implies.',
}

export default function CovariancePage() {
  return (
    <Workbench
      title="Covariance"
      subtitle="which matrix, and what it changes"
      rail={[
        { label: 'Default', state: 'recorded', detail: 'pairwise, unchanged' },
        { label: 'Alternatives', state: 'recorded', detail: 'named, not substituted' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              How much of the reported risk is a property of the book, and how
              much is a property of the estimator chosen to measure it.
            </p>
          </Panel>
          <Panel title="Condition number">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The ratio of largest to smallest eigenvalue. Large means the matrix
              is nearly singular in some direction — and that direction is exactly
              where an unconstrained optimiser puts its largest, least justified
              position.
            </p>
          </Panel>
          <Panel title="Complete case">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Pairwise deletion keeps more data and produces entries measured on
              different populations, which is what makes a matrix indefinite.
              Complete-case keeps fewer rows and reports how many, which is the
              honest sample size.
            </p>
          </Panel>
        </>
      }
    >
      <CovarianceLab />
    </Workbench>
  )
}
