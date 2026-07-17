/*
 * Clerk theming: the card is rendered CHROMELESS (transparent, no border,
 * no shadow) — the surrounding AuthShell glass panel provides all surface
 * language, in both themes. Element-level styles use CSS variables so the
 * form follows the active theme; Clerk passes them through as inline
 * styles, which resolve against the page's custom properties.
 */

const control = {
  background: 'var(--surface)',
  border: '1px solid var(--line-strong)',
  color: 'var(--text)',
  borderRadius: '6px',
}

export const clerkAppearance = {
  variables: {
    colorPrimary: '#1e6b54',
    borderRadius: '6px',
    fontFamily: "'Inter Variable', -apple-system, 'Segoe UI', sans-serif",
    fontSize: '15px',
  },
  elements: {
    rootBox: { width: '100%' },
    // Clerk v7 wraps the card in a cardBox that carries its own default
    // width (400px), border and drop shadow. Left unstyled it renders as a
    // second card that overflows the 420px AuthShell panel — neutralize it
    // so the glass shell is the only visible surface.
    cardBox: {
      width: '100%',
      maxWidth: '100%',
      background: 'transparent',
      border: 'none',
      boxShadow: 'none',
      borderRadius: 0,
    },
    card: {
      background: 'transparent',
      border: 'none',
      boxShadow: 'none',
      width: '100%',
      padding: '8px 4px',
    },
    headerTitle: {
      fontFamily: "'Newsreader Variable', Georgia, serif",
      fontWeight: 500,
      fontSize: '1.4rem',
      letterSpacing: '-0.01em',
      color: 'var(--text)',
    },
    headerSubtitle: { color: 'var(--muted)' },
    socialButtonsBlockButton: {
      ...control,
      transition: 'border-color 120ms ease-out, background 120ms ease-out',
    },
    socialButtonsBlockButtonText: { color: 'var(--text)', fontWeight: 550 },
    dividerLine: { background: 'var(--line)' },
    dividerText: { color: 'var(--faint)' },
    formFieldLabel: { color: 'var(--muted)', fontWeight: 550 },
    formFieldInput: control,
    formButtonPrimary: {
      background: 'var(--accent)',
      color: '#ffffff',
      fontWeight: 550,
      textTransform: 'none' as const,
      fontSize: '0.875rem',
      borderRadius: '6px',
    },
    footer: { background: 'transparent' },
    footerActionText: { color: 'var(--muted)' },
    footerActionLink: { color: 'var(--accent-strong)', fontWeight: 550 },
    identityPreview: control,
    identityPreviewText: { color: 'var(--text)' },
    otpCodeFieldInput: control,
    formResendCodeLink: { color: 'var(--accent-strong)' },
    // Clerk's development-instance badge: keep it, but as a quiet status
    // chip rather than a warning ("Development Preview", not an error).
    badge: {
      background: 'var(--surface-2)',
      color: 'var(--muted)',
      border: '1px solid var(--line)',
      borderRadius: '4px',
      fontWeight: 550,
      letterSpacing: '0.04em',
    },
    logoBox: { display: 'none' },

    // UserButton popover (terminal header, dark by default). Same CSS-
    // variable approach as above — previously unstyled, so it fell back to
    // Clerk's own light-mode default card and overrode the surrounding
    // dark theme whenever it opened.
    userButtonPopoverCard: {
      background: 'var(--surface)',
      border: '1px solid var(--line-strong)',
      boxShadow: 'var(--shadow-2)',
    },
    userButtonPopoverMain: { background: 'var(--surface)' },
    userButtonPopoverActionButton: { color: 'var(--text)' },
    userButtonPopoverActionButtonText: { color: 'var(--text)', fontWeight: 500 },
    userButtonPopoverActionButtonIcon: { color: 'var(--muted)' },
    userButtonPopoverFooter: { background: 'var(--surface-2)' },
    userPreviewMainIdentifier: { color: 'var(--text)' },
    userPreviewSecondaryIdentifier: { color: 'var(--muted)' },
    menuList: { background: 'var(--surface)', border: '1px solid var(--line-strong)' },
    menuItem: { color: 'var(--text)' },
  },
}
