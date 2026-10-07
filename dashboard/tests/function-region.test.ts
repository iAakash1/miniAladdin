/* The API proxy runs next to the backend.

   The Vercel project defaulted to iad1 (US East) while the Cloud Run backend is
   in asia-south1 (Mumbai) and the product's users are in India. The
   `x-vercel-id` header read `bom1::iad1::…`: a request entered at Mumbai, ran
   in Virginia, then called Cloud Run back in Mumbai — two crossings of the
   planet for a call whose backend time is a few milliseconds. Warm, a proxied
   macro read took 0.6–1.1 s against 0.06 s straight to Cloud Run.

   bom1 is Mumbai. A user anywhere still pays one long hop (to the function or
   from it to the backend), so co-locating the function with the backend is
   never worse than the default and is far better for the people it is for.
   This pins the decision so a later edit cannot silently undo it. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const root = join(__dirname, '..')

test('the functions are pinned to Mumbai, the region of the backend', () => {
  const config = JSON.parse(readFileSync(join(root, 'vercel.json'), 'utf8')) as { regions?: string[] }
  assert.deepEqual(config.regions, ['bom1'])
})

test('the backend this is co-located with is in asia-south1', () => {
  const doc = readFileSync(join(root, '..', 'docs', 'CLOUD_RUN_DEPLOYMENT.md'), 'utf8')
  assert.match(doc, /\|\s*Region\s*\|\s*`asia-south1`\s*\|/, 'the documented backend region changed: revisit vercel.json')
})
