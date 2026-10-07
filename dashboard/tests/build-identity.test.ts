/* A deployment must be able to say which commit it is.

   Production served a 14-day-old build whose /api/build answered
   `commit: "unknown"`: it had been deployed from a laptop, so Vercel recorded
   no git metadata and nothing on the site could be tied to a commit. The
   identity is now a pure function of the build-time values, so what a
   deployment reports can be pinned without a server. */

import assert from 'node:assert/strict'
import test from 'node:test'
import { buildIdentity } from '../src/lib/build-identity'

test('a git-sourced build reports its commit, branch, environment and deployment', () => {
  const id = buildIdentity({
    NEXT_PUBLIC_BUILD_SHA: '601fb7fe6f1961901ad6f7a0e6b001fe5315a68b',
    NEXT_PUBLIC_BUILD_REF: 'main',
    NEXT_PUBLIC_BUILD_ENV: 'production',
    NEXT_PUBLIC_BUILD_DEPLOYMENT: 'dpl_abc123',
    NEXT_PUBLIC_BUILD_TIME: '2026-10-07T08:00:00.000Z',
  })
  assert.deepEqual(id, {
    service: 'frontend',
    commit: '601fb7fe6f1961901ad6f7a0e6b001fe5315a68b',
    ref: 'main',
    environment: 'production',
    deployment: 'dpl_abc123',
    built_at: '2026-10-07T08:00:00.000Z',
  })
})

test('a build with no git metadata says unknown rather than inventing a commit', () => {
  const id = buildIdentity({ NEXT_PUBLIC_BUILD_SHA: 'unknown', NEXT_PUBLIC_BUILD_DEPLOYMENT: 'dpl_cli' })
  assert.equal(id.commit, 'unknown')
  assert.equal(id.ref, null)
  assert.equal(id.deployment, 'dpl_cli')
})

test('missing and blank values are null, never empty strings', () => {
  const id = buildIdentity({ NEXT_PUBLIC_BUILD_REF: '', NEXT_PUBLIC_BUILD_ENV: '   ' })
  assert.equal(id.commit, 'unknown')
  assert.equal(id.ref, null)
  assert.equal(id.environment, null)
  assert.equal(id.deployment, null)
  assert.equal(id.built_at, null)
})

test('only build-identifying fields are exposed, whatever else is in the environment', () => {
  const id = buildIdentity({
    NEXT_PUBLIC_BUILD_SHA: 'abc',
    CLERK_SECRET_KEY: 'sk_live_should_never_appear',
    RAZORPAY_KEY_SECRET: 'nope',
    BACKEND_ORIGIN: 'https://internal.example',
  })
  assert.deepEqual(Object.keys(id).sort(), ['built_at', 'commit', 'deployment', 'environment', 'ref', 'service'])
  assert.ok(!JSON.stringify(id).includes('sk_live'))
  assert.ok(!JSON.stringify(id).includes('internal.example'))
})
