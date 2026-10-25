import type { Metadata } from 'next'

import Workbench from '@/components/system/Workbench'
import AlertsWorkspace from '@/components/terminal/alerts/AlertsWorkspace'

export const metadata: Metadata = {
  title: 'Alerts',
  description: 'Price and filing alerts evaluated on the server, and the notification inbox.',
}

export default function AlertsPage() {
  return (
    <Workbench title="Alerts" subtitle="evaluated on the server's schedule">
      <AlertsWorkspace />
    </Workbench>
  )
}
