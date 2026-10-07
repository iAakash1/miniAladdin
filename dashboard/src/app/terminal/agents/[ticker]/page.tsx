import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import AgentObservatory from '@/components/terminal/observatory/AgentObservatory'
import EvidenceAudit from '@/components/terminal/admin/EvidenceAudit'
import { securityTitle } from '@/lib/page-title'

export async function generateMetadata({ params }: { params: Promise<{ ticker: string }> }): Promise<Metadata> {
  const { ticker } = await params
  return { title: securityTitle(ticker, 'agent run', 'Agent run') }
}

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
