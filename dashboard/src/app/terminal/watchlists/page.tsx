import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import TrackerWorkspace from '@/components/terminal/tracker/TrackerWorkspace'

export const metadata: Metadata = {
  title: 'Watchlists',
  description: 'Your watchlists with prices, freshness, period returns, alerts and research context.',
}

export default function WatchlistsPage() {
  return (
    <Workbench title="Watchlists" subtitle="tracked securities">
      <TrackerWorkspace />
    </Workbench>
  )
}
