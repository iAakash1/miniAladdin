import Link from 'next/link'
import Logo from '@/components/ui/Logo'

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
]

export default function SiteFooter() {
  return (
    <footer style={{ borderTop: '1px solid var(--line)', background: 'var(--surface)' }}>
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
            <p style={{ fontSize: '0.875rem', color: 'var(--muted)', lineHeight: 1.65, marginTop: 14 }}>
              Five weighted signals, one risk-adjusted verdict. Built on public
              macro and market data.
            </p>
          </div>

          {COLUMNS.map((col) => (
            <nav key={col.heading} aria-label={col.heading}>
              <p className="label" style={{ marginBottom: 14 }}>
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
                        style={{ fontSize: '0.875rem', color: 'var(--muted)', textDecoration: 'none' }}
                      >
                        {link.label}
                        <span aria-hidden="true" style={{ color: 'var(--faint)' }}> ↗</span>
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        style={{ fontSize: '0.875rem', color: 'var(--muted)', textDecoration: 'none' }}
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
          <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
            © {new Date().getFullYear()} OmniSignal
          </p>
          <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
            Research and education only — not investment advice.
          </p>
        </div>
      </div>
    </footer>
  )
}
