'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { UserButton } from '@clerk/nextjs'
import ScreenSearch from '@/components/terminal/ScreenSearch'
import { LogoMark } from '@/components/ui/Logo'
import ThemeToggle from '@/components/ui/ThemeToggle'
import { clerkAppearance } from '@/lib/clerk-appearance'

const TABS = [
  { href: '/terminal', label: 'Market' },
  { href: '/terminal/analyze', label: 'Analyze' },
  { href: '/terminal/portfolio', label: 'Portfolio' },
  { href: '/terminal/validation', label: 'Validation' },
  { href: '/terminal/methodology', label: 'Methodology' },
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
          <span style={{ fontSize: '0.9063rem', fontWeight: 620, letterSpacing: '-0.02em' }}>
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
            const active = pathname === tab.href
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

        {/* Global search — available on every /terminal/* page, not just Market */}
        <div className="terminal-header-search" style={{ flex: '1 1 200px', minWidth: 0, maxWidth: 280 }}>
          <ScreenSearch maxWidth={280} />
        </div>

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
