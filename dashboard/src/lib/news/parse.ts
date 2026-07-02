/* ============================================================
   RSS/Atom parsing — pure functions, no network.
   Handles RSS 2.0 (Yahoo, Dow Jones, CNBC) and Atom, including
   media:content / media:thumbnail / enclosure images.
   ============================================================ */

import { XMLParser } from 'fast-xml-parser'

export interface ParsedItem {
  title: string
  url: string
  summary: string
  publishedAt: string // ISO
  image: string | null
  author: string | null
}

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  trimValues: true,
})

type XmlNode = Record<string, unknown>

function asArray<T>(v: T | T[] | undefined | null): T[] {
  if (v == null) return []
  return Array.isArray(v) ? v : [v]
}

function text(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number') return String(v)
  if (typeof v === 'object') {
    const node = v as XmlNode
    if (typeof node['#text'] === 'string') return node['#text'] as string
    if (typeof node['#text'] === 'number') return String(node['#text'])
  }
  return ''
}

/** Strip tags/entities left behind by feeds that embed HTML in descriptions. */
export function cleanText(raw: string): string {
  return (
    raw
      .replace(/<!\[CDATA\[|\]\]>/g, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&apos;/gi, "'")
      .replace(/&quot;/gi, '"')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      // Numeric character references, hex and decimal (e.g. &#x2019; &#8217;),
      // which several Dow Jones feeds double-encode.
      .replace(/&#x([0-9a-f]{1,6});/gi, (_, hex: string) => safeCodePoint(parseInt(hex, 16)))
      .replace(/&#(\d{1,7});/g, (_, dec: string) => safeCodePoint(parseInt(dec, 10)))
      .replace(/\s+/g, ' ')
      .trim()
  )
}

function safeCodePoint(code: number): string {
  try {
    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : ''
  } catch {
    return ''
  }
}

function truncate(s: string, max = 240): string {
  if (s.length <= max) return s
  const cut = s.slice(0, max)
  return `${cut.slice(0, Math.max(0, cut.lastIndexOf(' ')))}…`
}

function toIso(dateStr: string): string | null {
  const t = Date.parse(dateStr)
  return Number.isNaN(t) ? null : new Date(t).toISOString()
}

function extractImage(item: XmlNode): string | null {
  const candidates: Array<XmlNode | undefined> = [
    ...asArray(item['media:content'] as XmlNode | XmlNode[]),
    ...asArray(item['media:thumbnail'] as XmlNode | XmlNode[]),
    ...asArray((item['media:group'] as XmlNode | undefined)?.['media:content'] as XmlNode | XmlNode[]),
    ...asArray(item['enclosure'] as XmlNode | XmlNode[]),
  ]
  for (const c of candidates) {
    if (!c) continue
    const url = (c['@_url'] as string) ?? ''
    const type = (c['@_type'] as string) ?? ''
    const width = parseInt((c['@_width'] as string) ?? '0', 10)
    const looksImage = /\.(jpe?g|png|webp|gif)(\?|$)/i.test(url) || type.startsWith('image/') || !type
    if (url && looksImage && url.startsWith('http') && width !== 1) return url
  }
  return null
}

function parseRssItem(item: XmlNode): ParsedItem | null {
  const title = cleanText(text(item.title))
  const url = text(item.link) || (item['guid'] ? text(item['guid']) : '')
  if (!title || !url.startsWith('http')) return null
  return {
    title,
    url,
    summary: truncate(cleanText(text(item.description))),
    publishedAt: toIso(text(item.pubDate) || text(item['dc:date'])) ?? new Date().toISOString(),
    image: extractImage(item),
    author: cleanText(text(item['dc:creator']) || text(item.author)) || null,
  }
}

function parseAtomEntry(entry: XmlNode): ParsedItem | null {
  const title = cleanText(text(entry.title))
  const links = asArray(entry.link as XmlNode | XmlNode[])
  const alt = links.find((l) => (l['@_rel'] ?? 'alternate') === 'alternate') ?? links[0]
  const url = (alt?.['@_href'] as string) ?? ''
  if (!title || !url.startsWith('http')) return null
  const authorNode = entry.author as XmlNode | undefined
  return {
    title,
    url,
    summary: truncate(cleanText(text(entry.summary) || text(entry.content))),
    publishedAt: toIso(text(entry.published) || text(entry.updated)) ?? new Date().toISOString(),
    image: extractImage(entry),
    author: authorNode ? cleanText(text(authorNode.name)) || null : null,
  }
}

/** Parse an RSS 2.0 or Atom feed. Malformed feeds return []. */
export function parseFeedXml(xml: string): ParsedItem[] {
  let doc: XmlNode
  try {
    doc = parser.parse(xml) as XmlNode
  } catch {
    return []
  }

  const rss = doc.rss as XmlNode | undefined
  const channel = rss?.channel as XmlNode | undefined
  if (channel) {
    return asArray(channel.item as XmlNode | XmlNode[])
      .map(parseRssItem)
      .filter((i): i is ParsedItem => i !== null)
  }

  const feed = doc.feed as XmlNode | undefined
  if (feed) {
    return asArray(feed.entry as XmlNode | XmlNode[])
      .map(parseAtomEntry)
      .filter((i): i is ParsedItem => i !== null)
  }

  return []
}
