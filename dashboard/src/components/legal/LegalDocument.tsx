import Link from 'next/link'
import type { ReactNode } from 'react'

import { legalDate } from '@/lib/legal'

export interface LegalSection {
  id: string
  title: string
  body: ReactNode
}

/**
 * The frame both legal pages share: a title, the date the wording last
 * changed, a plain-language summary, a contents list and numbered sections
 * with stable anchors, so a section can be linked to and read on its own.
 */
export default function LegalDocument({
  eyebrow, title, summary, sections, related,
}: {
  eyebrow: string
  title: string
  summary: ReactNode
  sections: LegalSection[]
  related: { href: string; label: string }
}) {
  return (
    <div className="container legal">
      <header className="legal__head">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="h-section">{title}</h1>
        <p className="legal__meta">
          Last updated {legalDate()} · <Link href={related.href}>{related.label}</Link>
        </p>
        <div className="legal__summary">{summary}</div>
      </header>

      <div className="legal__layout">
        <nav className="legal__toc" aria-label="Contents">
          <p className="sys-label">Contents</p>
          <ol>
            {sections.map((s, i) => (
              <li key={s.id}><a href={`#${s.id}`}><span className="legal__num">{i + 1}.</span> {s.title}</a></li>
            ))}
          </ol>
        </nav>

        <div className="legal__body">
          {sections.map((s, i) => (
            <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="legal__section">
              <h2 id={`${s.id}-h`}><span className="legal__num">{i + 1}.</span> {s.title}</h2>
              {s.body}
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
