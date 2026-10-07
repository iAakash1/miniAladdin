import { Shortcut } from '@/components/system/Shortcut'
import { Panel } from '@/components/system'

const LIVES: [string, string][] = [
  ['Index and sector tape', 'market data providers, cached server-side'],
  ['Watchlists', 'your account — synced across devices'],
  ['Recent research', 'your account’s research log'],
  ['Ranked universe', 'a cached cross-sectional snapshot'],
  ['Market news', 'public financial feeds'],
]

export default function HomeContext() {
  return (
    <>
      <Panel title="Where each section comes from">
        <ul className="objidx">
          {LIVES.map(([k, where]) => (
            <li className="objidx__row" key={k}>
              <span className="objidx__k">{k}</span>
              <span className="objidx__v">{where}</span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Keys">
        <ul className="objidx">
          {[
            [<><Shortcut k="K" /> or /</>, 'search companies and commands'],
            ['g c', 'reopen the last company'],
            ['?', 'every shortcut'],
          ].map(([keys, what]) => (
            <li className="objidx__row" key={String(what)}>
              <span className="objidx__k">{what}</span>
              <kbd className="sys-kbd">{keys}</kbd>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  )
}
