import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import PortfolioView from '@/components/terminal/PortfolioView'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Watchlists — miniAladdin',
  description: 'Named sets of securities to follow, and what has changed across them since you last looked.',
}

export default function PortfolioPage() {
  return (
    <Workbench
      title="Watchlists"
      subtitle="what you are following"
      rail={[
        { label: 'Lists', state: 'live', detail: 'stored in this browser' },
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
              Watchlists are stored in this browser, not on a server. They do not
              follow you to another machine, and clearing site data clears them.
              Nothing here is a position or an order.
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
