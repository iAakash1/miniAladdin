interface EmptyStateProps {
  title: string
  description?: string
  action?: React.ReactNode
  icon?: React.ReactNode
}

export default function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        gap: 10,
        padding: '56px 24px',
      }}
    >
      {icon && (
        <div style={{ color: 'var(--faint)', marginBottom: 4 }} aria-hidden="true">
          {icon}
        </div>
      )}
      <p className="h-panel" style={{ color: 'var(--text)' }}>
        {title}
      </p>
      {description && (
        <p style={{ fontSize: '0.875rem', color: 'var(--muted)', maxWidth: 380, lineHeight: 1.6 }}>
          {description}
        </p>
      )}
      {action && <div style={{ marginTop: 10 }}>{action}</div>}
    </div>
  )
}
