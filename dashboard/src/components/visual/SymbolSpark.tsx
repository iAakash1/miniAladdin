'use client'

import { useEffect, useRef, useState } from 'react'

import Sparkline from '@/components/ui/Sparkline'
import { readResource } from '@/lib/resource'

/**
 * Three months of closes for one symbol, loaded only once the row is on
 * screen. It reads the same server-side series cache the quote request just
 * filled, and the shared resource cache, so a list of sparklines costs no
 * extra vendor calls. Renders nothing when no series comes back.
 */
export default function SymbolSpark({ symbol, width = 72, height = 22 }: {
  symbol: string
  width?: number
  height?: number
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const [visible, setVisible] = useState(false)
  const [points, setPoints] = useState<{ for: string; values: number[] } | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || visible) return undefined
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setVisible(true); io.disconnect() }
    }, { rootMargin: '160px' })
    io.observe(el)
    return () => io.disconnect()
  }, [visible])

  useEffect(() => {
    if (!visible) return undefined
    let alive = true
    readResource<{ prices?: Array<{ close: number }> }>(`/api/chart/${encodeURIComponent(symbol)}?period=3mo`, 'snapshot')
      .then((d) => {
        if (!alive) return
        setPoints({ for: symbol, values: (d.prices ?? []).map((p) => p.close).filter((v) => Number.isFinite(v)) })
      })
      .catch(() => { if (alive) setPoints({ for: symbol, values: [] }) })
    return () => { alive = false }
  }, [visible, symbol])

  const values = points?.for === symbol ? points.values : null
  return (
    <span ref={ref} className="sspark" style={{ width, height }} data-state={values === null ? 'loading' : values.length > 1 ? 'ready' : 'empty'}>
      {values && values.length > 1 ? <Sparkline points={values} width={width} height={height} /> : null}
    </span>
  )
}
