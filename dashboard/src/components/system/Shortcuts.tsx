/**
 * Keyboard help.
 *
 * A keyboard-first product with undiscoverable keys is a keyboard-hostile
 * product. `?` opens this from anywhere, and every entry listed here is wired —
 * a help sheet that documents a key nothing handles is worse than none.
 */
'use client'

import { useEffect, useState } from 'react'

const GROUPS: { title: string; keys: { combo: string; action: string }[] }[] = [
  {
    title: 'Global',
    keys: [
      { combo: '⌘K  /  Ctrl K', action: 'Search objects and commands' },
      { combo: '/', action: 'Same, when not typing' },
      { combo: '?', action: 'This help' },
      { combo: 'Esc', action: 'Close a palette, drawer or help sheet' },
    ],
  },
  {
    title: 'Go to',
    keys: [
      { combo: 'g c', action: 'Command' },
      { combo: 'g j', action: 'Market' },
      { combo: 'g s', action: 'Securities' },
      { combo: 'g h', action: 'Relationships' },
      { combo: 'g f', action: 'Factors' },
      { combo: 'g g', action: 'Signals' },
      { combo: 'g m', action: 'Models' },
      { combo: 'g v', action: 'Evidence' },
      { combo: 'g a', action: 'Gates' },
      { combo: 'g p', action: 'Performance' },
      { combo: 'g x', action: 'Experiments' },
      { combo: 'g w', action: 'Compare' },
      { combo: 'g q', action: 'Difference' },
      { combo: 'g b', action: 'Book' },
      { combo: 'g r', action: 'Risk' },
      { combo: 'g k', action: 'Covariance' },
      { combo: 'g d', action: 'Data' },
      { combo: 'g o', action: 'Providers' },
      { combo: 'g n', action: 'Provenance' },
      { combo: 'g y', action: 'Handbook' },
      { combo: 'g e', action: 'Memos' },
      { combo: 'g t', action: 'Timeline' },
      { combo: 'g z', action: 'Watchlists — your own lists and holdings' },
      { combo: 'g u', action: 'Calibration' },

    ],
  },
  {
    title: 'In a palette',
    keys: [
      { combo: '↑ ↓', action: 'Move the cursor' },
      { combo: '⏎', action: 'Open the selection' },
    ],
  },
  {
    title: 'In a table',
    keys: [
      { combo: '↑ ↓', action: 'Move between rows' },
      { combo: '⏎', action: 'Select the focused row' },
      { combo: 'Tab', action: 'Reach the sort control on a column header' },
      { combo: 'Space', action: 'Toggle the sort on a focused header' },
    ],
  },
]

export default function Shortcuts() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
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
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false) }}
    >
      <div className="pal" style={{ width: 'min(760px, 100%)' }}>
        <div className="sys-panel-head" style={{ borderBottom: '1px solid var(--rule-strong)' }}>
          <h2 className="sys-label" style={{ margin: 0 }}>Keyboard</h2>
          <button className="sys-btn" onClick={() => setOpen(false)}>esc</button>
        </div>
        <div className="pal-body" style={{ padding: 'var(--d-4)' }}>
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            {GROUPS.map((g) => (
              <section key={g.title}>
                <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>{g.title}</div>
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {g.keys.map((k) => (
                      <tr key={k.combo}>
                        <td style={{ width: '42%' }}><kbd className="pal-hint">{k.combo}</kbd></td>
                        <td style={{ fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>{k.action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
          </div>
          <p style={{ margin: 'var(--d-4) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
            Every key listed is wired. A help sheet documenting a key nothing
            handles is worse than no help sheet.
          </p>
        </div>
      </div>
    </div>
  )
}
