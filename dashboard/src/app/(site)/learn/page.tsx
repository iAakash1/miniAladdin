import type { Metadata } from 'next'
import Link from 'next/link'

import { SOURCE_LABELS, allTopics, type LearnSource } from '@/lib/learn'

export const metadata: Metadata = {
  title: 'Learn',
  description:
    'Every metric, indicator and concept OmniSignal uses — defined, interpreted, and connected to how the platform actually scores.',
}

const SOURCE_ORDER: LearnSource[] = ['technical', 'street', 'metric', 'factor']

/**
 * The Learn Knowledge Center index: the platform's finance curriculum as
 * one browsable page. Static, public, server-rendered — the same authored
 * glossary content that powers every in-report Learn More disclosure.
 */
export default function LearnIndexPage() {
  const topics = allTopics()
  return (
    <div className="container" style={{ padding: 'clamp(48px, 7vw, 80px) 0 96px' }}>
      <p className="eyebrow" style={{ marginBottom: 12 }}>Knowledge center</p>
      <h1 className="h-section" style={{ marginBottom: 14 }}>Learn the language of the terminal</h1>
      <p className="lede" style={{ marginBottom: 40 }}>
        Every indicator, ratio and statistic OmniSignal reports — what it means, how it&apos;s
        built, when it helps, where it fails, and exactly how the scoring engine uses it.
      </p>

      {SOURCE_ORDER.map((source) => {
        const group = topics.filter((topic) => topic.source === source)
        if (group.length === 0) return null
        return (
          <section key={source} aria-label={SOURCE_LABELS[source]} style={{ marginBottom: 36 }}>
            <h2 className="h-panel" style={{ marginBottom: 14 }}>{SOURCE_LABELS[source]}</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
              {group.map((topic) => (
                <Link
                  key={topic.slug}
                  href={`/learn/${topic.slug}`}
                  className="panel"
                  style={{ padding: '14px 16px', textDecoration: 'none', display: 'block' }}
                >
                  <p style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: 4 }}>{topic.entry.label}</p>
                  <p style={{ fontSize: '0.75rem', color: 'var(--muted)', lineHeight: 1.5 }}>
                    {topic.entry.short}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
