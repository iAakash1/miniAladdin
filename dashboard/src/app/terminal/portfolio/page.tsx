import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import PortfolioView from '@/components/terminal/PortfolioView'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Watchlists',
  description: 'Named sets of securities to follow, and what has changed across them since you last looked.',
}

export default function PortfolioPage() {
  return (
    <Workbench
      title="Watchlists"
      subtitle="what you are following"
      rail={[
        { label: 'Lists', state: 'live', detail: 'saved to your account' },
        { label: 'Quotes', state: 'live', detail: 'vendor snapshot' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Which names you are tracking, and what moved among them since the
              last time you opened the list.
            </p>
          </Panel>
          <Panel title="Where these live">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Watchlists are saved to your account and follow you to another
              device. The verdicts shown beside each name come from research runs
              recorded in this browser, and positions stay on this device.
              Nothing here is an order.
            </p>
          </Panel>
          <Panel title="A list is not a portfolio">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Watching a name records interest, not exposure. The book built from
              the research signal is a separate object and lives under Book.
            </p>
          </Panel>
        </>
      }
    >
      <PortfolioView />
    </Workbench>
  )
}
