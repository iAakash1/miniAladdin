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
 *
 * The title is a real <h2>, not a styled span. Methodology is seven of
 * these and Validation is ten, and while the title rendered as a span both
 * pages exposed exactly one heading — the h1 — so the document outline a
 * screen reader (or a "jump to section" shortcut) builds from was empty.
 * `<summary>`'s content model explicitly permits heading content, so this
 * costs nothing and is not a workaround. Every call site sits directly
 * under the page's h1 with no intervening section, which is why the level
 * is fixed at 2 rather than configurable.
 */
export default function Section({ id, title, summary, defaultOpen = false, children }: SectionProps) {
  return (
    <details className="dash-section" open={defaultOpen}>
      <summary aria-controls={id}>
        <h2 className="h-panel" style={{ fontSize: '0.9375rem' }}>{title}</h2>
        {summary && <span className="dash-section__summary">{summary}</span>}
      </summary>
      <div id={id} className="dash-section__body fade-in">
        {children}
      </div>
    </details>
  )
}
