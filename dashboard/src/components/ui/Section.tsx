import type { ReactNode } from 'react'

interface SectionProps {
  id: string
  title: string
  /** Small always-visible preview next to the title (e.g. an item count),
   * so a collapsed section still communicates something before opening. */
  summary?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
}

/**
 * Expandable group — native <details>/<summary> so it's keyboard- and
 * screen-reader-accessible for free and works without any client JS.
 * Mirrors the .faq-item disclosure pattern already used on the public
 * site. Used for the dashboard's Economic Conditions / Interest Rates /
 * Inflation groups: detail that matters, hidden until asked for.
 */
export default function Section({ id, title, summary, defaultOpen = false, children }: SectionProps) {
  return (
    <details className="dash-section" open={defaultOpen}>
      <summary aria-controls={id}>
        <span className="h-panel" style={{ fontSize: '0.9375rem' }}>{title}</span>
        {summary && <span className="dash-section__summary">{summary}</span>}
      </summary>
      <div id={id} className="dash-section__body fade-in">
        {children}
      </div>
    </details>
  )
}
