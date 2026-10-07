import type { Metadata } from 'next'

import { securityTitle } from '@/lib/page-title'

export async function generateMetadata({ params }: { params: Promise<{ ticker: string }> }): Promise<Metadata> {
  const { ticker } = await params
  return { title: securityTitle(ticker, 'evidence', 'Evidence') }
}

export default function EvidenceLayout({ children }: { children: React.ReactNode }) {
  return children
}
