import Link from 'next/link'

/**
 * Frame for sign-in / sign-up: a warm glass panel over a quiet radial wash,
 * correct in both themes. The Clerk card inside is rendered chromeless
 * (see clerk-appearance) so this shell provides all the surface language.
 */
export default function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-shell">
      <header style={{ position: 'absolute', top: 0, left: 0, right: 0 }}>
        <div className="container" style={{ display: 'flex', alignItems: 'center', height: 64 }}>
          <Link href="/" aria-label="OmniSignal home" style={{ textDecoration: 'none' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9, color: 'var(--text)' }}>
              <svg width="21" height="21" viewBox="0 0 20 20" fill="none" aria-hidden="true" className="auth-logo">
                <rect x="0.75" y="0.75" width="18.5" height="18.5" rx="4.25" stroke="currentColor" strokeWidth="1.5" />
                <rect className="auth-bar auth-bar-1" x="4.75" y="10.5" width="2.5" height="5" rx="0.75" fill="currentColor" />
                <rect className="auth-bar auth-bar-2" x="8.75" y="7.5" width="2.5" height="8" rx="0.75" fill="currentColor" />
                <rect className="auth-bar auth-bar-3" x="12.75" y="4.5" width="2.5" height="11" rx="0.75" fill="currentColor" opacity="0.55" />
              </svg>
              <span style={{ fontSize: 17, fontWeight: 620, letterSpacing: '-0.02em' }}>OmniSignal</span>
            </span>
          </Link>
        </div>
      </header>

      <main id="main" className="auth-main">
        <div className="auth-panel">
          <div style={{ textAlign: 'center', marginBottom: 4 }}>
            <p className="eyebrow" style={{ marginBottom: 8 }}>Research terminal</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--muted)', lineHeight: 1.6, maxWidth: '34ch', margin: '0 auto' }}>
              Five signals, one explainable verdict — every number auditable.
            </p>
          </div>
          {children}
          <p style={{ fontSize: '0.75rem', color: 'var(--faint)', textAlign: 'center' }}>
            Free tier: five analyses a day. No card required.
          </p>
        </div>
      </main>
    </div>
  )
}
