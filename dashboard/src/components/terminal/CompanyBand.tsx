'use client'

import { useState } from 'react'
import { fmtPrice } from '@/lib/format'
import { saveReport } from '@/lib/persistence'
import type { Analysis, Verdict } from '@/lib/types'

const VERDICT_TONE: Record<Verdict, 'pos' | 'warn' | 'neg'> = {
  'Strong Buy': 'pos',
  Buy: 'pos',
  Hold: 'warn',
  Sell: 'neg',
  'Strong Sell': 'neg',
}

const TONE_VAR = { pos: 'var(--pos)', warn: 'var(--warn)', neg: 'var(--neg)' }
const WASH_VAR = { pos: 'var(--pos-wash)', warn: 'var(--warn-wash)', neg: 'var(--neg-wash)' }

export function VerdictChip({ verdict, size = 'md' }: { verdict: Verdict; size?: 'md' | 'lg' }) {
  const tone = VERDICT_TONE[verdict]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: size === 'lg' ? '7px 14px' : '4px 10px',
        borderRadius: 'var(--r-md)',
        background: WASH_VAR[tone],
        border: `1px solid color-mix(in srgb, ${TONE_VAR[tone]} 35%, transparent)`,
        color: TONE_VAR[tone],
        fontSize: size === 'lg' ? '0.9375rem' : '0.8125rem',
        fontWeight: 620,
        letterSpacing: '0.01em',
        whiteSpace: 'nowrap',
      }}
    >
      {verdict}
    </span>
  )
}

/** Bookmark this run into Saved Reports (Vault). Only rendered when the
 *  backend recorded the analysis (historyId present). */
function SaveReportButton({ historyId }: { historyId: string }) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')

  const save = async () => {
    setState('saving')
    const saved = await saveReport(historyId)
    setState(saved ? 'saved' : 'failed')
  }

  if (state === 'saved') {
    return (
      <span className="badge badge--accent" style={{ height: 24 }}>
        ★ Saved to Vault
      </span>
    )
  }
  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm"
      onClick={save}
      disabled={state === 'saving'}
      title="Bookmark this analysis in your Vault"
      style={{ border: '1px solid var(--line)' }}
    >
      {state === 'saving' ? 'Saving…' : state === 'failed' ? 'Retry save' : '☆ Save report'}
    </button>
  )
}

export default function CompanyBand({ analysis }: { analysis: Analysis }) {
  const wasDampened = analysis.verdict !== analysis.riskAdjusted

  return (
    <section
      aria-label={`${analysis.ticker} overview`}
      className="panel"
      style={{ padding: 'clamp(18px, 3vw, 26px)' }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '16px 32px',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 4 }}>
            <h2 className="mono" style={{ fontSize: '1.25rem', fontWeight: 600, letterSpacing: '0.01em' }}>
              {analysis.ticker}
            </h2>
            <span style={{ fontSize: '1rem', color: 'var(--muted)', fontWeight: 500 }}>
              {analysis.companyName}
            </span>
          </div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
            {[analysis.sector, analysis.marketCap ? `${analysis.marketCap} market cap` : null]
              .filter(Boolean)
              .join(' · ') || '—'}
          </p>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 18 }}>
            <span className="num" style={{ fontSize: 'clamp(1.9rem, 4vw, 2.4rem)', fontWeight: 600, lineHeight: 1 }}>
              {fmtPrice(analysis.price)}
            </span>
            <span style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>last close</span>
          </div>
        </div>

        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'flex-end',
              gap: 12,
              marginBottom: 10,
            }}
          >
            {analysis.historyId && <SaveReportButton historyId={analysis.historyId} />}
            <p className="label">Risk-adjusted verdict</p>
          </div>
          <VerdictChip verdict={analysis.riskAdjusted} size="lg" />
          <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginTop: 12, maxWidth: 240 }}>
            {wasDampened ? (
              <>
                Raw signal{' '}
                <strong style={{ fontWeight: 560, color: 'var(--text)' }}>{analysis.verdict}</strong>, dampened
                under macro regime <span className="num">SRM {analysis.macro.srm.toFixed(2)}</span>
              </>
            ) : (
              <>
                Raw and risk-adjusted signals agree
                {analysis.macro.srm > 1 ? (
                  <>
                    {' '}
                    at <span className="num">SRM {analysis.macro.srm.toFixed(2)}</span>
                  </>
                ) : null}
              </>
            )}
          </p>
        </div>
      </div>
    </section>
  )
}
