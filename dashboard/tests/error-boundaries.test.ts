/* A view that throws must be contained, described and recoverable.

   The app had no error boundary at all. A render-time exception — a provider
   field reaching a formatter as null is enough — would replace the page with
   the framework's blank "Application error" screen: no product name, no cause,
   no way back. These are source-level checks, because the rendered behaviour
   (what the framework does with a thrown error) belongs to the framework.
   What is ours, and pinned here, is that every route tree has a boundary,
   that it is a client component, and that it offers a retry. */

import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const APP = join(__dirname, '..', 'src', 'app')
const read = (path: string) => readFileSync(path, 'utf8')

/** Route trees that mount their own layout: each needs its own boundary. */
const TREES = readdirSync(APP, { withFileTypes: true })
  .filter((d) => d.isDirectory() && existsSync(join(APP, d.name, 'layout.tsx')) && !d.name.startsWith('('))
  .map((d) => d.name)

test('the root and every route tree with its own layout has an error boundary', () => {
  assert.ok(existsSync(join(APP, 'error.tsx')), 'no root error boundary')
  assert.ok(TREES.length >= 5, `expected several route trees, found ${TREES.join(', ')}`)
  for (const tree of TREES) {
    assert.ok(existsSync(join(APP, tree, 'error.tsx')), `/${tree} has a layout but no error.tsx`)
  }
})

test('every boundary is a client component that renders the shared RouteError with reset', () => {
  for (const file of ['error.tsx', ...TREES.map((t) => join(t, 'error.tsx'))]) {
    const src = read(join(APP, file))
    assert.match(src.trimStart(), /^'use client'/, `${file} must be a client component`)
    assert.match(src, /RouteError/, `${file} does not use the shared RouteError`)
    assert.match(src, /reset/, `${file} drops the retry`)
  }
})

test('the shared boundary offers retry and a way out, and shows no raw error text', () => {
  const src = read(join(__dirname, '..', 'src', 'components', 'system', 'RouteError.tsx'))
  assert.match(src, /onClick=\{\(\) => reset\(\)\}/, 'no retry action')
  assert.match(src, /href="\/"/, 'no way home')
  assert.match(src, /role="alert"/, 'the failure is not announced')
  assert.match(src, /error\.digest/, 'no reference a reader can quote')
  // The message and stack can carry provider payloads and internal paths; the
  // reader gets the opaque digest only.
  assert.doesNotMatch(src, /error\.message|error\.stack/, 'raw error text is rendered')
})

test('the failure copy does not claim a cause it does not know', () => {
  const src = read(join(__dirname, '..', 'src', 'components', 'system', 'RouteError.tsx'))
  assert.doesNotMatch(src, /Something went wrong/i)
  assert.match(src, /no figures are shown in its place/i)
})
