import { NextResponse } from 'next/server'

import { buildIdentity } from '@/lib/build-identity'

export const dynamic = 'force-dynamic'

/* Each variable is named literally on purpose. Next replaces
   `process.env.NEXT_PUBLIC_*` with the value fixed at build time only where it
   sees that exact expression; handing `process.env` itself to a function
   compiles to a runtime lookup of variables that were never set, and every
   field came back null on a deployment whose build time and commit were known. */
export function GET() {
  return NextResponse.json(
    buildIdentity({
      NEXT_PUBLIC_BUILD_SHA: process.env.NEXT_PUBLIC_BUILD_SHA,
      NEXT_PUBLIC_BUILD_REF: process.env.NEXT_PUBLIC_BUILD_REF,
      NEXT_PUBLIC_BUILD_ENV: process.env.NEXT_PUBLIC_BUILD_ENV,
      NEXT_PUBLIC_BUILD_DEPLOYMENT: process.env.NEXT_PUBLIC_BUILD_DEPLOYMENT,
      NEXT_PUBLIC_BUILD_TIME: process.env.NEXT_PUBLIC_BUILD_TIME,
    }),
    { headers: { 'Cache-Control': 'no-store' } },
  )
}
