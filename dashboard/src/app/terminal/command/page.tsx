import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import HomeContext from '@/components/terminal/home/HomeContext'
import Ideas from '@/components/terminal/home/Ideas'
import MarketBand from '@/components/terminal/home/MarketBand'
import MarketNews from '@/components/terminal/home/MarketNews'
import PaperLine from '@/components/terminal/home/PaperLine'
import RecentResearch from '@/components/terminal/home/RecentResearch'
import ResearchStart from '@/components/terminal/home/ResearchStart'
import ResearchStatus from '@/components/terminal/home/ResearchStatus'
import SectorMovers from '@/components/terminal/home/SectorMovers'
import Watchlist from '@/components/terminal/watchlist/Watchlist'

export const metadata: Metadata = {
  title: 'Home',
  description: 'Start research, see market context, your names and your latest research runs.',
}

/** Where a session starts: search, the market, your names, your research. */
export default function TerminalHome() {
  return (
    <Workbench title="Home" subtitle="start research · market context · your names" context={<HomeContext />}>
      <ResearchStart />
      <MarketBand />
      <div className="home-grid">
        <Watchlist />
        <RecentResearch />
      </div>
      <div className="home-grid home-grid--wide">
        <Ideas />
        <SectorMovers />
      </div>
      <MarketNews />
      <div className="home-lines">
        <ResearchStatus />
        <PaperLine />
      </div>
    </Workbench>
  )
}
