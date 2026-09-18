import IntermediateShell from '@/components/intermediate/IntermediateShell'
import PortfolioIntelligence from '@/components/terminal/PortfolioIntelligence'
import PositionsPanel from '@/components/terminal/PositionsPanel'

export default function IntermediatePortfolioPage() {
  return (
    <IntermediateShell title="Portfolio" subtitle="positions, concentration and coverage">
      <PositionsPanel />
      <PortfolioIntelligence />
    </IntermediateShell>
  )
}
