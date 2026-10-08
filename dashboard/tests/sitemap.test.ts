/* The sitemap lists what a stranger can open, and says nothing it cannot know. */

import assert from 'node:assert/strict'
import test from 'node:test'

import sitemap from '../src/app/sitemap'
import { allTopics } from '../src/lib/learn'

const entries = sitemap()
const paths = entries.map((e) => new URL(e.url).pathname)

test('every public Learn topic is listed, once', () => {
  const topics = allTopics()
  assert.ok(topics.length > 0)
  for (const topic of topics) assert.ok(paths.includes(`/learn/${topic.slug}`), topic.slug)
  assert.equal(new Set(paths).size, paths.length, 'a URL is listed twice')
})

test('nothing behind sign-in is listed', () => {
  const protectedPrefixes = ['/terminal', '/company', '/evidence', '/explore', '/beginner', '/intermediate', '/start', '/payment', '/api']
  for (const p of paths) assert.ok(!protectedPrefixes.some((x) => p === x || p.startsWith(`${x}/`)), p)
})

test('no page is claimed to have changed at the moment the sitemap was built', () => {
  for (const e of entries) assert.equal(e.lastModified, undefined, e.url)
})
