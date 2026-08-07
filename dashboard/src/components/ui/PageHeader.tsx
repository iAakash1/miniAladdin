import type { ReactNode } from 'react'

/**
 * The one way a page introduces itself.
 *
 * Before this, every route invented its own header. Three of them repeated
 * the identical `style={{ fontSize: '1rem', marginBottom: 6 }}` override
 * verbatim, which is the tell that the token was wrong rather than the usage
 * — and several pages opened at `<h2>`, so they shipped with no `<h1>` at
 * all. A screen reader announcing a document outline that starts at level
 * two is not a styling detail; it is a broken page.
 *
 * So this owns three things and nothing else: the heading level, the type
 * scale, and the rhythm between title, lede and the content beneath. Pages
 * supply words and, optionally, one action cluster.
 *
 * `lede` is capped near 68 characters per line here rather than at each call
 * site, because line length is a typographic decision that should be made
 * once. It is the single most-copied magic number the old headers carried.
 */
export default function PageHeader({
  eyebrow,
  title,
  lede,
  actions,
  meta,
}: {
  /** Small label above the title — the section a page belongs to. */
  eyebrow?: string
  title: string
  /** One or two sentences on what question this page answers. */
  lede?: ReactNode
  /** Buttons or inputs, aligned to the baseline of the title block. */
  actions?: ReactNode
  /** Quiet supporting facts: counts, timestamps, data provenance. */
  meta?: ReactNode
}) {
  return (
    <header className="page-head">
      <div className="page-head__text">
        {eyebrow && <span className="page-head__eyebrow">{eyebrow}</span>}
        <h1 className="page-head__title">{title}</h1>
        {lede && <p className="page-head__lede">{lede}</p>}
        {meta && <div className="page-head__meta">{meta}</div>}
      </div>
      {actions && <div className="page-head__actions">{actions}</div>}
    </header>
  )
}
