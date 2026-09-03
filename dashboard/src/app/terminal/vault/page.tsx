import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import VaultView from '@/components/terminal/VaultView'
import { Panel } from '@/components/system'

export const metadata: Metadata = {
  title: 'Vault — miniAladdin',
  description: 'Saved research: reports, notes and exports kept across sessions.',
}

export default function Page() {
  return (
    <Workbench title="Vault" subtitle="what you kept"
      context={
        <>
          <Panel title="What this answers">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              What you have deliberately saved, as opposed to what you merely visited.
            </p>
          </Panel>
          <Panel title="Saved is not published">
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Nothing in the vault is shared or transmitted. It is a record for you, held where you put it.
            </p>
          </Panel>
        </>
      }
    >
      <VaultView />
    </Workbench>
  )
}
