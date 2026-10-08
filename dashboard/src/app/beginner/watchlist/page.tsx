import type { Metadata } from 'next'

import SimpleShell from '@/components/beginner/SimpleShell'
import PortfolioView from '@/components/terminal/PortfolioView'

export const metadata: Metadata = { title: 'Watchlist' }

export default function BeginnerWatchlistPage() {
  return (
    <SimpleShell title="Watchlist" subtitle="companies you want to follow">
      <PortfolioView />
    </SimpleShell>
  )
}
