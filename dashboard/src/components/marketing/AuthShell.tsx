import Link from 'next/link'
import Logo from '@/components/ui/Logo'

/** Shared frame for sign-in / sign-up: editorial light, quiet, centered. */
export default function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--paper)',
      }}
    >
      <header style={{ borderBottom: '1px solid var(--line)' }}>
        <div className="container" style={{ display: 'flex', alignItems: 'center', height: 60 }}>
          <Link href="/" aria-label="OmniSignal home" style={{ textDecoration: 'none' }}>
            <Logo size={21} />
          </Link>
        </div>
      </header>

      <main
        id="main"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '48px 20px 64px',
        }}
      >
        {children}
        <p style={{ fontSize: '0.8125rem', color: 'var(--faint)', marginTop: 28, textAlign: 'center' }}>
          Free tier: five analyses a day. No card required.
        </p>
      </main>
    </div>
  )
}
