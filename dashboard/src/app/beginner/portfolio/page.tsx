import SimpleShell from '@/components/beginner/SimpleShell'
import PortfolioIntelligence from '@/components/terminal/PortfolioIntelligence'
import PositionsPanel from '@/components/terminal/PositionsPanel'

export default function BeginnerPortfolioPage() {
  return (
    <SimpleShell title="Portfolio" subtitle="what you hold and where risk is concentrated">
      <PositionsPanel />
      <PortfolioIntelligence />
    </SimpleShell>
  )
}
