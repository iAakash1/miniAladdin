/* A failure is described to the reader in words, never as the raw message. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { describeFailure, readerError } from '../src/lib/failure'
import { ResourceError } from '../src/lib/resource'

test('transport failures read as the service not being reachable', () => {
  assert.equal(readerError('Failed to fetch'), 'The service could not be reached')
  assert.equal(readerError('NetworkError when attempting to fetch resource.'), 'The service could not be reached')
})

test('status codes become plain words', () => {
  assert.equal(readerError('The analysis service returned an error (502).'), 'The service did not answer')
  assert.equal(readerError('/api/options/AAPL returned 429'), 'The provider is throttling requests')
  assert.equal(readerError('403 Forbidden'), 'This deployment does not include this data')
})

test('structured or URL-bearing messages are replaced, short plain ones kept', () => {
  assert.equal(readerError('{"detail":"boom"}'), 'The service did not answer')
  assert.equal(readerError('Not enough history for this ticker.'), 'Not enough history for this ticker')
  assert.doesNotMatch(readerError('error at https://api.vendor.io/v3/x?apikey=abc'), /https?:|apikey/)
  assert.equal(readerError(null), 'The service did not answer')
})

test('a described failure keeps the detail out of the headline', () => {
  const f = describeFailure(new ResourceError('/api/options/AAPL', 429, 'upstream 429 for https://x.io/q'), 'options data')
  assert.equal(f.title, 'Options data rate limited')
  assert.doesNotMatch(f.title + f.detail, /429|https/)
  assert.ok(f.technical && !/https?:/.test(f.technical))
})
