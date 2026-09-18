'use client'

import { use } from 'react'

import IntermediateAnalysis from '@/components/intermediate/IntermediateAnalysis'
import IntermediateShell from '@/components/intermediate/IntermediateShell'

export default function IntermediateCompanyPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params)
  const symbol = decodeURIComponent(ticker).toUpperCase()
  return (
    <IntermediateShell title={symbol} subtitle="factor and evidence analysis">
      <IntermediateAnalysis ticker={symbol} />
    </IntermediateShell>
  )
}
