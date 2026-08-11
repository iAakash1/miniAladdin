interface EmptyStateProps {
  title: string
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
export default function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && (
        <div className="empty-state__icon" aria-hidden="true">
          {icon}
        </div>
      )}
      <p className="empty-state__title">{title}</p>
      {description && <p className="empty-state__body">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  )
}
