import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SecurityView from '@/components/terminal/security/SecurityView'
import SecurityProfile from '@/components/terminal/security/SecurityProfile'
import Fundamentals2 from '@/components/terminal/security/Fundamentals2'
import SecurityResearch from '@/components/terminal/security/SecurityResearch'
import SecurityContext from '@/components/terminal/security/SecurityContext'

export const metadata: Metadata = {
  title: 'Security — miniAladdin',
  description: 'Identity, market, risk, model output and data provenance for one name.',
}

export default async function SecurityPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>
}) {
  const params = await searchParams
  const symbol = (params.symbol ?? '').toUpperCase()

  return (
    <Workbench
      title={symbol || 'Security'}
      subtitle={symbol ? 'price first, research below' : undefined}
      rail={[
        { label: 'Valuation', state: 'live', detail: 'current, not point-in-time' },
      ]}
      context={symbol ? <SecurityContext symbol={symbol} /> : undefined}
    >
      {symbol ? (
        <>
          {/* Price and chart lead, from the market providers, in well under a
              second. */}
          <div id="sec-price"><SecurityView symbol={symbol} /></div>
          {/* Identity, filings and coverage, on their own clock. The research
              endpoint fans out across every vendor and takes half a minute;
              nothing above waits for it, and if it never arrives the page is
              exactly as useful as it was a second after opening.

              This replaced the older research workspace here, which rendered a
              second and empty price chart above an identity table of em dashes
              and a valuation table of em dashes — a broken duplicate of what
              the view above already does from live providers. */}
          <div id="sec-company"><SecurityProfile symbol={symbol} /></div>
          {/* The ratio surface the provider layer has carried all along and
              the interface never showed: valuation multiples, margins,
              returns, growth, leverage and ownership, each with the period it
              describes. Shares one request with the profile above. */}
          <div id="sec-fundamentals"><Fundamentals2 symbol={symbol} /></div>
          {/* Last. An analyst opening a name wants the price, the chart and the
              business before the quantitative programme — this sat third,
              above the company itself. */}
          <SecurityResearch symbol={symbol} />
        </>
      ) : null}
    </Workbench>
  )
}
