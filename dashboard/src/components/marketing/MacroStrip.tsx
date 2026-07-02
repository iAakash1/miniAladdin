'use client'

import { useEffect, useState } from 'react'
import { fetchMacroClient } from '@/lib/api'
import { fmtNum, fmtPctRaw } from '@/lib/format'
import type { Macro } from '@/lib/types'
import Skeleton from '@/components/ui/Skeleton'

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'warn' | 'neg' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span className="label">{label}</span>
      <span
        className="num"
        style={{
          fontSize: '1.0625rem',
          fontWeight: 500,
          color: tone === 'neg' ? 'var(--neg)' : tone === 'warn' ? 'var(--warn)' : 'var(--text)',
        }}
      >
        {value}
      </span>
    </div>
  )
}

/**
 * Live macro readout — the landing page opens with real data,
 * not a claim about data. Hidden entirely if the API is unreachable.
 */
export default function MacroStrip() {
  const [macro, setMacro] = useState<Macro | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')

  useEffect(() => {
    let cancelled = false
    fetchMacroClient().then((m) => {
      if (cancelled) return
      if (m) {
        setMacro(m)
        setState('ready')
      } else {
        setState('failed')
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (state === 'failed') return null

  return (
    <section aria-label="Live macro conditions" className="hairline-top hairline-bottom" style={{ background: 'var(--surface)' }}>
      <div
        className="container"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 'clamp(20px, 4vw, 48px)',
          padding: '18px clamp(20px, 4vw, 32px)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 180 }}>
          <span className="live-dot" aria-hidden="true" />
          <span className="label" style={{ color: 'var(--muted)' }}>
            Macro conditions · FRED
          </span>
        </div>

        {state === 'loading' || !macro ? (
          <div style={{ display: 'flex', gap: 48, flex: 1 }} aria-hidden="true">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} width={90} height={38} />
            ))}
          </div>
        ) : (
          <>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 'clamp(24px, 4vw, 56px)',
                flex: 1,
              }}
            >
              <Stat
                label="Risk multiplier"
                value={fmtNum(macro.srm, 2)}
                tone={macro.srm > 1.2 ? 'warn' : undefined}
              />
              <Stat
                label="10Y–2Y spread"
                value={`${fmtNum(macro.yieldSpread, 2)}%`}
                tone={macro.inverted ? 'neg' : undefined}
              />
              <Stat label="CPI inflation" value={fmtPctRaw(macro.cpi)} tone={macro.cpi > 4 ? 'warn' : undefined} />
              <Stat label="Fed funds rate" value={fmtPctRaw(macro.fedRate)} />
            </div>
            <span
              className={`badge ${macro.status === 'ELEVATED' || macro.recessionWarning ? 'badge--warn' : 'badge--pos'}`}
            >
              {macro.recessionWarning ? 'Recession warning' : macro.status.toLowerCase()}
            </span>
          </>
        )}
      </div>
    </section>
  )
}
