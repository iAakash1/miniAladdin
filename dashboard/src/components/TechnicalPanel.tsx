'use client'

interface Headline {
  title: string
  score: number
  label: string
  source: string
  url: string
  published_at: string
}

interface Props {
  rsi: number; sharpe: number; sortino: number
  volatility: number; momentum: number; drawdown: number
  sentiment: number; sentimentLabel: string
  headlineCount?: number; headlines?: Headline[]
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span style={{ fontFamily:'var(--font-mono)', fontSize:'.82rem', fontWeight:500, color: color ?? 'var(--text)' }}>{value}</span>
    </div>
  )
}

const cRsi  = (v: number) => v > 70 ? 'var(--red)' : v < 30 ? 'var(--green)' : 'var(--text)'
const cRat  = (v: number) => v > 1  ? 'var(--green)' : v < 0 ? 'var(--red)' : 'var(--amber)'
const cMom  = (v: number) => v > 0  ? 'var(--green)' : 'var(--red)'
const cVol  = (v: number) => v > 0.45 ? 'var(--red)' : v > 0.25 ? 'var(--amber)' : 'var(--green)'
const cSent = (v: number) => v > 0.1  ? 'var(--green)' : v < -0.1 ? 'var(--red)' : 'var(--amber)'

function timeAgo(iso: string): string {
  if (!iso) return ''
  try {
    const diff = Date.now() - new Date(iso).getTime()
    const h = Math.floor(diff / 3600000)
    const d = Math.floor(h / 24)
    if (d > 0) return d + 'd ago'
    if (h > 0) return h + 'h ago'
    return 'just now'
  } catch { return '' }
}

function LabelBadge({ label }: { label: string }) {
  const color = label === 'Bullish' ? 'var(--green)' : label === 'Bearish' ? 'var(--red)' : 'var(--amber)'
  const bg    = label === 'Bullish' ? 'var(--green-dim)' : label === 'Bearish' ? 'var(--red-dim)' : 'var(--amber-dim)'
  const bd    = label === 'Bullish' ? 'var(--green-border)' : label === 'Bearish' ? 'var(--red-border)' : 'var(--amber-border)'
  return (
    <span style={{ fontFamily:'var(--font-mono)', fontSize:'.58rem', letterSpacing:'.06em', color, background:bg, border:'1px solid ' + bd, borderRadius:3, padding:'1px 6px' }}>
      {label.toUpperCase()}
    </span>
  )
}

export default function TechnicalPanel({ rsi, sharpe, sortino, volatility, momentum, drawdown, sentiment, sentimentLabel, headlineCount, headlines = [] }: Props) {
  const s = sentiment ?? 0

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>

      <div className="card" style={{ padding:'20px 22px' }}>
        <div className="section-heading"><span>Technical Analysis</span></div>
        <Row label="RSI (14)"              value={(rsi??0).toFixed(1)}                    color={cRsi(rsi??0)} />
        <Row label="Sharpe Ratio"          value={(sharpe??0).toFixed(3)}                 color={cRat(sharpe??0)} />
        <Row label="Sortino Ratio"         value={(sortino??0).toFixed(3)}                color={cRat(sortino??0)} />
        <Row label="21D Momentum"          value={((momentum??0)*100).toFixed(2) + '%'}   color={cMom(momentum??0)} />
        <Row label="Annualized Volatility" value={((volatility??0)*100).toFixed(1) + '%'} color={cVol(volatility??0)} />
        <Row label="Max Drawdown"          value={((drawdown??0)*100).toFixed(2) + '%'}   color="var(--red)" />
      </div>

      <div className="card" style={{ padding:'20px 22px' }}>
        <div className="section-heading">
          <span>News Sentiment{headlineCount != null && <span style={{ marginLeft:8, fontFamily:'var(--font-mono)', fontSize:'.6rem', fontWeight:400, color:'var(--muted)', textTransform:'none' }}>{headlineCount} articles</span>}</span>
        </div>
        <div style={{ display:'flex', alignItems:'flex-end', gap:12, marginBottom:14 }}>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:'1.9rem', fontWeight:700, color:cSent(s), lineHeight:1, letterSpacing:'-.02em' }}>
            {s > 0 ? '+' : ''}{s.toFixed(3)}
          </span>
          <span style={{ fontFamily:'var(--font-mono)', fontSize:'.7rem', color:cSent(s), background:s>0.1?'var(--green-dim)':s<-0.1?'var(--red-dim)':'var(--amber-dim)', border:'1px solid ' + (s>0.1?'var(--green-border)':s<-0.1?'var(--red-border)':'var(--amber-border)'), borderRadius:4, padding:'2px 8px', marginBottom:3, letterSpacing:'.06em' }}>
            {(sentimentLabel ?? 'Neutral').toUpperCase()}
          </span>
        </div>
        <div style={{ position:'relative', height:5, background:'rgba(255,255,255,0.06)', borderRadius:3, marginBottom:6 }}>
          <div style={{ position:'absolute', left:'50%', top:0, bottom:0, width:1, background:'rgba(255,255,255,0.18)' }} />
          <div style={{ position:'absolute', top:0, bottom:0, left:s>=0?'50%':(50+s*50)+'%', width:Math.abs(s)*50+'%', background:cSent(s), borderRadius:3 }} />
        </div>
        <div style={{ display:'flex', justifyContent:'space-between' }}>
          <span className="label" style={{ fontSize:'.55rem' }}>-1 Bearish</span>
          <span className="label" style={{ fontSize:'.55rem' }}>+1 Bullish</span>
        </div>
      </div>

      {headlines.length > 0 && (
        <div className="card" style={{ padding:'20px 22px' }}>
          <div className="section-heading"><span>Latest News</span></div>
          <div style={{ display:'flex', flexDirection:'column' }}>
            {headlines.map((h, i) => (
              <div key={i} style={{ padding:'12px 0', borderBottom: i < headlines.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                <div style={{ display:'flex', alignItems:'flex-start', gap:8, marginBottom:6 }}>
                  <span style={{ display:'inline-block', width:6, height:6, borderRadius:'50%', background: h.label==='Bullish'?'var(--green)':h.label==='Bearish'?'var(--red)':'var(--amber)', flexShrink:0, marginTop:5 }} />
                  <a href={h.url || '#'} target="_blank" rel="noopener noreferrer"
                    style={{ fontFamily:'var(--font-mono)', fontSize:'.78rem', color:'var(--text)', textDecoration:'none', lineHeight:1.5, flex:1 }}>
                    {h.title}
                  </a>
                  {h.url && <span style={{ color:'var(--accent)', fontSize:'.75rem', flexShrink:0, marginTop:2 }}>↗</span>}
                </div>
                <div style={{ display:'flex', alignItems:'center', gap:8, paddingLeft:14, flexWrap:'wrap' }}>
                  <LabelBadge label={h.label} />
                  <span className="label" style={{ fontSize:'.6rem' }}>{h.source}</span>
                  {h.published_at && <span className="label" style={{ fontSize:'.6rem' }}>{timeAgo(h.published_at)}</span>}
                  {h.score !== 0 && <span style={{ fontFamily:'var(--font-mono)', fontSize:'.6rem', color:h.score>0?'var(--green)':h.score<0?'var(--red)':'var(--muted)' }}>{h.score>0?'+':''}{h.score.toFixed(2)}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
