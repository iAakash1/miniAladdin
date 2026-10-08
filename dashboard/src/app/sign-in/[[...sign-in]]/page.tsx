import { SignIn } from '@clerk/nextjs'
import NonceClerkProvider from '@/components/auth/NonceClerkProvider'
import type { Metadata } from 'next'
import AuthShell from '@/components/marketing/AuthShell'
import { clerkAppearance } from '@/lib/clerk-appearance'

export const metadata: Metadata = {
  title: 'Sign in',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

export default function SignInPage() {
  return (
    <NonceClerkProvider>
      <AuthShell>
        <SignIn appearance={clerkAppearance} />
      </AuthShell>
    </NonceClerkProvider>
  )
}
