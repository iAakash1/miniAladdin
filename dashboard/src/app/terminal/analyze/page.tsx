'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import CommandBar from '@/components/terminal/CommandBar'
import TerminalShell, { type TerminalShellContext } from '@/components/terminal/TerminalShell'
import EmptyState from '@/components/ui/EmptyState'
import { LogoMark } from '@/components/ui/Logo'
import { fetchMacroClient } from '@/lib/api'
import { fmtNum, fmtPctRaw } from '@/lib/format'
import { FREE_DAILY_LIMIT } from '@/lib/usage'
import type { Macro } from '@/lib/types'

/**
 * Analyze — the research launcher. The report itself lives at
 * /company/{ticker} (a permanent, bookmarkable URL); this page exists to
 * start from a blank slate: type or pick a ticker, see the current macro
 * regime while you decide. Legacy /terminal/analyze?ticker=X deep links
 * redirect to the company page.
 */
export default function AnalyzePage() {
  return (
    <TerminalShell loadingLabel="Loading terminal…">
      {(shell) => <AnalyzeLauncher shell={shell} />}
    </TerminalShell>
  )
}

function AnalyzeLauncher({ shell }: { shell: TerminalShellContext }) {
  const router = useRouter()
  const { isPro, usedToday } = shell
  const [macro, setMacro] = useState<Macro | null>(null)
  const [fast, setFast] = useState(false)

  /* Legacy deep link: /terminal/analyze?ticker=NVDA → /company/NVDA. */
  useEffect(() => {
    const symbol = new URLSearchParams(window.location.search).get('ticker')
    if (symbol && /^[A-Z.^-]{1,8}$/.test(symbol.toUpperCase())) {
      router.replace(`/company/${encodeURIComponent(symbol.toUpperCase())}`)
    }
  }, [router])

  useEffect(() => {
    let cancelled = false
    fetchMacroClient().then((m) => {
      if (!cancelled && m) setMacro(m)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <section aria-label="Run an analysis" style={{ marginBottom: 24 }}>
        <CommandBar
          loading={false}
          fast={fast}
          onFastChange={setFast}
          onAnalyze={(ticker) =>
            router.push(
              `/company/${encodeURIComponent(ticker.trim().toUpperCase())}${fast ? '?fast=1' : ''}`,
            )
          }
        />
      </section>

      {!isPro && usedToday > 0 && usedToday < FREE_DAILY_LIMIT && (
        <p style={{ fontSize: '0.75rem', color: 'var(--faint)', margin: '-12px 0 20px' }}>
          {FREE_DAILY_LIMIT - usedToday} of {FREE_DAILY_LIMIT} free analyses left today.
        </p>
      )}

      <EmptyState
        icon={<LogoMark size={36} />}
        title="Analyze any US-listed equity"
        description="Type a ticker or pick one above. A full analysis reads price history, fundamentals, news sentiment and the macro regime — about ten seconds — and lands on a permanent page you can bookmark."
      />
      {macro && (
        <section
          aria-label="Current macro conditions"
          className="terminal-grid-four"
          style={{ maxWidth: 880, margin: '0 auto' }}
        >
          {[
            {
              label: 'Risk multiplier',
              value: fmtNum(macro.srm, 2),
              warn: macro.srm > 1.2,
              note: macro.srm > 1.2 ? 'elevated regime' : 'normal regime',
            },
            {
              label: '10Y–2Y spread',
              value: `${fmtNum(macro.yieldSpread, 2)}%`,
              warn: macro.inverted,
              note: macro.inverted ? 'inverted curve' : 'positive slope',
            },
            {
              label: 'CPI inflation',
              value: fmtPctRaw(macro.cpi),
              warn: macro.cpi > 4,
              note: 'year over year',
            },
            {
              label: 'Fed funds rate',
              value: fmtPctRaw(macro.fedRate),
              warn: false,
              note: 'effective rate',
            },
          ].map((s) => (
            <div key={s.label} className="panel" style={{ padding: '16px 18px' }}>
              <p className="label" style={{ marginBottom: 8 }}>
                {s.label}
              </p>
              <p
                className="num"
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 600,
                  color: s.warn ? 'var(--warn)' : 'var(--text)',
                  marginBottom: 3,
                }}
              >
                {s.value}
              </p>
              <p style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>{s.note}</p>
            </div>
          ))}
        </section>
      )}
    </>
  )
}
