'use client'

import { safeDecode } from '@/lib/page-title'
import Link from 'next/link'
import { useSyncExternalStore } from 'react'

import Icon from '@/components/shell/Icon'
import { Shortcut } from '@/components/system/Shortcut'
import ModeSwitch from '@/components/beginner/ModeSwitch'
import { LogoMark } from '@/components/ui/Logo'
import { destinationAt } from '@/lib/destinations'
import type { NavigationDefinition } from '@/lib/navigation'
import { emptySnapshot, recentSnapshot, subscribeSymbols } from '@/lib/symbols'

function isActive(pathname: string, href: string, terminal: boolean): boolean {
  if (terminal) return destinationAt(pathname)?.href === href
  return pathname === href || (href !== '/beginner' && href !== '/intermediate' && pathname.startsWith(`${href}/`))
}

/* ── collapsed rail ──────────────────────────────────────────────────────
   A desktop preference: the rail folds to its icons and the workspace takes
   the width. Kept in this browser only; the server always renders it open,
   so the first paint never disagrees with the markup. */

const RAIL_KEY = 'omni.rail'
const railListeners = new Set<() => void>()

function readCollapsed(): boolean {
  try { return window.localStorage.getItem(RAIL_KEY) === 'collapsed' } catch { return false }
}

export function setRailCollapsed(collapsed: boolean): void {
  try { window.localStorage.setItem(RAIL_KEY, collapsed ? 'collapsed' : 'open') } catch { /* private mode: this page only */ }
  railListeners.forEach((l) => l())
}

function subscribeRail(onChange: () => void) {
  railListeners.add(onChange)
  window.addEventListener('storage', onChange)
  return () => { railListeners.delete(onChange); window.removeEventListener('storage', onChange) }
}

export function useRailCollapsed(): boolean {
  return useSyncExternalStore(subscribeRail, readCollapsed, () => false)
}

export default function Rail({
  set, pathname, open, onNavigate, collapsed = false,
}: {
  set: NavigationDefinition
  pathname: string
  open: boolean
  onNavigate: () => void
  /** Desktop only: icons, with each name as the link's tooltip. */
  collapsed?: boolean
}) {
  const recent = useSyncExternalStore(subscribeSymbols, recentSnapshot, emptySnapshot)
  const terminal = set.home === '/terminal/command'
  const currentSymbol = pathname.startsWith('/company/')
    ? safeDecode(pathname.split('/')[2]).toUpperCase()
    : null

  return (
    <nav className="shell-rail" data-open={open ? '' : undefined} aria-label="Primary">
      <div className="rail-head">
        <Link href={set.home} className="rail-brand" aria-label="OmniSignal home" onClick={onNavigate}>
          <LogoMark size={18} />
          <span className="rail-brand__name">OmniSignal</span>
        </Link>
        <button
          type="button"
          className="rail-collapse sys-btn sys-btn--ghost sys-btn--icon sys-btn--xs"
          onClick={() => setRailCollapsed(!collapsed)}
          aria-pressed={collapsed}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          <Icon name="sidebar" size={14} />
        </button>
      </div>

      <div className="rail-scroll">
        {set.groups.map((group) => (
          <div className="rail-group" key={group.group}>
            <p className="rail-group__label">{group.group}</p>
            <ul className="rail-list">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href, terminal)
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="rail-link"
                      aria-current={active ? 'page' : undefined}
                      onClick={onNavigate}
                      title={collapsed ? item.label : undefined}
                    >
                      <Icon name={item.icon} className="rail-link__icon" />
                      <span className="rail-link__label">{item.label}</span>
                      {item.key ? <kbd className="rail-link__key" aria-hidden>G {item.key.toUpperCase()}</kbd> : null}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}

        {terminal ? (
          <div className="rail-group rail-group--recent">
            <p className="rail-group__label">Recent companies</p>
            {recent.length ? (
              <ul className="rail-list">
                {recent.slice(0, 6).map((sym) => (
                  <li key={sym}>
                    <Link
                      href={`/company/${encodeURIComponent(sym)}`}
                      className="rail-link rail-link--symbol"
                      aria-current={currentSymbol === sym ? 'page' : undefined}
                      onClick={onNavigate}
                    >
                      <span className="rail-sym">{sym}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rail-empty">Companies you open appear here.</p>
            )}
          </div>
        ) : null}

        {terminal ? (
          /* The top bar's detail-level select is hidden below 1024px; on a
             phone this is the way to the other two experiences. */
          <div className="rail-group rail-group--narrow">
            <p className="rail-group__label">Detail level</p>
            <div className="rail-modes">
              <ModeSwitch to="intermediate" compact />
              <ModeSwitch to="beginner" compact />
            </div>
          </div>
        ) : (
          <div className="rail-group rail-group--modes">
            <p className="rail-group__label">Detail level</p>
            <div className="rail-modes">
              {set.home !== '/beginner' ? <ModeSwitch to="beginner" compact /> : null}
              {set.home !== '/intermediate' ? <ModeSwitch to="intermediate" compact /> : null}
              <ModeSwitch to="advanced" compact />
            </div>
          </div>
        )}
      </div>

      <div className="rail-foot">
        <span><kbd><Shortcut k="K" /></kbd> Search</span>
        <span><kbd>?</kbd> Shortcuts</span>
      </div>
    </nav>
  )
}
