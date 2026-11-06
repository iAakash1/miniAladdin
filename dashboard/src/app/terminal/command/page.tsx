import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Attention from '@/components/terminal/home/Attention'
import HomeContext from '@/components/terminal/home/HomeContext'
import Ideas from '@/components/terminal/home/Ideas'
import MarketBand from '@/components/terminal/home/MarketBand'
import MarketNews from '@/components/terminal/home/MarketNews'
import PaperLine from '@/components/terminal/home/PaperLine'
import RecentResearch from '@/components/terminal/home/RecentResearch'
import ResearchStart from '@/components/terminal/home/ResearchStart'
import ResearchStatus from '@/components/terminal/home/ResearchStatus'
import SectorLeaders from '@/components/terminal/home/SectorLeaders'
import SectorMovers from '@/components/terminal/home/SectorMovers'
import Watchlist from '@/components/terminal/watchlist/Watchlist'

export const metadata: Metadata = {
  title: 'Home',
  description: 'Start research, see market context, your names and your latest research runs.',
}

/**
 * Where a session starts.
 *
 * The first screen answers, in reading order: where do I begin (the research
 * field), what is the market doing (the snapshot beside it), what did I last
 * conclude (recent research), and what needs me (alerts, the inbox, data).
 * The main column is the research; the side column is everything that waits
 * on the reader.
 */
export default function TerminalHome() {
  return (
    <Workbench title="Home" subtitle="start research, read the market, pick up where you left off" context={<HomeContext />}>
      <div className="home">
        <div className="home__lead">
          <ResearchStart />
          <MarketBand />
        </div>

        <div className="home__cols">
          <div className="home__main">
            <RecentResearch />
            <Watchlist />
            <SectorLeaders />
            <Ideas />
            <SectorMovers />
          </div>
          <aside className="home__side" aria-label="Needs your attention">
            <Attention />
            <PaperLine />
            <ResearchStatus />
            <MarketNews />
          </aside>
        </div>
      </div>
    </Workbench>
  )
}
