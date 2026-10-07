import { NextResponse } from 'next/server'

import { buildIdentity } from '@/lib/build-identity'

export const dynamic = 'force-dynamic'

export function GET() {
  return NextResponse.json(buildIdentity(process.env), { headers: { 'Cache-Control': 'no-store' } })
}
