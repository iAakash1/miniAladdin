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
      <p className="num" style={{ fontSize: 'var(--t-body)', color: 'var(--faint)', letterSpacing: 'var(--tracking-label)' }}>
        404
      </p>
      <h1 className="h-section">This page doesn&apos;t exist</h1>
      <p style={{ fontSize: 'var(--t-value)', color: 'var(--muted)', maxWidth: 380, lineHeight: 1.6 }}>
        The address may have changed. Everything OmniSignal does starts from the
        home page or the terminal.
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
        <Link href="/" className="sys-btn">
          Home
        </Link>
        <Link href="/terminal" className="sys-btn sys-btn--primary">
          Open terminal
        </Link>
      </div>
    </div>
  )
}
