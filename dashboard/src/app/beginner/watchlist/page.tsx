import SimpleShell from '@/components/beginner/SimpleShell'
import PortfolioView from '@/components/terminal/PortfolioView'

export default function BeginnerWatchlistPage() {
  return (
    <SimpleShell title="Watchlist" subtitle="companies you want to follow">
      <PortfolioView />
    </SimpleShell>
  )
}
