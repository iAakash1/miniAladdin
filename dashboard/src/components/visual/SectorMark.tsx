/**
 * A sector's mark: one line icon per GICS sector, monochrome on a quiet
 * plate. Sector names arrive in several vendor spellings, so they are
 * normalised before lookup; an unknown sector gets a neutral mark.
 */

type SectorKey =
  | 'technology' | 'communication' | 'discretionary' | 'staples' | 'energy'
  | 'financials' | 'health' | 'industrials' | 'materials' | 'realestate'
  | 'utilities' | 'other'

const ICON: Record<SectorKey, string> = {
  technology: 'M5.5 5.5h5v5h-5ZM3.5 3.5h9v9h-9ZM6 1.5v2M10 1.5v2M6 12.5v2M10 12.5v2M1.5 6h2M1.5 10h2M12.5 6h2M12.5 10h2',
  communication: 'M8 9.5v5M5.5 14.5h5M8 9.5a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2ZM4.8 11.2a4.5 4.5 0 0 1 0-6.4M11.2 4.8a4.5 4.5 0 0 1 0 6.4M2.7 13.3a7.5 7.5 0 0 1 0-10.6M13.3 2.7a7.5 7.5 0 0 1 0 10.6',
  discretionary: 'M3 5.5h10l-.8 8.5H3.8ZM5.8 5.5V4.3a2.2 2.2 0 0 1 4.4 0v1.2',
  staples: 'M2 4h2l1.6 7h7L14 6H5M6.5 13.5h.01M11.5 13.5h.01',
  energy: 'M8 1.8c.4 2.4 3.6 4 3.6 7.3a3.6 3.6 0 0 1-7.2 0c0-1.5.7-2.5 1.5-3.3.2 1.2.8 1.9 1.5 2.2C7.4 5.6 7.3 3.6 8 1.8Z',
  financials: 'M2 6.2 8 2.5l6 3.7ZM3.5 6.5v6M6.5 6.5v6M9.5 6.5v6M12.5 6.5v6M2 13.5h12',
  health: 'M6.2 2.5h3.6v3.7h3.7v3.6H9.8v3.7H6.2V9.8H2.5V6.2h3.7Z',
  industrials: 'M8 10.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4ZM8 1.8v1.8M8 12.4v1.8M1.8 8h1.8M12.4 8h1.8M3.6 3.6l1.3 1.3M11.1 11.1l1.3 1.3M3.6 12.4l1.3-1.3M11.1 4.9l1.3-1.3',
  materials: 'M8 1.8 13.5 5v6L8 14.2 2.5 11V5ZM8 8 13.5 5M8 8 2.5 5M8 8v6.2',
  realestate: 'M2.5 14V6.5L8 2.5l5.5 4V14ZM6.3 14v-4h3.4v4M1.5 14h13',
  utilities: 'M9 1.8 3.8 9h3.7l-.9 5.2L12.2 7H8.4Z',
  other: 'M3 3h4v4H3ZM9 3h4v4H9ZM3 9h4v4H3ZM9 9h4v4H9Z',
}

const LABEL: Record<SectorKey, string> = {
  technology: 'Technology',
  communication: 'Communication services',
  discretionary: 'Consumer discretionary',
  staples: 'Consumer staples',
  energy: 'Energy',
  financials: 'Financials',
  health: 'Health care',
  industrials: 'Industrials',
  materials: 'Materials',
  realestate: 'Real estate',
  utilities: 'Utilities',
  other: 'Sector',
}

export function sectorKey(sector?: string | null): SectorKey {
  const s = (sector ?? '').toLowerCase()
  if (!s) return 'other'
  if (/tech|semicon|software|electronic|computer|information/.test(s)) return 'technology'
  if (/communic|media|telecom|entertain|interactive/.test(s)) return 'communication'
  if (/discretion|cyclical|retail|auto|apparel|leisure|restaurant/.test(s)) return 'discretionary'
  if (/staple|defensive|beverage|food|household|tobacco/.test(s)) return 'staples'
  if (/energy|oil|gas/.test(s)) return 'energy'
  if (/financ|bank|insur|capital market|credit/.test(s)) return 'financials'
  if (/health|pharma|biotech|medical/.test(s)) return 'health'
  if (/industr|aerospace|defen|transport|machinery|airline/.test(s)) return 'industrials'
  if (/material|chemical|metal|mining|steel|paper/.test(s)) return 'materials'
  if (/real estate|reit|property/.test(s)) return 'realestate'
  if (/utilit|electric|water/.test(s)) return 'utilities'
  return 'other'
}

export function sectorLabel(sector?: string | null): string {
  const key = sectorKey(sector)
  return key === 'other' && sector ? sector : LABEL[key]
}

/** The sector's line glyph alone, for decorative use at large sizes. */
export function SectorGlyph({ sector, size, className }: { sector?: string | null; size: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={0.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={ICON[sectorKey(sector)]} />
    </svg>
  )
}

export default function SectorMark({ sector, size = 20, label = false }: {
  sector?: string | null
  size?: number
  /** Render the sector name beside the mark. */
  label?: boolean
}) {
  const key = sectorKey(sector)
  const name = sectorLabel(sector)
  return (
    <span className="smark" data-sector={key} title={label ? undefined : name}>
      <span className="smark__plate" style={{ width: size, height: size }} aria-hidden>
        <svg width={Math.round(size * 0.62)} height={Math.round(size * 0.62)} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round">
          <path d={ICON[key]} />
        </svg>
      </span>
      {label ? <span className="smark__label">{name}</span> : null}
    </span>
  )
}
