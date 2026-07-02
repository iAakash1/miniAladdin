interface LogoProps {
  size?: number
  withWordmark?: boolean
  className?: string
}

/**
 * Mark: three ascending signal bars inside a square frame —
 * drawn, not generated; reads at 14px and at 40px.
 */
export function LogoMark({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="0.75" y="0.75" width="18.5" height="18.5" rx="4.25" stroke="currentColor" strokeWidth="1.5" />
      <rect x="4.75" y="10.5" width="2.5" height="5" rx="0.75" fill="currentColor" />
      <rect x="8.75" y="7.5" width="2.5" height="8" rx="0.75" fill="currentColor" />
      <rect x="12.75" y="4.5" width="2.5" height="11" rx="0.75" fill="currentColor" opacity="0.55" />
    </svg>
  )
}

export default function Logo({ size = 20, withWordmark = true, className }: LogoProps) {
  return (
    <span
      className={className}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 9, color: 'var(--text)' }}
    >
      <LogoMark size={size} />
      {withWordmark && (
        <span
          style={{
            fontSize: size * 0.82,
            fontWeight: 620,
            letterSpacing: '-0.02em',
            lineHeight: 1,
          }}
        >
          OmniSignal
        </span>
      )}
    </span>
  )
}
