'use client'

/**
 * Keyboard help. `?` opens it from anywhere; every key listed is wired, and
 * the navigation chords are read from the destination registry.
 */

import { useEffect, useState } from 'react'

import Icon from '@/components/shell/Icon'
import { DESTINATIONS } from '@/lib/destinations'

const GROUPS: { title: string; keys: { combo: string; action: string }[] }[] = [
  {
    title: 'Global',
    keys: [
      { combo: '⌘K · Ctrl K', action: 'Search companies, themes and commands' },
      { combo: '/', action: 'Search, when not typing' },
      { combo: '?', action: 'This sheet' },
      { combo: 'Esc', action: 'Close a palette, drawer or sheet' },
      { combo: 'g c', action: 'Reopen the last company' },
    ],
  },
  ...DESTINATIONS.map((g) => ({
    title: `Go to · ${g.group}`,
    keys: g.items.map((d) => ({ combo: `g ${d.key}`, action: d.label })),
  })),
  {
    title: 'In a table',
    keys: [
      { combo: 'j · ↓', action: 'Next row' },
      { combo: 'k · ↑', action: 'Previous row' },
      { combo: 'Home · End', action: 'First and last row' },
      { combo: '↵ · Space', action: 'Open the focused row' },
    ],
  },
]

export default function Shortcuts() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
      if (e.key === '?' && !typing) { e.preventDefault(); setOpen((v) => !v) }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!open) return null

  return (
    <div
      className="pal-backdrop"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false) }}
    >
      <div className="pal pal--wide" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
        <div className="pal-title">
          <h2>Keyboard</h2>
          <button type="button" className="sys-btn sys-btn--icon" onClick={() => setOpen(false)} aria-label="Close">
            <Icon name="close" size={14} />
          </button>
        </div>
        <div className="keys-grid">
          {GROUPS.map((g) => (
            <section key={g.title} className="keys-group">
              <h3 className="sys-label">{g.title}</h3>
              <dl>
                {g.keys.map((k) => (
                  <div key={k.combo} className="keys-row">
                    <dt><kbd>{k.combo}</kbd></dt>
                    <dd>{k.action}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
