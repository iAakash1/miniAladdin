/* A sign states a direction, and zero has none.

   `format()` already withholds the plus on a zero and on anything that rounds
   to zero. Forty-five call sites rebuilt the rule by hand as
   `${v >= 0 ? '+' : ''}${v.toFixed(n)}`, which prints "+0.000" for a flat
   factor, "-0.00" for -0.0001, and the literal "NaN" or "Infinity" when the
   figure is undefined, seven of them behind their own local helper. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

import { fmtSigned } from '../src/lib/format'

test('a gain has a plus, a loss has a minus, zero has neither', () => {
  assert.equal(fmtSigned(0.1234, 3), '+0.123')
  assert.equal(fmtSigned(-0.1234, 3), '-0.123')
  assert.equal(fmtSigned(0, 3), '0.000')
  assert.equal(fmtSigned(-0, 3), '0.000')
})

test('the sign is decided after rounding', () => {
  assert.equal(fmtSigned(0.0004, 2), '0.00', 'a value that rounds to zero is not a gain')
  assert.equal(fmtSigned(-0.0004, 2), '0.00', 'and is not a loss')
  assert.equal(fmtSigned(0.005, 2), '+0.01')
})

test('a figure that is not a number is no value, not "NaN"', () => {
  for (const v of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    assert.equal(fmtSigned(v as number | null | undefined, 2), '—')
  }
})

test('whole-number deltas carry no decimals', () => {
  assert.equal(fmtSigned(3, 0), '+3')
  assert.equal(fmtSigned(-12, 0), '-12')
  assert.equal(fmtSigned(0, 0), '0')
})

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

test('no component rebuilds the sign rule by hand', () => {
  const SRC = join(__dirname, '..', 'src')
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).split(sep).join('/')
    if (rel === 'lib/format.ts') continue
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(/>=? 0 \? '\+' : ''/g)) offenders.push(`${rel}: ${m[0]}`)
  }
  assert.deepEqual(offenders, [])
})
