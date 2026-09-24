/**
 * The product's icon set: a handful of 16px stroke glyphs drawn inline.
 * Small enough that an icon library would cost more than it gives.
 */

const PATHS = {
  home: 'M2.5 7.2 8 2.8l5.5 4.4v6.3a.5.5 0 0 1-.5.5H9.8V10H6.2v4H3a.5.5 0 0 1-.5-.5Z',
  screen: 'M2.5 4h11M4.5 8h7M6.5 12h3',
  market: 'M2 13.5h12M2.5 11l3.2-3.6 2.8 2.2 5-5.6',
  graph: 'M4.2 4.6 11 4.1M4.8 5.8l2.4 5.6M11.2 5.3 8.6 11M4 3a1.6 1.6 0 1 1 0 3.2A1.6 1.6 0 0 1 4 3Zm8 0a1.6 1.6 0 1 1 0 3.2A1.6 1.6 0 0 1 12 3Zm-4 8a1.6 1.6 0 1 1 0 3.2A1.6 1.6 0 0 1 8 11Z',
  log: 'M4 2.5h5.5L12 5v8.5H4ZM9.5 2.5V5H12M6 8h4M6 10.5h4',
  list: 'M6 4.5h7.5M6 8h7.5M6 11.5h7.5M3 4.5h.01M3 8h.01M3 11.5h.01',
  paper: 'M3 5.5h9.5l-2.2-2.2M13 10.5H3.5l2.2 2.2',
  model: 'M8 2.5 13.5 5.3 8 8.1 2.5 5.3ZM2.5 8.2 8 11l5.5-2.8M2.5 11 8 13.8l5.5-2.8',
  flask: 'M6 2.5h4M7 2.5v4.2l-3.6 6a1 1 0 0 0 .86 1.5h7.48a1 1 0 0 0 .86-1.5L9 6.7V2.5M5.2 10.5h5.6',
  factor: 'M3.5 13.5V8.5M8 13.5v-10M12.5 13.5v-6.5M2 13.5h12',
  providers: 'M3 4.2C3 3.3 5.2 2.5 8 2.5s5 .8 5 1.7-2.2 1.7-5 1.7S3 5.1 3 4.2Zm0 0v7.6c0 .9 2.2 1.7 5 1.7s5-.8 5-1.7V4.2M3 8c0 .9 2.2 1.7 5 1.7S13 8.9 13 8',
  provenance: 'M4.5 2.5v11M4.5 8h3.5a3 3 0 0 0 3-3V2.5M11 13.5V9.5',
  book: 'M8 4.4C6.5 3.4 4.5 3 2.5 3v9c2 0 4 .4 5.5 1.4 1.5-1 3.5-1.4 5.5-1.4V3c-2 0-4 .4-5.5 1.4Zm0 0v9',
  health: 'M2 8.5h2.8l1.6-3.8 3 7.3 1.6-3.5H14',
  search: 'M7 11.5a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9Zm3.3-1.2 3.2 3.2',
  menu: 'M2.5 4.5h11M2.5 8h11M2.5 11.5h11',
  close: 'm4 4 8 8M12 4l-8 8',
  info: 'M8 14A6 6 0 1 1 8 2a6 6 0 0 1 0 12Zm0-6.2V11M8 5.2h.01',
  chevronRight: 'm6 3.5 4.5 4.5L6 12.5',
  chevronDown: 'm3.5 6 4.5 4.5L12.5 6',
  star: 'm8 2.6 1.6 3.4 3.7.4-2.8 2.5.8 3.7L8 10.7l-3.3 1.9.8-3.7-2.8-2.5 3.7-.4Z',
  external: 'M9.5 2.5h4v4M13.5 2.5 7.5 8.5M11.5 9.5v3.5a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5V5a.5.5 0 0 1 .5-.5h3.5',
  copy: 'M5.5 5.5h7v8h-7ZM3.5 10.5v-8h7',
  refresh: 'M13.5 3.5v3h-3M2.5 12.5v-3h3M3.4 6.5a5 5 0 0 1 9-1.6l1.1 1.6M12.6 9.5a5 5 0 0 1-9 1.6L2.5 9.5',
  panel: 'M2.5 3.5h11v9h-11ZM9.5 3.5v9',
  company: 'M3 13.5V3.5h6v10M9 6.5h4v7M2 13.5h12M5 6h2M5 8.5h2M5 11h2M11 9h.01M11 11h.01',
  alert: 'M8 2.8 14 13H2Zm0 4v2.8M8 11h.01',
  check: 'm3.5 8.5 3 3 6-7',
  clock: 'M8 14A6 6 0 1 1 8 2a6 6 0 0 1 0 12Zm0-9v3.2l2 1.3',
  evidence: 'M8 2.5 13 4.5v3.7c0 3-2.2 5-5 5.8-2.8-.8-5-2.8-5-5.8V4.5Zm-2.2 5.8 1.6 1.6 3-3.2',
  spark: 'M8 2v2.5M8 11.5V14M2 8h2.5M11.5 8H14M3.8 3.8l1.8 1.8M10.4 10.4l1.8 1.8M3.8 12.2l1.8-1.8M10.4 5.6l1.8-1.8',
  signOut: 'M6.5 13.5h-3a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5h3M10.5 11l3-3-3-3M13.5 8h-7',
} as const

export type IconName = keyof typeof PATHS

export default function Icon({
  name, size = 16, className, title,
}: {
  name: IconName
  size?: number
  className?: string
  /** Only when the icon is the sole content of a control. */
  title?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
    >
      {title ? <title>{title}</title> : null}
      <path d={PATHS[name]} />
    </svg>
  )
}
