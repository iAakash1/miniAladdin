/* A negative figure is printed with U+2212 MINUS SIGN, not the hyphen-minus.

   Set in Inter with tabular numerals, the hyphen keeps its short glyph inside
   a digit-wide cell, so "-3.4%" read as "- 3.4%" in every column of returns.
   The minus sign is drawn to the width of the plus and sits against its
   number. These tests hold three things: every central formatter emits it,
   nothing that is not a sign is touched, and no code computes with the text. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import {
  MINUS, fmtNum, fmtPct, fmtPctRaw, fmtPrice, fmtSigned, parsePercentString, typographicMinus,
  uncertaintyBreakdown,
} from '../src/lib/format'
import { format } from '../src/lib/quantity'

const SRC = join(__dirname, '..', 'src')

test('the minus sign is U+2212', () => {
  assert.equal(MINUS, '\u2212')
  assert.equal(MINUS.codePointAt(0), 0x2212)
})

test('a leading sign and an exponent sign become the minus sign', () => {
  assert.equal(typographicMinus('-3.4'), '−3.4')
  assert.equal(typographicMinus('-$12.50'), '−$12.50')
  assert.equal(typographicMinus('-.5'), '−.5')
  assert.equal(typographicMinus('1.2e-5'), '1.2e−5')
  assert.equal(typographicMinus('-1.2e-5'), '−1.2e−5')
})

test('a hyphen that is not a sign is left alone', () => {
  for (const text of ['BRK-B', '2026-11-04', '12-1', 'post-earnings', 'scoring-v2.1', '—', '', 'Coca-Cola', 'EXP-014']) {
    assert.equal(typographicMinus(text), text)
  }
})

test('every central formatter prints a loss with the minus sign and no hyphen', () => {
  const outputs = [
    fmtNum(-1.5), fmtNum(-0.004, 3), fmtPct(-0.034, 1), fmtPct(-0.034, 1, false), fmtPctRaw(-4.47),
    fmtPctRaw(-4.47, 2, true), fmtPrice(-12.5), fmtPrice(-1234.5), fmtSigned(-0.1234, 3),
    format(-0.05, 'percent', { digits: 2 }).text, format(-2_400_000_000, 'currency').text,
    format(-1234.5, 'currency').text, format(-3, 'count').text, format(-1.25, 'ratio').text,
    format(-0.0004, 'eigenvalue').text, format(-1.96, 'zscore').text,
  ]
  for (const text of outputs) {
    assert.ok(text.startsWith(MINUS), `${text} does not start with the minus sign`)
    assert.ok(!text.includes('-'), `${text} still carries a hyphen-minus`)
  }
  assert.equal(fmtPct(-0.034, 1), '−3.4%')
  assert.equal(fmtPrice(-1234.5), '−$1,234.50')
  assert.equal(format(-2_400_000_000, 'currency').text, '−2.40B')
  assert.equal(format(-0.0004, 'eigenvalue').text, '−4.00e−4')
})

test('a gain keeps its plus, and zero or a value that rounds to zero has no sign', () => {
  assert.equal(fmtPct(0.034, 1), '+3.4%')
  assert.equal(fmtSigned(0.5, 1), '+0.5')
  assert.equal(fmtPct(-0.00001), '0.00%')
  assert.equal(fmtNum(-0.0001, 2), '0.00')
  assert.equal(fmtSigned(-0.0001, 2), '0.00')
  assert.equal(fmtPrice(-0.001), '$0.00')
  assert.equal(format(-0.00001, 'percent', { digits: 2 }).text, '0.00')
  assert.equal(fmtNum(0), '0.00')
})

test('positive figures, grouping and precision are unchanged', () => {
  assert.equal(fmtPrice(1019.26), '$1,019.26')
  assert.equal(format(1019.26, 'currency').text, '1,019.26')
  assert.equal(format(4_789_955_589_281, 'currency').text, '4.79T')
  assert.equal(format(3.5, 'count', { digits: 4 }).text, '3.5')
  assert.equal(fmtPctRaw(4.47), '4.47%')
})

test('uncertainty components carry the minus sign too', () => {
  assert.equal(uncertaintyBreakdown({ dispersion: -0.12, data: 0.05 }), 'disp −0.12 · data 0.05')
})

test('API strings are still parsed with an ASCII sign; display text is never parsed', () => {
  assert.equal(parsePercentString('-0.35%'), -0.35)
  // A display string is presentation: parsing one back is how a typographic
  // minus would silently become NaN. The one place that did it now reads the number.
  const view = readFileSync(join(SRC, 'components', 'terminal', 'PortfolioView.tsx'), 'utf8')
  assert.doesNotMatch(view, /parseFloat\(text\)/)
  assert.ok(Number.isNaN(Number(fmtPct(-0.034, 1).replace('%', ''))), 'display text is not a number')
})

test('in composed text, only a hyphen that begins a number becomes the minus sign', async () => {
  const { typographicMinusInText } = await import('../src/lib/format')
  assert.equal(typographicMinusInText('hist -3.193'), 'hist −3.193')
  assert.equal(typographicMinusInText('S&P 500 -2.01% over the window'), 'S&P 500 −2.01% over the window')
  assert.equal(typographicMinusInText('-0.5 to (-1.2)'), '−0.5 to (−1.2)')
  assert.equal(typographicMinusInText('z=-1.9, t: -2.4'), 'z=−1.9, t: −2.4')
  for (const text of ['BRK-B fell', 'as of 2026-11-04', 'the 12-1 window', 'post-earnings drift', 'scoring-v2.1', 'EXP-014', '+DI 13 / −DI 22']) {
    assert.equal(typographicMinusInText(text), text)
  }
})
