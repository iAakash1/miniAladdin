import type { Metadata, Viewport } from 'next'
import '@fontsource-variable/inter'
import '@fontsource-variable/newsreader'
import '@fontsource-variable/newsreader/wght-italic.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import './globals.css'
import StateMeanings from '@/components/system/StateMeanings'
import { THEME_COLOR, THEME_SCRIPT } from '@/lib/theme'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://omnisignalterminal.vercel.app'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'OmniSignal — Evidence-grounded equity research',
    template: '%s · OmniSignal',
  },
  description:
    'An equity research terminal: deterministic quantitative signals, multi-provider evidence with visible disagreement, SEC primary sources and grounded AI explanation that never decides.',
  keywords: ['equity research', 'evidence provenance', 'quantitative analysis', 'SEC filings', 'FRED macro', 'research terminal'],
  authors: [{ name: 'OmniSignal' }],
  openGraph: {
    type: 'website',
    siteName: 'OmniSignal',
    title: 'OmniSignal — Evidence-grounded equity research',
    description:
      'Deterministic signals, reconciled multi-provider evidence, SEC primary sources and grounded AI explanation — every number traceable to its source.',
    url: SITE_URL,
  },
  twitter: {
    card: 'summary_large_image',
    title: 'OmniSignal — Evidence-grounded equity research',
    description: 'Deterministic signals. Auditable evidence. Grounded explanation.',
  },
  robots: { index: true, follow: true },
}

export const viewport: Viewport = {
  themeColor: THEME_COLOR.dark,
  width: 'device-width',
  initialScale: 1,
}

/* Every page is rendered per request.

   The Content-Security-Policy carries a fresh nonce for each response, and Next
   can stamp a nonce only on markup it renders for that request. A prerendered
   page is the same bytes for everyone, so its inline bootstrap scripts could not
   carry one and the policy would have to allow any inline script instead - the
   one thing a script policy exists to refuse. The marketing and learning pages
   were the only static routes; they are small, and rendering them on demand
   costs milliseconds against a policy that holds for every route. */
export const dynamic = 'force-dynamic'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
        <StateMeanings />
      </body>
    </html>
  )
}
