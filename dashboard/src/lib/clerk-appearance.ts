/* Clerk theming aligned to the editorial light language. */

export const clerkAppearance = {
  variables: {
    colorPrimary: '#1e6b54',
    colorText: '#1c1b18',
    colorTextSecondary: '#5b594f',
    colorBackground: '#ffffff',
    colorInputBackground: '#ffffff',
    colorInputText: '#1c1b18',
    colorDanger: '#b3382e',
    borderRadius: '6px',
    fontFamily: "'Inter Variable', -apple-system, 'Segoe UI', sans-serif",
    fontSize: '15px',
  },
  elements: {
    card: {
      border: '1px solid #e8e6de',
      boxShadow: '0 2px 8px rgba(28, 27, 24, 0.07), 0 1px 2px rgba(28, 27, 24, 0.05)',
      borderRadius: '10px',
    },
    headerTitle: {
      fontFamily: "'Newsreader Variable', Georgia, serif",
      fontWeight: 500,
      fontSize: '1.5rem',
      letterSpacing: '-0.01em',
    },
    formButtonPrimary: {
      fontWeight: 550,
      textTransform: 'none' as const,
      fontSize: '0.875rem',
    },
    footerActionLink: { color: '#1e6b54', fontWeight: 550 },
  },
}
