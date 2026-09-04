/**
 * The column beside home.
 *
 * It used to be three paragraphs telling a first-time reader where to type,
 * where prices come from, and that watchlists are local. Read once, then
 * furniture — and furniture that costs a fifth of the screen every morning
 * for the rest of the product's life.
 *
 * What survives a hundredth visit is the keyboard. This terminal is meant to
 * be driven without the mouse, and a compact key map is the one piece of
 * reference that is as useful on the hundredth morning as the first. The
 * second block says where each thing on this page actually lives, which is
 * the same question the old prose answered in a paragraph, in a line.
 *
 * Nothing here is a claim about data. Provenance travels with the figures.
 */

import { Panel } from '@/components/system'

const KEYS: [string, string][] = [
  ['/', 'search securities'],
  ['⌘K', 'commands'],
  ['↑ ↓', 'move through results'],
  ['↵', 'open'],
  ['esc', 'close'],
]

const LIVES: [string, string][] = [
  ['Quotes', 'market providers'],
  ['Market', 'snapshot, server'],
  ['Watchlist', 'this browser'],
  ['Recent', 'this browser'],
]

export default function HomeContext() {
  return (
    <>
      <Panel title="Keys">
        <ul className="objidx">
          {KEYS.map(([k, what]) => (
            <li className="objidx__row" key={k}>
              <span className="objidx__k">{what}</span>
              <kbd className="sys-kbd">{k}</kbd>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Where this lives">
        <ul className="objidx">
          {LIVES.map(([k, where]) => (
            <li className="objidx__row" key={k}>
              <span className="objidx__k">{k}</span>
              <span className="objidx__v">{where}</span>
            </li>
          ))}
        </ul>
        <p className="objidx__foot">
          Anything kept in this browser does not follow you to another machine,
          and clearing site data clears it.
        </p>
      </Panel>
    </>
  )
}
