import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Watchlist from '@/components/terminal/watchlist/Watchlist'
import RecentSecurities from '@/components/terminal/home/RecentSecurities'
import ResearchStatus from '@/components/terminal/home/ResearchStatus'
import MarketSummary from '@/components/terminal/home/MarketSummary'
import { Grid, Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Terminal — miniAladdin',
  description: 'What you are watching, what the market is doing, and where you left off.',
}

/**
 * The way in.
 *
 * This screen used to lead with the research programme: NO PRODUCTION
 * CANDIDATE at full weight, a gate table, a registry population, an
 * explanation of why a net Sharpe placed above its blockers is an invitation
 * to read the Sharpe and stop.
 *
 * Every word of that is true and it was the wrong first screen. A terminal
 * opens on what you are watching and what has moved. The research status is a
 * line — honest, unsoftened, and one link from the archive that holds the
 * eight gates and the reasons.
 */
export default function TerminalHome() {
  return (
    <Workbench
      title="Terminal"
      subtitle="what you are watching"
      context={
        <>
          <Panel title="Start here">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Type a ticker or a company name in the search box above, or press{' '}
              <kbd className="sys-kbd">/</kbd> from anywhere. Apple, AAPL, NVDA —
              the symbol database covers most listed US names.
            </p>
          </Panel>
          <Panel title="Where prices come from">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Quotes and history come from the market providers directly, not
              from the research dataset. A security works whether or not any
              experiment has ever scored it.
            </p>
          </Panel>
          <Panel title="Watchlists are local">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Kept in this browser and keyed on the ticker. They do not follow
              you to another machine, and clearing site data clears them.
            </p>
          </Panel>
        </>
      }
    >
      <Grid>
        <Watchlist />
        <RecentSecurities />
      </Grid>

      {/* The summary, not the workspace. Home embedded the whole market page —
          breadth history, the sector map, the events table, leadership, the
          ninety-day chart — which is a good workspace and far too much for a
          screen whose job is to say what matters right now. */}
      <MarketSummary />

      {/* One line. The archive is a link away. */}
      <ResearchStatus />
    </Workbench>
  )
}
