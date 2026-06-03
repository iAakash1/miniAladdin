import { ClerkProvider } from '@clerk/nextjs'
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'OmniSignal — Agentic Risk Engine',
  description: 'Multi-factor risk analysis: FRED macro, technicals, sentiment.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <head>
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
          <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=JetBrains+Mono:wght@300;400;500;700&display=swap" rel="stylesheet" />
          <script src="https://checkout.razorpay.com/v1/checkout.js" async></script>
        </head>
        <body>{children}</body>
      </html>
    </ClerkProvider>
  )
}
