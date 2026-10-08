import type { Metadata } from 'next'

import { securityTitle } from '@/lib/page-title'

export async function generateMetadata({ params }: { params: Promise<{ ticker: string }> }): Promise<Metadata> {
  const { ticker } = await params
  return { title: securityTitle(ticker, 'plain-language analysis', 'Company') }
}

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  return children
}
