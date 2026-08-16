interface EmptyStateProps {
  title: string
  /** Heading level for the title. Defaults to a plain <p>, which is right
   *  for an empty state nested inside a page that already has structure —
   *  it should not inject a heading into someone else's outline. Pass a
   *  heading only where the empty state *is* the page's main content, as on
   *  /terminal/analyze, whose entire body is this component. */
  titleAs?: 'p' | 'h1' | 'h2'
  description?: string
  action?: React.ReactNode
  icon?: React.ReactNode
}

/**
 * The state a surface shows when it has nothing to show.
 *
 * Bounded by a dashed rule rather than a solid card: dashed reads as "space
 * reserved for content that is not here yet", which is the actual message.
 * A solid, shadowed card reads as a finished object and makes an empty
 * screen look like a broken one.
 *
 * Styling moved out of inline objects and into `.empty-state` so every empty
 * surface in the product shares one treatment — previously each caller
 * inherited a copy of the same six style properties, which is how they drift.
 */
export default function EmptyState({ title, titleAs: TitleTag = 'p', description, action, icon }: EmptyStateProps) {
  return (
    /* `gridfield` rules the empty area faintly and fades the ruling out
       before it reaches the text — adapted from Uiverse `kencode7/
       perfect-puma-86`, whose mechanism is a repeating line gradient under a
       mask that dissolves it. An empty surface with nothing at all in it
       reads as a rendering failure; ruled space reads as space, which is
       what an empty state is actually reporting. */
    <div className="empty-state gridfield">
      {/* A quiet grid glyph when the caller supplies no icon. An empty
          surface with nothing in it reads as unfinished; a small mark reads
          as "this is a place that holds things, and it is empty". */}
      <div className="empty-state__icon" aria-hidden="true">
        {icon ?? <span className="empty-glyph" />}
      </div>
      <TitleTag className="empty-state__title">{title}</TitleTag>
      {description && <p className="empty-state__body">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  )
}
