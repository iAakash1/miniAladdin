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

/** One entry of the reference: the label in its own column, the text at reading size. */
function Row({ label, text, formula }: { label: string; text?: string; formula?: boolean }) {
  if (!text) return null
  return (
    <div className="lt__row">
      <dt>{label}</dt>
      <dd>{formula ? <code className="lt__formula">{text}</code> : text}</dd>
    </div>
  )
}

export default async function LearnTopicPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const topic = LEARN_INDEX[slug]
  if (!topic) notFound()
  const entry = topic.entry
  const related = relatedTopics(slug)

  return (
    <article className="container lt" style={{ paddingTop: 'clamp(48px, 7vw, 80px)', paddingBottom: 96 }}>
      <p className="eyebrow" style={{ marginBottom: 12 }}>
        <Link href="/learn" style={{ textDecoration: 'none', color: 'inherit' }}>Knowledge center</Link>
        {' · '}{SOURCE_LABELS[topic.source]}
      </p>
      <h1 className="h-section" style={{ marginBottom: 14 }}>{entry.label}</h1>
      <p className="lede">{entry.short}</p>

      <dl className="lt__list">
        <Row label="Formula" text={entry.formula} formula />
        <Row label="Interpretation" text={entry.interpretation} />
        <Row label="What good looks like" text={entry.good} />
        <Row label="What bad looks like" text={entry.bad} />
        <Row label="Typical range" text={entry.typicalRange} />
        <Row label="Limitations" text={entry.limitations} />
      </dl>

      {entry.why || entry.entersScore ? (
        <section className="lt__use" aria-labelledby="lt-use-h">
          <h2 className="lt__use-h" id="lt-use-h">In OmniSignal</h2>
          <dl className="lt__list lt__list--use">
            <Row label="How it is used" text={entry.why} />
            <Row label="Where it enters the score" text={entry.entersScore} />
          </dl>
        </section>
      ) : null}

      <dl className="lt__list lt__list--refs">
        <Row label="References" text={entry.references.join(' · ')} />
      </dl>

      {related.length > 0 && (
        <section aria-label="Related concepts" className="lt__related">
          <p className="sys-label" style={{ marginBottom: 12 }}>Related concepts</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {related.map((t) => (
              <Link key={t.slug} href={`/learn/${t.slug}`} className="sys-btn" style={{ textDecoration: 'none' }}>
                {t.entry.label}
              </Link>
            ))}
          </div>
        </section>
      )}
    </article>
  )
}
