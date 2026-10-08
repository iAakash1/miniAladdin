import { ClerkProvider } from '@clerk/nextjs'
import { headers } from 'next/headers'
import type { ComponentProps } from 'react'

/**
 * `ClerkProvider` with the request's Content-Security-Policy nonce.
 *
 * Clerk renders its browser SDK as a plain `<script src>` in the server HTML.
 * Under `'strict-dynamic'` a script written into the document by the parser
 * runs only if it carries the response's nonce - a host allowlist no longer
 * counts - so without this the SDK is blocked and sign-in does not load. The
 * proxy stamps the nonce on the request as `x-nonce`; this hands it to Clerk.
 *
 * A server component, so it must be rendered during a request (every route is
 * dynamic). Use it instead of `ClerkProvider` directly.
 */
export default async function NonceClerkProvider(props: ComponentProps<typeof ClerkProvider>) {
  const nonce = (await headers()).get('x-nonce') ?? undefined
  return <ClerkProvider nonce={nonce} {...props} />
}
