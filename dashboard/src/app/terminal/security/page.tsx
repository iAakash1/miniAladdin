import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SecurityWorkspace from '@/components/terminal/security/SecurityWorkspace'
import SymbolPicker from '@/components/terminal/security/SymbolPicker'
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
      subtitle={symbol ? 'one name, five questions' : undefined}
      rail={[
        { label: 'Valuation', state: 'live', detail: 'current, not point-in-time' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What this name is, how it has moved, what risk it carries, what the
              research pipeline says about it, and which of those are
              point-in-time.
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
      <SymbolPicker current={symbol} />
      {symbol ? <SecurityWorkspace symbol={symbol} /> : null}
    </Workbench>
  )
}
