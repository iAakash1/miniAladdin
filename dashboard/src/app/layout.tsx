import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'OmniSignal — Agentic Risk Engine',
  description:
    'Multi-factor risk analysis: FRED macro signals, technical indicators, and news sentiment unified into a single risk-adjusted verdict.',
  openGraph: {
    title: 'OmniSignal',
    description: 'Agentic Multi-Factor Risk & Prediction Engine',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@300;400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
