import type { Metadata, Viewport } from 'next'
import '@fontsource-variable/inter'
import '@fontsource-variable/newsreader'
import '@fontsource-variable/newsreader/wght-italic.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import './globals.css'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://mini-aladding.vercel.app'

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
  themeColor: '#0a0b0d',
  width: 'device-width',
  initialScale: 1,
}

/** Runs before paint. Dark is the default; an explicit light choice wins. */
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('omni-theme');document.documentElement.dataset.theme=t==='light'?'light':'dark'}catch(e){document.documentElement.dataset.theme='dark'}})()`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  )
}
