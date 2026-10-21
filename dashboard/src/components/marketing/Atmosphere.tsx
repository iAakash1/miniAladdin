'use client'

import { useEffect } from 'react'

/**
 * Sections marked `data-reveal` fade up as they enter the viewport. The
 * stylesheet hides them only once this has armed the page, so a reader
 * without JavaScript, or with reduced motion, sees everything at once.
 *
 * It never changes content.
 */
export default function Atmosphere() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const targets = [...document.querySelectorAll<HTMLElement>('[data-reveal]')]
    if (!targets.length || !('IntersectionObserver' in window)) return

    const root = document.documentElement
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.setAttribute('data-revealed', '')
          observer.unobserve(entry.target)
        }
      },
      { rootMargin: '0px 0px -10% 0px', threshold: 0.06 },
    )
    // Anything already on screen is shown before the page is armed, so the
    // first paint never blinks.
    for (const el of targets) {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.9) el.setAttribute('data-revealed', '')
      else observer.observe(el)
    }
    root.classList.add('od-reveal-armed')
    return () => {
      observer.disconnect()
      root.classList.remove('od-reveal-armed')
    }
  }, [])

  return null
}
