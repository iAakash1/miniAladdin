import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { LEARN_INDEX, SOURCE_LABELS, allTopics, relatedTopics } from '@/lib/learn'

export function generateStaticParams() {
  return allTopics().map((topic) => ({ slug: topic.slug }))
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params
  const topic = LEARN_INDEX[slug]
  return topic
    ? { title: `${topic.entry.label} — Learn`, description: topic.entry.short }
    : { title: 'Learn' }
}

function Row({ label, text }: { label: string; text?: string }) {
  if (!text) return null
  return (
    <div style={{ marginBottom: 18 }}>
      <p className="label" style={{ marginBottom: 6 }}>{label}</p>
      <p style={{ fontSize: '0.9375rem', lineHeight: 1.65, color: 'var(--muted)', maxWidth: '68ch' }}>{text}</p>
    </div>
  )
}

/**
 * One Learn topic as a permanent page — the deep-link target for every
 * glossary entity in the Intelligence OS, every cross-link chip, and
 * every future citation. Server-rendered from the same authored entries
 * that power in-report Learn More disclosures: one source of truth.
 */
export default async function LearnTopicPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const topic = LEARN_INDEX[slug]
  if (!topic) notFound()
  const entry = topic.entry
  const related = relatedTopics(slug)

  return (
    <article className="container" style={{ padding: 'clamp(48px, 7vw, 80px) 0 96px', maxWidth: 820 }}>
      <p className="eyebrow" style={{ marginBottom: 12 }}>
        <Link href="/learn" style={{ textDecoration: 'none', color: 'inherit' }}>Knowledge center</Link>
        {' · '}{SOURCE_LABELS[topic.source]}
      </p>
      <h1 className="h-section" style={{ marginBottom: 14 }}>{entry.label}</h1>
      <p className="lede" style={{ marginBottom: 36 }}>{entry.short}</p>

      <Row label="Formula" text={entry.formula} />
      <Row label="Interpretation" text={entry.interpretation} />
      <Row label="What good looks like" text={entry.good} />
      <Row label="What bad looks like" text={entry.bad} />
      <Row label="Typical range" text={entry.typicalRange} />
      <Row label="Limitations" text={entry.limitations} />
      <Row label="How OmniSignal uses it" text={entry.why} />
      <Row label="Where it enters the score" text={entry.entersScore} />
      <Row label="References" text={entry.references.join(' · ')} />

      {related.length > 0 && (
        <section aria-label="Related concepts" className="hairline-top" style={{ paddingTop: 24, marginTop: 12 }}>
          <p className="label" style={{ marginBottom: 12 }}>Related concepts</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {related.map((t) => (
              <Link key={t.slug} href={`/learn/${t.slug}`} className="btn btn--secondary btn--sm" style={{ textDecoration: 'none' }}>
                {t.entry.label}
              </Link>
            ))}
          </div>
        </section>
      )}
    </article>
  )
}
