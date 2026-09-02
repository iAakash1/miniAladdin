import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import SpreadCurve from '@/components/terminal/performance/SpreadCurve'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Performance — miniAladdin',
  description: 'The quantile spread curve in rank points, with its drawdown, turnover and cost.',
}

export default async function PerformancePage({
  searchParams,
}: {
  searchParams: Promise<{ experiment?: string; model?: string }>
}) {
  const p = await searchParams
  const experiment = p.experiment ?? 'EXP-006'
  const model = p.model ?? 'gradient_boosting'

  return (
    <Workbench
      title="Performance"
      subtitle={`${experiment} · ${model}`}
      rail={[
        { label: 'Units', state: 'experimental', detail: 'rank points, not returns' },
        { label: 'Cost', state: 'recorded', detail: '10 bp half-spread in this curve' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Whether the signal separates the top quantile from the bottom, and
              whether that separation survives rebalancing friction.
            </p>
          </Panel>
          <Panel title="Rank points">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The label is a cross-sectional rank in [−1, 1]. The curve accumulates
              rank spread additively, so 11.3 means eleven rank points, not
              1,130%. Compounding a rank once produced a +6,553% curve here, which
              is why the unit is repeated on every figure.
            </p>
          </Panel>
          <Panel title="Where the evidence comes from">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Not from this curve. Every Sharpe and cost figure quoted as evidence
              comes from the artifact&apos;s costed backtest, which models market
              impact this diagnostic does not.
            </p>
          </Panel>
        </>
      }
    >
      <SpreadCurve experiment={experiment} model={model} />
    </Workbench>
  )
}
