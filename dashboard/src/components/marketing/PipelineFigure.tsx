/**
 * How a research run is put together, as a diagram: providers answer, their
 * readings are reconciled into evidence, the deterministic engine sets the
 * signal, and the explanation layer narrates it with citations that point
 * back into the evidence. A concept drawing — it carries no figures.
 */
const PROVIDERS = [58, 104, 150, 196, 242]
const EVIDENCE = [
  { y: 50, state: 'pos' },
  { y: 86, state: 'pos' },
  { y: 122, state: 'info' },
  { y: 158, state: 'pos' },
  { y: 194, state: 'missing' },
  { y: 230, state: 'pos' },
] as const
const BARS = [
  { y: 112, w: 46 }, { y: 130, w: 18 }, { y: 148, w: 34 }, { y: 166, w: -14 }, { y: 184, w: -8 },
]

export default function PipelineFigure() {
  return (
    <figure className="lp-pipe">
      <svg viewBox="0 0 960 290" role="img" aria-labelledby="pipe-title pipe-desc" className="lp-pipe__svg">
        <title id="pipe-title">How a research run is assembled</title>
        <desc id="pipe-desc">
          Providers feed evidence items; the evidence feeds the deterministic engine, which sets the
          signal; the explanation layer writes a narrative whose citations point back to the evidence.
        </desc>

        {/* providers → evidence */}
        {PROVIDERS.map((py, i) => EVIDENCE.filter((_, j) => j % 5 === i % 5 || j === i).map((e) => (
          <path
            key={`${py}-${e.y}`}
            className={e.state === 'missing' ? 'lp-pipe__flow lp-pipe__flow--gap' : 'lp-pipe__flow'}
            d={`M150,${py} C220,${py} 230,${e.y + 11} 300,${e.y + 11}`}
          />
        )))}
        {PROVIDERS.map((y) => (
          <g key={y} transform={`translate(110 ${y - 16})`}>
            <rect className="lp-pipe__node" width="32" height="32" rx="7" />
            <circle className="lp-pipe__dot" cx="16" cy="16" r="4.5" />
          </g>
        ))}

        {/* evidence items */}
        {EVIDENCE.map((e) => (
          <g key={e.y} transform={`translate(300 ${e.y})`}>
            <rect className={e.state === 'missing' ? 'lp-pipe__item lp-pipe__item--gap' : 'lp-pipe__item'} width="132" height="22" rx="5" />
            <circle className={`lp-pipe__state lp-pipe__state--${e.state}`} cx="13" cy="11" r="3.5" />
            <rect className="lp-pipe__line" x="24" y="9" width={e.state === 'missing' ? 52 : 78} height="4" rx="2" />
          </g>
        ))}

        {/* evidence → engine */}
        {EVIDENCE.filter((e) => e.state !== 'missing').map((e) => (
          <path key={`x${e.y}`} className="lp-pipe__flow" d={`M432,${e.y + 11} C480,${e.y + 11} 480,150 522,150`} />
        ))}

        {/* engine */}
        <g transform="translate(522 88)">
          <rect className="lp-pipe__engine" width="166" height="124" rx="10" />
          <line className="lp-pipe__axis" x1="83" y1="18" x2="83" y2="110" />
          {BARS.map((b) => (
            <rect
              key={b.y}
              className={b.w >= 0 ? 'lp-pipe__bar lp-pipe__bar--pos' : 'lp-pipe__bar lp-pipe__bar--neg'}
              x={b.w >= 0 ? 83 : 83 + b.w}
              y={b.y - 88 + 12}
              width={Math.abs(b.w)}
              height="8"
              rx="2"
            />
          ))}
        </g>

        {/* engine → synthesis: the signal is fixed before anything is written */}
        <path className="lp-pipe__signal" d="M688,150 L770,150" markerEnd="url(#pipe-arrow)" />
        <defs>
          <marker id="pipe-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" className="lp-pipe__arrow" />
          </marker>
        </defs>

        {/* synthesis document with citations back into the evidence */}
        <g transform="translate(778 70)">
          <path className="lp-pipe__doc" d="M0,6 a6,6 0 0 1 6,-6 h82 l26,26 v128 a6,6 0 0 1 -6,6 h-102 a6,6 0 0 1 -6,-6 z" />
          <path className="lp-pipe__fold" d="M88,0 v20 a6,6 0 0 0 6,6 h20" />
          {[44, 60, 76, 100, 116, 132].map((y, i) => (
            <rect key={y} className="lp-pipe__line" x="14" y={y} width={[74, 62, 70, 66, 50, 58][i]} height="4" rx="2" />
          ))}
          <circle className="lp-pipe__cite" cx="96" cy="46" r="5" />
          <circle className="lp-pipe__cite" cx="84" cy="118" r="5" />
        </g>
        <path className="lp-pipe__back" d="M874,116 C860,20 520,10 432,61" />
        <path className="lp-pipe__back" d="M862,188 C830,272 520,282 432,241" />
      </svg>
      <ol className="lp-pipe__steps">
        <li><b>Providers answer</b><span>or say that they did not. A missing input stays missing.</span></li>
        <li><b>Evidence is reconciled</b><span>readings are compared across vendors, never averaged into one.</span></li>
        <li><b>The engine sets the signal</b><span>deterministic factor math, a macro gate on momentum, itemised confidence.</span></li>
        <li><b>The narrative cites</b><span>and is validated against the evidence. Failing sections are withheld.</span></li>
      </ol>
    </figure>
  )
}
