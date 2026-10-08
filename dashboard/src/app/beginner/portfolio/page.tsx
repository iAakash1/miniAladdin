import type { Metadata } from 'next'

import SimpleShell from '@/components/beginner/SimpleShell'
import PortfolioIntelligence from '@/components/terminal/PortfolioIntelligence'
import PositionsPanel from '@/components/terminal/PositionsPanel'

export const metadata: Metadata = { title: 'Portfolio' }

export default function BeginnerPortfolioPage() {
  return (
    <SimpleShell title="Portfolio" subtitle="what you hold and where risk is concentrated">
      <PositionsPanel />
      <PortfolioIntelligence />
    </SimpleShell>
  )
}
