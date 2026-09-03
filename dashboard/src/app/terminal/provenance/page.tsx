import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import ChainPicker from '@/components/terminal/provenance/ChainPicker'
import Lineage from '@/components/terminal/provenance/Lineage'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Provenance — miniAladdin',
  description: 'The chain from vendor observation to prediction, with each stage marked as observed, derived or model-predicted.',
}

export default async function ProvenancePage({
  searchParams,
}: {
  searchParams: Promise<{ label?: string; model?: string }>
}) {
  const params = await searchParams
  const label = params.label ?? 'fwd_rank_21'
  const model = params.model ?? 'gradient_boosting'

  return (
    <Workbench
      title="Provenance"
      subtitle={`${label} · ${model}`}
      rail={[
        { label: 'Chain', state: 'recorded', detail: 'from artifact' },
        { label: 'Sources', state: 'recorded', detail: 'checksummed partitions' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Where a prediction came from — every dataset, transformation and
              inference between a vendor observation and the number on screen.
            </p>
          </Panel>
          <Panel title="Stage kinds">
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>observed</td><td style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', whiteSpace: 'normal' }}>A vendor measurement, in an immutable checksummed partition.</td></tr>
                <tr><td>derived</td><td style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', whiteSpace: 'normal' }}>Computed here from observations. Reproducible, but this system&apos;s own arithmetic.</td></tr>
                <tr><td>model predicted</td><td style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', whiteSpace: 'normal' }}>An inference. Nothing downstream is more reliable than this link.</td></tr>
              </tbody>
            </table>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Rendering all stages identically would hide exactly the distinction
              a reviewer opens a lineage to find.
            </p>
          </Panel>
        </>
      }
    >
      <ChainPicker label={label} model={model} />
      <Lineage label={label} model={model} />
    </Workbench>
  )
}
