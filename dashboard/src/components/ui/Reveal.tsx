'use client'

import { useEffect, useRef } from 'react'

interface RevealProps {
  children: React.ReactNode
  /** Transition delay in ms, for gentle staggering */
  delay?: number
  as?: 'div' | 'section' | 'li'
  className?: string
  style?: React.CSSProperties
}

/** Fires once when the element enters the viewport. Respects reduced motion via CSS. */
export default function Reveal({ children, delay = 0, as: Tag = 'div', className, style }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.classList.add('is-visible')
            observer.disconnect()
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -32px 0px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <Tag
      ref={ref as React.Ref<never>}
      className={`reveal${className ? ` ${className}` : ''}`}
      style={{ transitionDelay: delay ? `${delay}ms` : undefined, ...style }}
    >
      {children}
    </Tag>
  )
}
