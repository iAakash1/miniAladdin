import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import PortfolioWorkbench from '@/components/terminal/portfolio2/PortfolioWorkbench'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Book — miniAladdin',
  description: 'Holdings, exposure, cost assumptions and risk share for the research allocation.',
}

export default function BookPage() {
  return (
    <Workbench
      title="Book"
      subtitle="what is held, and what it costs to hold it"
      rail={[
        { label: 'Book', state: 'recorded', detail: 'research allocation' },
        { label: 'Cost', state: 'recorded', detail: '1 bp + 5 bp half-spread' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What the book holds, in what size, on which side — and what the
              friction of holding it is assumed to be.
            </p>
          </Panel>
          <Panel title="Turnover and cost">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Costs are charged on the round-trip notional; reported turnover is
              one-way. Replacing a fully invested book trades twice the capital,
              not once, so multiplying the one-way figure by the quoted rate gives
              half the real charge. Both bases are published.
            </p>
          </Panel>
          <Panel title="Risk lives elsewhere">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Risk has its own workspace rather than a second copy here. Two
              implementations of the same table eventually disagree.
            </p>
          </Panel>
        </>
      }
    >
      <PortfolioWorkbench />
    </Workbench>
  )
}
