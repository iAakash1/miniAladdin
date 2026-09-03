'use client'

/**
 * The research launcher: start from a blank slate.
 *
 * A security's report lives at a permanent, bookmarkable URL. This page exists
 * for the moment before you know which security — type or pick a ticker, and
 * read the current macro regime while you decide, because the regime is the
 * context every single-name read happens inside.
 *
 * Two behaviours it has to keep from the page it replaces.
 *
 * **Legacy deep links still resolve.** `/terminal/analyze?ticker=NVDA` was a
 * URL people bookmarked and shared. It redirects to the company page rather
 * than rendering a launcher that ignores the ticker it was handed.
 *
 * **Free-tier usage is stated, and only once it is known.** The remaining-count
 * line renders only after the session resolves. Showing a free-tier message to
 * a paying reader for one frame is worse than showing nothing for one frame.
 */

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Strip } from '@/components/system'
import { useEntitlement } from '@/components/system/Entitlement'
import CommandBar from '@/components/terminal/CommandBar'
import { fetchMacroClient } from '@/lib/api'
import { FREE_DAILY_LIMIT } from '@/lib/usage'
import type { Macro } from '@/lib/types'

export default function Launcher() {
  const router = useRouter()
  const { resolved, isPro, usedToday } = useEntitlement()
  const [macro, setMacro] = useState<Macro | null>(null)
  const [macroFailed, setMacroFailed] = useState(false)
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
    fetchMacroClient()
      .then((m) => {
        if (cancelled) return
        if (m) setMacro(m)
        else setMacroFailed(true)
      })
      .catch(() => { if (!cancelled) setMacroFailed(true) })
    return () => { cancelled = true }
  }, [])

  const remaining = FREE_DAILY_LIMIT - usedToday

  return (
    <>
      <Panel title="Analyse a security" state="live">
        <Prose>
          Type a ticker or pick one below. A full analysis reads price history,
          fundamentals, news sentiment and the macro regime — around ten seconds
          — and lands on a permanent page you can bookmark.
        </Prose>
        <div style={{ marginTop: 'var(--d-3)' }}>
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
        </div>
        {/* Only once the session is known. An entitlement that has not resolved
            is not the same as a free one, and rendering the second for the
            first shows a paying reader a limit they do not have. */}
        {resolved && !isPro && usedToday > 0 && remaining > 0 ? (
          <Prose size="fine">
            {remaining} of {FREE_DAILY_LIMIT} free analyses left today.
          </Prose>
        ) : null}
      </Panel>

      <Panel
        title="The regime you are reading into"
        subtitle="current macro conditions"
        state={macro ? 'live' : macroFailed ? 'unavailable' : 'waking'}
      >
        {macro ? (
          <>
            <Strip metrics={[
              {
                label: 'Risk multiplier', value: macro.srm, digits: 2,
                title: macro.srm > 1.2 ? 'elevated regime' : 'normal regime',
              },
              {
                label: '10Y–2Y spread', value: macro.yieldSpread, digits: 2, unit: '%',
                title: macro.inverted ? 'inverted curve' : 'positive slope',
              },
              { label: 'CPI inflation', value: macro.cpi, digits: 1, unit: '%', title: 'year over year' },
              { label: 'Fed funds rate', value: macro.fedRate, digits: 2, unit: '%', title: 'effective rate' },
            ]} />
            <Prose size="fine">
              A single-name read happens inside a regime. These are the same
              readings the market workspace shows, repeated here because the
              decision they qualify is the one about to be made.
            </Prose>
          </>
        ) : macroFailed ? (
          /* The launcher still works without macro. Saying the regime is
             unavailable is different from implying conditions are normal. */
          <StateBlock
            state="unavailable"
            title="The macro regime could not be read"
            detail="Analysis still runs. The regime context for it is simply not available right now, and none is assumed in its place."
          />
        ) : (
          <StateBlock state="waking" title="Reading current macro conditions" />
        )}
      </Panel>
    </>
  )
}
