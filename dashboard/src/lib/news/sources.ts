import type { NewsCategory } from '../types'

export interface FeedSource {
  /** Short label shown on cards */
  name: string
  url: string
  /** Category assumed when keyword classification is inconclusive */
  defaultCategory: NewsCategory | null
}

/**
 * Feed registry. Every feed is optional at runtime: a failing feed is
 * skipped and reported in the response `sources` array, never fatal.
 * Yahoo + Dow Jones feeds verified live July 2026.
 */
export const FEED_SOURCES: FeedSource[] = [
  {
    name: 'Yahoo Finance',
    url: 'https://finance.yahoo.com/news/rssindex',
    defaultCategory: null, // broad — classify per item
  },
  {
    name: 'MarketWatch',
    url: 'https://feeds.content.dowjones.io/public/rss/mw_topstories',
    defaultCategory: 'markets',
  },
  {
    name: 'MarketWatch',
    url: 'https://feeds.content.dowjones.io/public/rss/mw_marketpulse',
    defaultCategory: 'markets',
  },
  {
    name: 'CNBC',
    url: 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114',
    defaultCategory: null,
  },
  {
    name: 'CNBC',
    url: 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258',
    defaultCategory: 'economy',
  },
  {
    name: 'CNBC',
    url: 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910',
    defaultCategory: 'technology',
  },
]

export const NEWS_CATEGORIES: Array<{ value: NewsCategory; label: string }> = [
  { value: 'markets', label: 'Markets' },
  { value: 'economy', label: 'Economy' },
  { value: 'companies', label: 'Companies' },
  { value: 'technology', label: 'Technology' },
  { value: 'crypto', label: 'Crypto' },
]
