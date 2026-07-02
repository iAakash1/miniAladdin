'use client'

import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

export function applyTheme(theme: Theme, persist: boolean) {
  document.documentElement.dataset.theme = theme
  if (persist) {
    try {
      localStorage.setItem('omni-theme', theme)
    } catch {
      /* private mode */
    }
  }
}

/* The <html data-theme> attribute is the single source of truth (set
   pre-paint by the root layout script). Subscribe via MutationObserver so
   every toggle instance — and ThemeSync — stays in agreement. */
function subscribeToTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}

function useTheme(): Theme {
  return useSyncExternalStore(
    subscribeToTheme,
    () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'),
    () => 'light',
  )
}

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <circle cx="7.5" cy="7.5" r="3.25" stroke="currentColor" strokeWidth="1.4" />
      {[
        [7.5, 0.6, 7.5, 2.4],
        [7.5, 12.6, 7.5, 14.4],
        [0.6, 7.5, 2.4, 7.5],
        [12.6, 7.5, 14.4, 7.5],
        [2.6, 2.6, 3.9, 3.9],
        [11.1, 11.1, 12.4, 12.4],
        [2.6, 12.4, 3.9, 11.1],
        [11.1, 3.9, 12.4, 2.6],
      ].map(([x1, y1, x2, y2], i) => (
        <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      ))}
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path
        d="M13 9.2A6 6 0 0 1 5.8 2a6 6 0 1 0 7.2 7.2Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function ThemeToggle() {
  const theme = useTheme()

  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm"
      onClick={() => applyTheme(theme === 'dark' ? 'light' : 'dark', true)}
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
      style={{ width: 32, padding: 0 }}
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </button>
  )
}
