import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import Launcher from '@/components/terminal/security/Launcher'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Analyse — miniAladdin',
  description: 'Start a security analysis from a blank slate, in the macro regime it will be read inside.',
}

export default function AnalyzePage() {
  return (
    <Workbench
      title="Analyse"
      subtitle="start from a ticker"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Which security to look at, before you know which one.
            </p>
          </Panel>
          <Panel title="Where the report lives">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              A completed analysis lands on a permanent URL under the company
              path, which is safe to bookmark and to share. This page is only the
              way in.
            </p>
          </Panel>
          <Panel title="Regime is context, not a verdict">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              An elevated risk multiplier or an inverted curve describes the
              conditions a read happens inside. It says nothing about the
              security you are about to look at.
            </p>
          </Panel>
        </>
      }
    >
      <Launcher />
    </Workbench>
  )
}
