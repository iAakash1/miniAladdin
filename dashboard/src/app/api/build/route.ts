import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export function GET() {
  return NextResponse.json({
    service: 'frontend',
    commit: process.env.NEXT_PUBLIC_BUILD_SHA ?? 'unknown',
  })
}
