import IntermediateShell from '@/components/intermediate/IntermediateShell'
import PortfolioView from '@/components/terminal/PortfolioView'

export default function IntermediateWatchlistPage() {
  return (
    <IntermediateShell title="Watchlist" subtitle="what you are following">
      <PortfolioView />
    </IntermediateShell>
  )
}
