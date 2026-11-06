import type { Metadata } from 'next'
import Link from 'next/link'

import Workbench from '@/components/system/Workbench'
import PortfolioView from '@/components/terminal/PortfolioView'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Portfolio',
  description: 'Positions you record, their exposure, and what has changed across the names you follow since you last looked.',
}

export default function PortfolioPage() {
  return (
    <Workbench
      title="Portfolio"
      subtitle="what you hold, how it has done and where the risk sits"
      rail={[
        { label: 'Positions', state: 'live', detail: 'saved to your account' },
        { label: 'Lists', state: 'live', detail: 'saved to your account' },
        { label: 'Quotes', state: 'live', detail: 'vendor snapshot' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What you hold and what it is worth, how the book has done against a
              benchmark, where its concentration and risk sit, and what the
              research says about the names you follow.
            </p>
          </Panel>
          <Panel title="Managing lists">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Live prices, notes, tags, ordering and alerts for each list are on{' '}
              <Link href="/terminal/watchlists">Watchlists</Link>. Both pages read the same lists from your account.
            </p>
          </Panel>
          <Panel title="Where these live">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Positions and watchlists are saved to your account and follow you to
              another device. Verdicts come from your account&apos;s research record;
              the run-to-run change columns use snapshots kept in this browser.
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
