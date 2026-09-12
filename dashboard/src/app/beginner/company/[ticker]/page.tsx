'use client'

import { use } from 'react'

import BeginnerAnalysis from '@/components/beginner/BeginnerAnalysis'
import SimpleShell from '@/components/beginner/SimpleShell'

export default function BeginnerCompanyPage(
  { params }: { params: Promise<{ ticker: string }> },
) {
  const { ticker } = use(params)
  const symbol = decodeURIComponent(ticker).toUpperCase()

  return (
    <SimpleShell title={symbol} subtitle="plain-language analysis">
      <BeginnerAnalysis ticker={symbol} />
    </SimpleShell>
  )
}
