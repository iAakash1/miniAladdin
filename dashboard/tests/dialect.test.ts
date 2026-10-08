/* One English.

   The interface formats every number and date for en-US and covers US-listed companies, but its prose
   had drifted between dialects: the beginner page's button said "Analyse" while its sibling intermediate
   page said "Analyze", and one screen said "Data catalogue" beside another that said "Normalization".
   This reads the strings a reader sees (string literals and JSX text, never comments or identifiers) and
   fails on a British spelling.

   Not flagged on purpose: "analyses" (the plural noun, correct in both), "optimism", "realistic", and the
   two values below that are matched against data rather than shown as prose. */

import assert from 'node:assert/strict'
import test from 'node:test'

import { visibleStrings } from './visible-strings'

const BRITISH = new RegExp(
  '\\b(' + [
    'colour\\w*', 'behaviour\\w*', 'authoris\\w*', 'organis\\w*', 'summaris\\w*', 'recognis\\w*',
    'analyse', 'analysed', 'analysing', 'centre\\w*', 'centred', 'favour\\w*', 'licence', 'catalogue\\w*', 'grey',
    'normalis\\w*', 'visualis\\w*', 'initialis\\w*', 'standardis\\w*', 'optimiser\\w*', 'prioritis\\w*',
    'categoris\\w*', 'customis\\w*', 'minimis\\w*', 'maximis\\w*', 'utilis\\w*', 'neighbour\\w*', 'programme\\w*',
    'artefact\\w*', '(?:un)?labelled', 'modelling', 'travelled', 'signalling', 'ageing', 'judgement', 'whilst', 'amongst',
    'realised', 'realises', 'realising',
  ].join('|') + ')\\b', 'i',
)

/** Strings that are values the code compares against, not words a reader reads. */
const VALUES = new Set(['standardised', 'cancelled'])

test('no British spelling appears in text a reader sees', () => {
  const offenders = visibleStrings()
    .filter(({ text }) => !(VALUES.has(text.trim().toLowerCase()) && !/\s/.test(text.trim())))
    .flatMap(({ file, line, text }) => {
      const hit = BRITISH.exec(text)
      return hit ? [`${file}:${line} "${hit[0]}"`] : []
    })
  assert.deepEqual(offenders, [])
})
