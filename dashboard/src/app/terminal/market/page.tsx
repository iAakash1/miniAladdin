import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import MarketWorkspace from '@/components/terminal/market/MarketWorkspace'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Market — miniAladdin',
  description: 'Breadth, sector leadership, momentum dispersion, macro and dated events.',
}

export default function MarketPage() {
  return (
    <Workbench
      title="Market"
      subtitle="what is happening"
      rail={[
        { label: 'Feed', state: 'live', detail: 'vendor data, not point-in-time' },
        { label: 'Research', state: 'recorded', detail: 'nothing here feeds a factor' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What the market is doing now — breadth, which sectors lead, how much
              separates them, and what is scheduled.
            </p>
          </Panel>
          <Panel title="Live, not recorded">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              These are vendor values describing the market now. They change
              between views and are not point-in-time, so no factor and no
              experiment is built from them — the research surfaces use the
              point-in-time panel instead, and the difference is the reason both
              exist.
            </p>
          </Panel>
          <Panel title="Momentum dispersion">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The spread between the leading and lagging sector is the
              cross-sectional opportunity a long/short book tries to capture. A
              narrow spread means there is little to separate, whatever the index
              level is doing.
            </p>
          </Panel>
        </>
      }
    >
      <MarketWorkspace />
    </Workbench>
  )
}
