import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Calibration from '@/components/terminal/validation/Calibration'
import { Panel, StateBlock } from '@/components/system'

export const metadata: Metadata = {
  title: 'Calibration — miniAladdin',
  description: 'Does a score mean what it says: calibration, confusion, population stability and rolling IC for one name.',
}

export default async function CalibrationPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>
}) {
  const p = await searchParams
  const symbol = (p.symbol ?? '').toUpperCase()

  return (
    <Workbench
      title={symbol ? `Calibration · ${symbol}` : 'Calibration'}
      subtitle="does a score mean what it says"
      rail={[
        { label: 'Scope', state: 'experimental', detail: 'one name, before costs' },
        { label: 'Evidence', state: 'blocked', detail: 'not promotion evidence' },
      ]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Whether the scoring engine&apos;s output means what it claims on a
              given name — not whether a strategy works.
            </p>
          </Panel>
          <Panel title="Calibration against ranking">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A model can rank well and be badly calibrated. Where it is, every
              threshold decision taken on its output is wrong even though the
              information coefficient looks fine — the two are different questions
              and neither substitutes for the other.
            </p>
          </Panel>
          <Panel title="Population stability">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Whether the scores being produced now come from the distribution the
              engine was validated on. A model can be perfectly calibrated on a
              population it no longer sees.
            </p>
          </Panel>
        </>
      }
    >
      {symbol ? (
        <Calibration symbol={symbol} />
      ) : (
        <Panel title="Calibration">
          <StateBlock
            state="unknown"
            title="No security selected"
            detail="Open a name from the book or search, or add ?symbol=TICKER to this address."
          />
        </Panel>
      )}
    </Workbench>
  )
}
