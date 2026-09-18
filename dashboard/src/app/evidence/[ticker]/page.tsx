'use client'

import { use } from 'react'
import { useSearchParams } from 'next/navigation'

import SimpleShell from '@/components/beginner/SimpleShell'
import IntermediateShell from '@/components/intermediate/IntermediateShell'
import Workbench from '@/components/system/Workbench'
import EvidenceAudit from '@/components/terminal/admin/EvidenceAudit'
import { useCapabilities } from '@/lib/capabilities'

export default function EvidenceInspectorPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params)
  const symbol = decodeURIComponent(ticker).toUpperCase()
  const search = useSearchParams()
  const { caps } = useCapabilities()
  const requested = search.get('mode')
  const mode = requested === 'beginner' || requested === 'intermediate' || requested === 'advanced'
    ? requested
    : caps?.experience_mode ?? 'advanced'
  const content = (
    <EvidenceAudit
      initialSymbol={symbol}
      initialEvidenceId={search.get('evidence') ?? ''}
    />
  )

  if (mode === 'beginner') {
    return <SimpleShell title={`${symbol} evidence`} subtitle="claims and their sources">{content}</SimpleShell>
  }
  if (mode === 'intermediate') {
    return <IntermediateShell title={`${symbol} evidence`} subtitle="claims and their sources">{content}</IntermediateShell>
  }
  return (
    <Workbench title={`${symbol} evidence`} subtitle="claims and their sources">
      {content}
    </Workbench>
  )
}
