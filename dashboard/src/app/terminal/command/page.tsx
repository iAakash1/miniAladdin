import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Watchlist from '@/components/terminal/watchlist/Watchlist'
import RecentSecurities from '@/components/terminal/home/RecentSecurities'
import ResearchStatus from '@/components/terminal/home/ResearchStatus'
import MarketBand from '@/components/terminal/home/MarketBand'
import HomeContext from '@/components/terminal/home/HomeContext'
import SectorMovers from '@/components/terminal/home/SectorMovers'
import { Grid } from '@/components/system'

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
      subtitle="what matters now"
      context={<HomeContext />}
    >
      {/* The market leads because it is the only thing on this page that is
          true on a first morning. Everything below depends on the reader
          having done something; this does not, it is different every day, and
          it is the question a terminal is opened to answer. */}
      <MarketBand />

      {/* Which parts of it moved. The band says the market is up; this says
          the day was energy while industrials fell, which is a different
          morning entirely. */}
      <SectorMovers />

      {/* Then the reader's own names. Empty, these are one line each rather
          than two rectangles apologising for being new. */}
      <Grid>
        <Watchlist />
        <RecentSecurities />
      </Grid>

      {/* One line. The archive is a link away. */}
      <ResearchStatus />
    </Workbench>
  )
}
