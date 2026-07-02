import { ClerkProvider, SignUp } from '@clerk/nextjs'
import type { Metadata } from 'next'
import AuthShell from '@/components/marketing/AuthShell'
import { clerkAppearance } from '@/lib/clerk-appearance'

export const metadata: Metadata = {
  title: 'Create account',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

export default function SignUpPage() {
  return (
    <ClerkProvider>
      <AuthShell>
        <SignUp appearance={clerkAppearance} />
      </AuthShell>
    </ClerkProvider>
  )
}
