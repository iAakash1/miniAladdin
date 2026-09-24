/**
 * The two ways a request meets the vendors, side by side.
 *
 * A single value — a quote for the header — walks a fallback chain and stops
 * at the first vendor that answers. Research evidence fans out to every
 * capable vendor within the capability's budget, and the answers are
 * normalised and reconciled rather than one being picked. A concept drawing:
 * vendors are lettered, not named, and nothing here is a live reading.
 */
export default function RoutingFigure() {
  return (
    <figure className="rt" aria-label="Fallback chain compared with evidence fan-out">
      <div className="rt-panel">
        <p className="rt-k">One value · fallback chain</p>
        <svg viewBox="0 0 300 120" className="rt-svg" role="img" aria-label="A request tries vendor A, which fails, then vendor B, which answers; vendor C is never called">
          <rect className="rt-req" x="6" y="44" width="58" height="32" rx="6" />
          <text className="rt-t" x="35" y="64" textAnchor="middle">request</text>
          <path className="rt-line" d="M64 60 H96" />
          <rect className="rt-v rt-v--fail" x="96" y="44" width="44" height="32" rx="6" />
          <text className="rt-t" x="118" y="64" textAnchor="middle">A</text>
          <text className="rt-x" x="118" y="36" textAnchor="middle">×</text>
          <path className="rt-line" d="M140 60 H172" />
          <rect className="rt-v rt-v--ok" x="172" y="44" width="44" height="32" rx="6" />
          <text className="rt-t" x="194" y="64" textAnchor="middle">B</text>
          <path className="rt-line rt-line--dim" d="M216 60 H248" />
          <rect className="rt-v rt-v--idle" x="248" y="44" width="44" height="32" rx="6" />
          <text className="rt-t rt-t--dim" x="270" y="64" textAnchor="middle">C</text>
          <path className="rt-ans" d="M194 76 V102 H35 V76" />
          <text className="rt-t rt-t--ans" x="114" y="114" textAnchor="middle">first answer returned · C never called</text>
        </svg>
        <p className="rt-note">Used where one current figure is needed quickly — a header quote, a sparkline.</p>
      </div>
      <div className="rt-panel">
        <p className="rt-k">Research evidence · fan-out and reconcile</p>
        <svg viewBox="0 0 300 120" className="rt-svg" role="img" aria-label="A request goes to vendors A to E in parallel; their answers are normalised and reconciled into one evidence record with agreement and conflicts kept">
          <rect className="rt-req" x="6" y="44" width="58" height="32" rx="6" />
          <text className="rt-t" x="35" y="64" textAnchor="middle">request</text>
          {[14, 36, 58, 80, 102].map((y, i) => (
            <g key={y}>
              <path className={i === 3 ? 'rt-line rt-line--dim' : 'rt-line'} d={`M64 60 C80 60 84 ${y} 104 ${y}`} />
              <rect className={i === 3 ? 'rt-v rt-v--fail' : 'rt-v rt-v--ok'} x="104" y={y - 9} width="30" height="18" rx="4" />
              <text className="rt-t rt-t--sm" x="119" y={y + 3.5} textAnchor="middle">{'ABCDE'[i]}</text>
              {i !== 3 ? <path className="rt-line" d={`M134 ${y} C156 ${y} 158 60 178 60`} /> : null}
            </g>
          ))}
          <rect className="rt-rec" x="178" y="40" width="114" height="40" rx="7" />
          <text className="rt-t rt-t--sm" x="235" y="56" textAnchor="middle">normalise · reconcile</text>
          <text className="rt-t rt-t--xs rt-t--dim" x="235" y="70" textAnchor="middle">agree · single · conflict</text>
        </svg>
        <p className="rt-note">Used for the evidence behind a signal. Disagreement is kept side by side; a vendor that fails is named.</p>
      </div>
    </figure>
  )
}
