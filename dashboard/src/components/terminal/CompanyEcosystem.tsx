'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import Skeleton from '@/components/ui/Skeleton'
import { EDGE_LABELS, fetchKnowledge, type CompanyKnowledge } from '@/lib/knowledge'

const TONE_COLOR = { pos: 'var(--pos)', neg: 'var(--neg)', neutral: 'var(--muted)' } as const

/**
 * Company ecosystem — leadership, corporate structure, products, industry
 * and the SEC-grounded filing timeline. Every row comes from the merged
 * knowledge graph (SEC + Wikidata, deduplicated backend-side); this
 * component renders and cites, it computes nothing.
 *
 * Loads independently of the report so a slow encyclopedic lookup never
 * delays the verdict, and renders nothing at all when no provider had
 * anything to say.
 */
export default function CompanyEcosystem({ ticker }: { ticker: string }) {
  const [state, setState] = useState<{ status: 'loading' } | { status: 'ready'; data: CompanyKnowledge | null }>({
    status: 'loading',
  })

  useEffect(() => {
    let alive = true
    setState({ status: 'loading' })
    fetchKnowledge(ticker).then((data) => {
      if (alive) setState({ status: 'ready', data })
    })
    return () => {
      alive = false
    }
  }, [ticker])

  if (state.status === 'loading') {
    return (
      <section aria-label="Company ecosystem" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
        <h3 className="h-panel" style={{ marginBottom: 14 }}>Ecosystem</h3>
        <Skeleton height={120} />
      </section>
    )
  }

  const data = state.data
  if (!data || (data.ecosystem.length === 0 && data.timeline.length === 0 && data.findings.length === 0)) {
    return null
  }

  return (
    <section aria-label="Company ecosystem" className="panel" style={{ padding: 'clamp(18px, 3vw, 24px)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 10, marginBottom: 16 }}>
        <h3 className="h-panel">Ecosystem</h3>
        <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
          {data.graph.nodes} entities · {data.graph.edges} relationships
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '0.6875rem', color: 'var(--faint)' }}>
          {data.graph.providers.join(' · ') || 'no sources'}
        </span>
      </div>

      {data.ecosystem.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: data.findings.length ? 18 : 0 }}>
          {data.ecosystem.map((group) => (
            <div key={group.key}>
              <p className="label" style={{ fontSize: '0.625rem', marginBottom: 8 }}>{group.label}</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {group.members.map((member) => {
                  const roles = member.edges.map((edge) => EDGE_LABELS[edge] ?? edge).join(' · ')
                  const content = (
                    <>
                      {member.label}
                      <span className="label" style={{ fontSize: '0.5625rem', color: 'var(--faint)' }}>{roles}</span>
                    </>
                  )
                  return member.route ? (
                    <Link
                      key={member.id}
                      href={member.route}
                      className="btn btn--ghost btn--xs"
                      style={{ border: '1px solid var(--line)', textDecoration: 'none' }}
                    >
                      {content}
                    </Link>
                  ) : (
                    <span
                      key={member.id}
                      className="btn btn--ghost btn--xs"
                      style={{ border: '1px solid var(--line)', cursor: 'default' }}
                    >
                      {content}
                    </span>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {data.findings.length > 0 && (
        <details className="disclosure">
          <summary style={{ fontSize: '0.8125rem', fontWeight: 550, color: 'var(--muted)' }}>
            Reported financials from SEC filings ({data.findings.length})
          </summary>
          <ul style={{ listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {data.findings.map((finding) => (
              <li key={finding.id} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55 }}>
                <span
                  aria-hidden="true"
                  style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: TONE_COLOR[finding.tone] }}
                />
                <span>
                  <span style={{ color: 'var(--text)' }}>{finding.text}</span>
                  {finding.evidence[0]?.source.url && (
                    <>
                      {' '}
                      <a
                        href={finding.evidence[0].source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.6875rem', color: 'var(--accent-strong)' }}
                      >
                        source
                      </a>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {data.timeline.length > 0 && (
        <details className="disclosure" style={{ marginTop: 10 }}>
          <summary style={{ fontSize: '0.8125rem', fontWeight: 550, color: 'var(--muted)' }}>
            Filing timeline ({data.timeline.length})
          </summary>
          <ul style={{ listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.timeline.map((event) => (
              <li key={event.id} style={{ display: 'flex', gap: 12, fontSize: '0.8125rem', alignItems: 'baseline' }}>
                <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)', width: 84, flexShrink: 0 }}>
                  {event.date}
                </span>
                <span style={{ color: 'var(--text)', fontWeight: 550, width: 110, flexShrink: 0 }}>{event.title}</span>
                <span style={{ color: 'var(--muted)', flex: 1, minWidth: 0 }}>{event.detail}</span>
                {event.source?.url && (
                  <a
                    href={event.source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '0.6875rem', color: 'var(--accent-strong)', flexShrink: 0 }}
                  >
                    view
                  </a>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
