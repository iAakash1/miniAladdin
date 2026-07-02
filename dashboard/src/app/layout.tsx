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
    default: 'OmniSignal — Equity research terminal',
    template: '%s · OmniSignal',
  },
  description:
    'Five weighted signals — momentum, risk-adjusted return, valuation, news sentiment and the macro cycle — combined into one risk-adjusted verdict per stock.',
  keywords: ['equity research', 'stock analysis', 'risk analysis', 'market news', 'FRED', 'technical analysis'],
  authors: [{ name: 'OmniSignal' }],
  openGraph: {
    type: 'website',
    siteName: 'OmniSignal',
    title: 'OmniSignal — Equity research terminal',
    description:
      'Five weighted signals combined into one risk-adjusted verdict per stock. Live macro conditions from FRED, technicals, fundamentals and news sentiment.',
    url: SITE_URL,
  },
  twitter: {
    card: 'summary_large_image',
    title: 'OmniSignal — Equity research terminal',
    description: 'Five weighted signals. One risk-adjusted verdict.',
  },
  robots: { index: true, follow: true },
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#faf9f6' },
    { media: '(prefers-color-scheme: dark)', color: '#111210' },
  ],
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  )
}
