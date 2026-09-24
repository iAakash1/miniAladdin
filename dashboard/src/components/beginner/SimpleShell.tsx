'use client'

import type { ReactNode } from 'react'

import Workbench from '@/components/system/Workbench'

/** Simple mode: the same shell and engine, with a shorter rail. */
export default function SimpleShell({
  title, subtitle, children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <Workbench title={title} subtitle={subtitle} navigation="beginner">
      {children}
    </Workbench>
  )
}
