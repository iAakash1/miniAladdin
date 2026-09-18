import Workbench from '@/components/system/Workbench'
import AgentObservatory from '@/components/terminal/observatory/AgentObservatory'
import EvidenceAudit from '@/components/terminal/admin/EvidenceAudit'

export default async function AgentRunPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params
  const symbol = decodeURIComponent(ticker).toUpperCase()
  return (
    <Workbench title={`${symbol} agent run`} subtitle="specialists, evidence and validation">
      <AgentObservatory initialSymbol={symbol} />
      <EvidenceAudit initialSymbol={symbol} />
    </Workbench>
  )
}
