import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ModelCompare from '@/components/terminal/compare/ModelCompare'
import SecurityCompare from '@/components/terminal/compare/SecurityCompare'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Compare — miniAladdin',
  description: 'Side-by-side model comparison, with differences coloured only where the metric declares a direction.',
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>
}) {
  const params = await searchParams
  const a = (params.a ?? '').toUpperCase()
  const b = (params.b ?? '').toUpperCase()

  return (
    <Workbench
      title="Compare"
      subtitle={a && b ? `${a} against ${b}` : 'side by side'}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              How two or more models differ, field by field, against a baseline.
            </p>
          </Panel>
          <Panel title="Why most deltas are grey">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A difference is coloured only where the metric declares a direction.
              Turnover of 18× is not worse than 6× without knowing the strategy,
              and colouring it red would be an opinion dressed as a measurement.
            </p>
          </Panel>
          <Panel title="Not comparable">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Where one side did not record a field, the cell says n/c. An absent
              value is not a match and not a zero: a model with no deflated Sharpe
              has not tied one that recorded a failing value.
            </p>
          </Panel>
        </>
      }
    >
      {/* Securities first: this is the comparison a reader arrives wanting.
          The model comparison below it is research, and stays research. */}
      {a && b ? <SecurityCompare a={a} b={b} /> : null}

      <ModelCompare />
    </Workbench>
  )
}
