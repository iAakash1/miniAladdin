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
 *
 * Set as a reference index rather than a wall of cards: a contents column
 * names the sections and their sizes, and each section is a ruled list of
 * terms with the one line that defines them.
 */
export default function LearnIndexPage() {
  const topics = allTopics()
  const sections = SOURCE_ORDER
    .map((source) => ({ source, items: topics.filter((topic) => topic.source === source) }))
    .filter((s) => s.items.length > 0)

  return (
    <div className="container learn" style={{ paddingTop: 'clamp(48px, 7vw, 80px)', paddingBottom: 96 }}>
      <header className="learn__head">
        <p className="eyebrow" style={{ marginBottom: 12 }}>Knowledge center</p>
        <h1 className="h-section" style={{ marginBottom: 14 }}>Learn the language of the terminal</h1>
        <p className="lede">
          Every indicator, ratio and statistic OmniSignal reports — what it means, how it&apos;s
          built, when it helps, where it fails, and exactly how the scoring engine uses it.
        </p>
      </header>

      <div className="learn__body">
        <nav className="learn__toc" aria-label="Sections">
          <p className="learn__toc-k">{topics.length} entries</p>
          <ol>
            {sections.map(({ source, items }) => (
              <li key={source}>
                <a href={`#learn-${source}`}>
                  <span>{SOURCE_LABELS[source]}</span>
                  <span className="learn__toc-n">{items.length}</span>
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="learn__sections">
          {sections.map(({ source, items }) => (
            <section key={source} id={`learn-${source}`} aria-labelledby={`learn-${source}-h`} className="learn__section">
              <h2 className="learn__section-h" id={`learn-${source}-h`}>{SOURCE_LABELS[source]}</h2>
              <ul className="learn__list">
                {items.map((topic) => (
                  <li key={topic.slug}>
                    <Link href={`/learn/${topic.slug}`} className="learn__item">
                      <span className="learn__term">{topic.entry.label}</span>
                      <span className="learn__def">{topic.entry.short}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
