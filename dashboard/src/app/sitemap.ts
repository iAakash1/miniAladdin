import type { MetadataRoute } from 'next'

import { allTopics } from '@/lib/learn'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://omnisignalterminal.vercel.app'

/**
 * The pages a search engine may index: the ones the edge serves without signing in.
 *
 * No `lastModified`. A `new Date()` here said every page changed at the moment the
 * sitemap was generated, which is never true and teaches a crawler to ignore the
 * field; the content has no modification time to report, so none is reported.
 * Each Learn topic is a permanent, server-rendered page and is listed with the index.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE_URL, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/news`, changeFrequency: 'hourly', priority: 0.8 },
    { url: `${SITE_URL}/learn`, changeFrequency: 'monthly', priority: 0.6 },
    ...allTopics().map((topic) => ({
      url: `${SITE_URL}/learn/${topic.slug}`,
      changeFrequency: 'monthly' as const,
      priority: 0.4,
    })),
  ]
}
