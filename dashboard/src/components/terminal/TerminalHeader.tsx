'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { UserButton } from '@clerk/nextjs'
import { LogoMark } from '@/components/ui/Logo'
import ThemeToggle from '@/components/ui/ThemeToggle'
import { clerkAppearance } from '@/lib/clerk-appearance'

/* Navigation names WORKFLOWS, not implementation. Eight tabs had grown to
   mirror the route table; an analyst thinks in five moves — see what is
   happening, research a name, check holdings, continue an investigation,
   learn a concept. Everything removed from here (Vault, Graph, Validation,
   Methodology) stays one ⌘K keystroke away and is linked from the surface
   it belongs to, which is why the palette affordance beside these tabs is
   part of this change rather than a nicety. */
const TABS = [
  { href: '/terminal', label: 'Market', match: (p: string) => p === '/terminal' },
  { href: '/terminal/analyze', label: 'Research', match: (p: string) => p.startsWith('/terminal/analyze') || p.startsWith('/company') },
  { href: '/terminal/portfolio', label: 'Portfolio', match: (p: string) => p.startsWith('/terminal/portfolio') },
  { href: '/terminal/sessions', label: 'Workspace', match: (p: string) => p.startsWith('/terminal/sessions') || p.startsWith('/terminal/graph') || p.startsWith('/terminal/vault') },
  { href: '/learn', label: 'Learn', match: (p: string) => p.startsWith('/learn') || p.startsWith('/terminal/methodology') || p.startsWith('/terminal/validation') },
]
import { fmtNum, fmtPctRaw } from '@/lib/format'
import { FREE_DAILY_LIMIT } from '@/lib/usage'
import type { Macro } from '@/lib/types'

interface TerminalHeaderProps {
  macro: Macro | null
  isPro: boolean
  usedToday: number
  onUpgrade: () => void
}

function HeaderStat({ label, value, tone }: { label: string; value: string; tone?: 'warn' | 'neg' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, whiteSpace: 'nowrap' }}>
      <span className="label" style={{ fontSize: '0.625rem' }}>
        {label}
      </span>
      <span
        className="num"
        style={{
          fontSize: '0.75rem',
          fontWeight: 500,
          color: tone === 'neg' ? 'var(--neg)' : tone === 'warn' ? 'var(--warn)' : 'var(--text)',
        }}
      >
        {value}
      </span>
    </div>
  )
}

export default function TerminalHeader({ macro, isPro, usedToday, onUpgrade }: TerminalHeaderProps) {
  const pathname = usePathname()
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        background: 'color-mix(in srgb, var(--bg) 88%, transparent)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        borderBottom: '1px solid var(--line)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          height: 54,
          padding: '0 clamp(16px, 3vw, 28px)',
        }}
      >
        <Link
          href="/"
          aria-label="OmniSignal home"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 9,
            textDecoration: 'none',
            color: 'var(--text)',
            flexShrink: 0,
          }}
        >
          <LogoMark size={19} />
          <span style={{ fontSize: '0.9375rem', fontWeight: 620, letterSpacing: '-0.02em' }}>
            OmniSignal
          </span>
          <span
            className="label"
            style={{ color: 'var(--faint)', paddingLeft: 10, borderLeft: '1px solid var(--line)' }}
          >
            Terminal
          </span>
        </Link>

        <nav aria-label="Terminal sections" className="terminal-tabs" style={{ display: 'flex', gap: 2, minWidth: 0 }}>
          {TABS.map((tab) => {
            // A tab stays lit for every surface inside its workflow, so the
            // user never loses their place after following a deep link.
            const active = tab.match(pathname)
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? 'page' : undefined}
                className="btn btn--ghost btn--sm"
                style={{
                  height: 28,
                  flexShrink: 0,
                  fontWeight: active ? 600 : 500,
                  color: active ? 'var(--text)' : 'var(--muted)',
                  background: active ? 'var(--surface-2)' : undefined,
                }}
              >
                {tab.label}
              </Link>
            )
          })}
        </nav>

        {/* One search surface, not two: the palette is the search box AND
            the way to reach everything no longer in the tab bar. Making the
            shortcut visible is what allows the tab reduction. */}
        <button
          type="button"
          className="terminal-header-search btn btn--secondary btn--sm"
          onClick={() => window.dispatchEvent(new CustomEvent('omni-open-palette'))}
          aria-keyshortcuts="Meta+K Control+K"
          style={{
            flex: '1 1 180px', minWidth: 0, maxWidth: 260, justifyContent: 'space-between',
            color: 'var(--muted)', fontWeight: 450,
          }}
        >
          <span>Search everything…</span>
          <kbd className="num" style={{
            fontSize: '0.625rem', color: 'var(--faint)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-sm)', padding: '1px 5px',
          }}>
            ⌘K
          </kbd>
        </button>

        {/* Live macro readout */}
        {macro && (
          <div
            className="terminal-header-macro"
            style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 'auto' }}
            aria-label="Live macro conditions"
          >
            <HeaderStat label="SRM" value={fmtNum(macro.srm, 2)} tone={macro.srm > 1.2 ? 'warn' : undefined} />
            <HeaderStat
              label="10Y–2Y"
              value={`${fmtNum(macro.yieldSpread, 2)}%`}
              tone={macro.inverted ? 'neg' : undefined}
            />
            <HeaderStat label="CPI" value={fmtPctRaw(macro.cpi)} tone={macro.cpi > 4 ? 'warn' : undefined} />
            <HeaderStat label="Fed" value={fmtPctRaw(macro.fedRate)} />
          </div>
        )}

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginLeft: macro ? 0 : 'auto',
            flexShrink: 0,
          }}
        >
          <ThemeToggle />
          {isPro ? (
            <span className="badge badge--accent">Pro</span>
          ) : (
            <>
              <span
                className="num terminal-usage"
                aria-label={`${FREE_DAILY_LIMIT - usedToday} of ${FREE_DAILY_LIMIT} free analyses remaining today`}
                style={{ fontSize: '0.75rem', color: usedToday >= FREE_DAILY_LIMIT ? 'var(--warn)' : 'var(--muted)' }}
              >
                {Math.max(0, FREE_DAILY_LIMIT - usedToday)}/{FREE_DAILY_LIMIT} free
              </span>
              <button type="button" className="btn btn--secondary btn--sm" onClick={onUpgrade}>
                Upgrade
              </button>
            </>
          )}
          <UserButton
            appearance={{
              variables: clerkAppearance.variables,
              elements: { ...clerkAppearance.elements, avatarBox: { width: 28, height: 28 } },
            }}
          />
        </div>
      </div>
    </header>
  )
}
