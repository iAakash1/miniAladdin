import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import AdminDiagnostics from '@/components/terminal/admin/AdminDiagnostics'
import { Panel, Prose } from '@/components/system'

export const metadata: Metadata = {
  title: 'Operations — miniAladdin',
  description: 'Deployment posture, configured capabilities and provider state.',
}

export default function AdminPage() {
  return (
    <Workbench
      title="Operations"
      subtitle="deployment posture"
      rail={[{ label: 'Diagnostics', state: 'live', detail: 'operator only' }]}
      context={
        <>
          <Panel title="What this answers">
            <Prose>
              Whether this deployment has what it needs to do its job: which
              capabilities are configured, which vendors are answering, and
              which have been cooled down after failing.
            </Prose>
          </Panel>
          <Panel title="Posture, not material">
            <Prose>
              Every line says whether something is configured. None of them say
              what it is configured with. A diagnostics page that prints
              credentials is a credential leak with a nicer name.
            </Prose>
          </Panel>
          <Panel title="The boundary is the server">
            <Prose>
              Access is decided by the backend on every request. Not drawing
              this link for an ordinary account would be a presentation
              choice; refusing the request is the control.
            </Prose>
          </Panel>
        </>
      }
    >
      <AdminDiagnostics />
    </Workbench>
  )
}
