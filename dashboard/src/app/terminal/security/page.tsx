import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SecurityView from '@/components/terminal/security/SecurityView'
import SecurityProfile from '@/components/terminal/security/SecurityProfile'
import { Panel } from '@/components/system'

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
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What this name is doing, first. Identity, price and history load
              from the market providers in under a second; the research layer is
              an order of magnitude slower and sits below rather than in front
              of it.
            </p>
          </Panel>
          <Panel title="Ticker identity">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A ticker is not permanent. It can be reassigned after a delisting, so
              a ticker-keyed history is only as trustworthy as the dataset&apos;s
              survivorship classification — which the Data workspace publishes.
            </p>
          </Panel>
          <Panel title="Predictions are not instructions">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              No model is promoted, so nothing here is served as a
              recommendation. A prediction is a research output in rank units and
              the deployment status travels beside it on every render.
            </p>
          </Panel>
        </>
      }
    >
      {symbol ? (
        <>
          {/* Price and chart lead, from the market providers, in well under a
              second. */}
          <SecurityView symbol={symbol} />
          {/* Identity, filings and coverage, on their own clock. The research
              endpoint fans out across every vendor and takes half a minute;
              nothing above waits for it, and if it never arrives the page is
              exactly as useful as it was a second after opening.

              This replaced the older research workspace here, which rendered a
              second and empty price chart above an identity table of em dashes
              and a valuation table of em dashes — a broken duplicate of what
              the view above already does from live providers. */}
          <SecurityProfile symbol={symbol} />
        </>
      ) : null}
    </Workbench>
  )
}
