'use client'

/**
 * The application shell every workspace sits in.
 *
 *   top bar     brand · location · search · account
 *   rail        destinations, grouped; recent companies
 *   workspace   the one scroll container (#workspace)
 *   status bar  live system facts, read from the backend
 *
 * Page-specific explanation ("what this answers") lives in an About drawer
 * opened on request, so the workspace keeps its full width.
 */

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState, type ReactNode } from 'react'

import { type ResearchState } from './index'
import Palette, { applyStoredDensity, openPalette } from './Palette'
import Shortcuts from './Shortcuts'
import { ChartCursorProvider } from './ChartCursor'
import { MetricProvider } from './MetricContext'
import MetricInspector from './MetricInspector'
import Rail from '@/components/shell/Rail'
import TopBar from '@/components/shell/TopBar'
import StatusBar from '@/components/shell/StatusBar'
import Drawer from '@/components/shell/Drawer'
import Icon from '@/components/shell/Icon'
import { GOTO, destinationAt, viewAt } from '@/lib/destinations'
import { NAVIGATION, type NavigationSet } from '@/lib/navigation'
import { recentSnapshot } from '@/lib/symbols'

export interface RailState {
  label: string
  state: ResearchState
  detail?: string
}

export default function Workbench({
  title,
  subtitle,
  actions,
  context,
  rail,
  children,
  navigation = 'terminal',
  header = true,
  flush = false,
  width = 'default',
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  /** Explanatory content for this view, shown in the About drawer. */
  context?: ReactNode
  /** Page-specific facts for the status bar. */
  rail?: RailState[]
  children: ReactNode
  navigation?: NavigationSet
  /** False when the page renders its own header (the company workspace). */
  header?: boolean
  /** No workspace padding — the page manages its own layout. */
  flush?: boolean
  width?: 'default' | 'reading' | 'full'
}) {
  const pathname = usePathname()
  const router = useRouter()
  // Each overlay remembers the page it was opened on, so navigating away
  // closes it without an effect writing state.
  const [navOn, setNavOn] = useState<string | null>(null)
  const [aboutOn, setAboutOn] = useState<string | null>(null)
  const navOpen = navOn === pathname
  const aboutOpen = aboutOn === pathname
  const setNavOpen = (next: boolean | ((open: boolean) => boolean)) =>
    setNavOn((on) => ((typeof next === 'function' ? next(on === pathname) : next) ? pathname : null))
  const setAboutOpen = (next: boolean | ((open: boolean) => boolean)) =>
    setAboutOn((on) => ((typeof next === 'function' ? next(on === pathname) : next) ? pathname : null))

  const destination = navigation === 'terminal' ? destinationAt(pathname) : undefined
  const view = navigation === 'terminal' ? viewAt(pathname) : undefined
  const views = destination?.views
  // A destination with several views keeps its own name as the heading; the
  // tab row says which view is open.
  const heading = views && views.length > 1 && destination ? destination.label : title

  useEffect(() => { applyStoredDensity() }, [])

  // `g` then a letter: go to a destination. `g c` reopens the last company.
  useEffect(() => {
    if (navigation !== 'terminal') return undefined
    let armed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (armed) {
        armed = false
        if (timer) clearTimeout(timer)
        const key = e.key.toLowerCase()
        if (key === 'c') {
          const last = recentSnapshot()[0]
          e.preventDefault()
          if (last) router.push(`/company/${encodeURIComponent(last)}`)
          else openPalette()
          return
        }
        const dest = GOTO[key]
        if (dest) { e.preventDefault(); router.push(dest) }
        return
      }
      if (e.key === 'g') {
        armed = true
        timer = setTimeout(() => { armed = false }, 1000)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); if (timer) clearTimeout(timer) }
  }, [navigation, router])

  const set = NAVIGATION[navigation]

  return (
    <MetricProvider>
      <ChartCursorProvider>
        <div className="shell" data-nav-open={navOpen ? '' : undefined}>
          <TopBar
            navigation={navigation}
            section={set.sectionFor(pathname)}
            location={view && view.label !== destination?.label ? `${destination?.label} · ${view.label}` : heading}
            onMenu={() => setNavOpen((v) => !v)}
            navOpen={navOpen}
          />

          <Rail set={set} pathname={pathname} open={navOpen} onNavigate={() => setNavOpen(false)} />
          {navOpen ? (
            <button type="button" className="shell-scrim" aria-label="Close navigation" onClick={() => setNavOpen(false)} />
          ) : null}

          <div className="shell-main">
            <div className="ws" id="workspace" data-scroll-root="">
              {header ? (
                <header className="ws-head" data-width={width}>
                  <div className="ws-head__title">
                    <h1 className="ws-head__h1">{heading}</h1>
                    {subtitle ? <p className="ws-head__sub">{subtitle}</p> : null}
                  </div>
                  {actions || context ? (
                    <div className="ws-head__actions">
                      {actions}
                      {context ? (
                        <button
                          type="button"
                          className="sys-btn sys-btn--ghost"
                          aria-expanded={aboutOpen}
                          aria-controls="about-drawer"
                          onClick={() => setAboutOpen((v) => !v)}
                        >
                          <Icon name="info" size={14} />
                          About this view
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </header>
              ) : null}

              {header && views && views.length > 1 ? (
                <nav className="ws-tabs" aria-label={`${destination?.label} views`} data-width={width}>
                  {views.map((v) => {
                    const active = view?.href === v.href
                    return (
                      <Link
                        key={v.href}
                        href={v.href}
                        className="ws-tab"
                        aria-current={active ? 'page' : undefined}
                        title={v.answers}
                      >
                        {v.label}
                      </Link>
                    )
                  })}
                </nav>
              ) : null}

              <main id="main" className={`ws-body${flush ? ' ws-body--flush' : ''}`} data-width={width}>
                {children}
              </main>
            </div>
          </div>

          <StatusBar pageFacts={rail} />

          {context ? (
            <Drawer id="about-drawer" open={aboutOpen} onClose={() => setAboutOpen(false)} title={`About ${view?.label ?? heading}`}>
              {context}
            </Drawer>
          ) : null}

          <Palette />
          <Shortcuts />
          <MetricInspector />
        </div>
      </ChartCursorProvider>
    </MetricProvider>
  )
}
