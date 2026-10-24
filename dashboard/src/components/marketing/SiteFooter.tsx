import Link from 'next/link'
import Logo from '@/components/ui/Logo'
import { FRED_NOTICE, FRED_TERMS_URL } from '@/lib/legal'

const COLUMNS = [
  {
    heading: 'Product',
    links: [
      { href: '/terminal', label: 'Terminal' },
      { href: '/news', label: 'Market news' },
      { href: '/#methodology', label: 'Methodology' },
      { href: '/#pricing', label: 'Pricing' },
    ],
  },
  {
    heading: 'Data sources',
    links: [
      { href: 'https://www.sec.gov/edgar/search/', label: 'SEC EDGAR', external: true },
      { href: 'https://fred.stlouisfed.org', label: 'FRED — St. Louis Fed', external: true },
      { href: 'https://finance.yahoo.com', label: 'Yahoo Finance', external: true },
      { href: 'https://www.alphavantage.co', label: 'Alpha Vantage', external: true },
    ],
  },
  {
    heading: 'Company',
    links: [
      { href: 'https://github.com/iAakash1/miniAladdin', label: 'GitHub', external: true },
      { href: '/sign-in', label: 'Sign in' },
      { href: '/sign-up', label: 'Create account' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { href: '/terms', label: 'Terms and Conditions' },
      { href: '/privacy', label: 'Privacy notice' },
    ],
  },
]

export default function SiteFooter() {
  return (
    <footer className="site-footer" style={{ background: 'var(--glass-chrome)' }}>
      <div className="container" style={{ padding: '56px clamp(20px, 4vw, 32px) 0' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '40px 32px',
            paddingBottom: 48,
          }}
        >
          <div style={{ gridColumn: 'span 1', maxWidth: 280 }}>
            <Logo size={20} />
            <p style={{ fontSize: 'var(--t-body-lg)', color: 'var(--ink-muted)', lineHeight: 1.65, marginTop: 14 }}>
              Evidence-grounded equity research. A deterministic engine sets
              the signal; every input is traced to the provider that supplied it.
            </p>
          </div>

          {COLUMNS.map((col) => (
            <nav key={col.heading} aria-label={col.heading}>
              <p className="sys-label" style={{ marginBottom: 14 }}>
                {col.heading}
              </p>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {col.links.map((link) => (
                  <li key={link.label}>
                    {'external' in link && link.external ? (
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 'var(--t-body-lg)', color: 'var(--ink-muted)', textDecoration: 'none' }}
                      >
                        {link.label}
                        <span aria-hidden="true" style={{ color: 'var(--ink-faint)' }}> ↗</span>
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        style={{ fontSize: 'var(--t-body-lg)', color: 'var(--ink-muted)', textDecoration: 'none' }}
                      >
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div
          className="hairline-top"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px 24px',
            justifyContent: 'space-between',
            padding: '20px 0 28px',
          }}
        >
          <p style={{ fontSize: 'var(--t-body)', color: 'var(--ink-faint)' }}>
            © {new Date().getFullYear()} OmniSignal · an independent, experimental research project
          </p>
          <p style={{ fontSize: 'var(--t-body)', color: 'var(--ink-faint)' }}>
            Research and education only — <Link href="/terms#not-advice" className="site-footer__link">not investment advice</Link>.
          </p>
          {/* Required wording, verbatim, from the FRED API terms of use. */}
          <p className="site-footer__notice">
            {FRED_NOTICE} <a href={FRED_TERMS_URL} className="site-footer__link">FRED API terms</a>.
          </p>
        </div>
      </div>
    </footer>
  )
}
