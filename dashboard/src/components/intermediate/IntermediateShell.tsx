'use client'

import type { ReactNode } from 'react'

import Workbench from '@/components/system/Workbench'

/** Intermediate detail: the same shell and engine, with a shorter rail. */
export default function IntermediateShell({
  title, subtitle, children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <Workbench title={title} subtitle={subtitle} navigation="intermediate">
      {children}
    </Workbench>
  )
}
