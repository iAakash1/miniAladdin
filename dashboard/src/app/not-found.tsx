import Link from 'next/link'
import Logo from '@/components/ui/Logo'

export default function NotFound() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 18,
        padding: 24,
        textAlign: 'center',
        background: 'var(--paper)',
      }}
    >
      <Logo size={22} />
      <p className="num" style={{ fontSize: '0.8125rem', color: 'var(--faint)', letterSpacing: '0.08em' }}>
        404
      </p>
      <h1 className="h-section">This page doesn&apos;t exist</h1>
      <p style={{ fontSize: '0.9375rem', color: 'var(--muted)', maxWidth: 380, lineHeight: 1.6 }}>
        The address may have changed. Everything OmniSignal does starts from the
        home page or the terminal.
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
        <Link href="/" className="btn btn--secondary btn--sm">
          Home
        </Link>
        <Link href="/terminal" className="btn btn--primary btn--sm">
          Open terminal
        </Link>
      </div>
    </div>
  )
}
