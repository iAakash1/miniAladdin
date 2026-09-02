import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Memos from '@/components/terminal/memos/Memos'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Memos — miniAladdin',
  description: 'A research notebook: thesis, evidence, risks and conclusion, attached to the objects the claim rests on.',
}

export default async function MemosPage({
  searchParams,
}: {
  searchParams: Promise<{ memo?: string }>
}) {
  const p = await searchParams
  return (
    <Workbench
      title="Memos"
      subtitle="what you concluded, and what it rests on"
      rail={[{ label: 'Storage', state: 'recorded', detail: 'this browser only' }]}
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What you decided, why, and which objects would have to change for
              the decision to change.
            </p>
          </Panel>
          <Panel title="Evidence before conclusion">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              The four fields are in the order a claim has to be made. A memo that
              states its conclusion first is an opinion looking for support, and
              the form is arranged to make that awkward.
            </p>
          </Panel>
          <Panel title="Nothing is generated">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Every word here is yours. The product does not write research
              conclusions, and a memo that appeared without an author would be
              exactly the kind of confident text this system exists to avoid.
            </p>
          </Panel>
        </>
      }
    >
      <Memos initialId={p.memo} />
    </Workbench>
  )
}
