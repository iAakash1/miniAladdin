'use client'
import { useState, useCallback, useEffect } from 'react'
import { useUser, UserButton } from '@clerk/nextjs'
import PriceChart     from '@/components/PriceChart'
import MacroPanel     from '@/components/MacroPanel'
import VerdictBadge   from '@/components/VerdictBadge'
import TechnicalPanel from '@/components/TechnicalPanel'
import UpgradeModal   from '@/components/UpgradeModal'
import type { MacroData } from '@/types/api'

const QUICK      = ['NVDA','AAPL','TSLA','MSFT','META','AMZN','GOOGL','SPY']
const SCORE: Record<string,number> = {'Strong Buy':6,'Buy':3,'Hold':0,'Sell':-3,'Strong Sell':-6}
const FREE_LIMIT = 5

function normMacro(m: any): MacroData {
  const p = (v: any) => { const n = parseFloat(String(v??'0').replace('%','').replace('N/A','0')); return isNaN(n)?0:n }
  return { srm:m?.risk_multiplier??1, yield_spread:m?.yield_spread??0, cpi:p(m?.inflation_rate), fed_funds_rate:p(m?.fed_funds_rate) }
}

function norm(raw: any, chart: any) {
  const t=raw.technicals??{}, s=raw.sentiment??{}, v=t.raw_signal??'Hold'
  return {
    ticker:raw.ticker??'—', verdict:v, risk_adjusted_signal:t.risk_adjusted_signal??v,
    signal_score:SCORE[t.risk_adjusted_signal??v]??0, srm:raw.macro?.risk_multiplier??1,
    current_price:t.current_price??0, rsi:t.rsi_14??0, sharpe_ratio:t.sharpe_ratio??0,
    sortino_ratio:t.sortino_ratio??0, volatility:t.volatility??0, momentum:t.return_21d??0,
    max_drawdown:t.max_drawdown??0, sentiment_score:s.average_score??0,
    sentiment_label:s.dominant_label??'Neutral', sentiment_headline_count:s.headline_count??0,
    headlines:s.headlines??[],
    price_history:(chart?.prices??[]).map((p:any)=>({date:p.date,close:p.close})),
    macro:normMacro(raw.macro),
  }
}

function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
      <polygon points="11,1 21,6 21,16 11,21 1,16 1,6" stroke="#38bdf8" strokeWidth="1.2" fill="rgba(56,189,248,0.1)"/>
      <circle cx="11" cy="11" r="3.2" fill="#38bdf8" fillOpacity="0.9"/>
      <line x1="11" y1="5" x2="11" y2="8.2" stroke="#38bdf8" strokeWidth="1"/>
      <line x1="11" y1="13.8" x2="11" y2="17" stroke="#38bdf8" strokeWidth="1"/>
    </svg>
  )
}

function Skel({h}:{h:number}){return <div className="shimmer" style={{height:h,borderRadius:8}}/>}

function HStat({label,value,color}:{label:string,value:string,color?:string}){
  return(
    <div style={{display:'flex',alignItems:'center',gap:5,padding:'0 10px',borderLeft:'1px solid rgba(255,255,255,0.06)'}}>
      <span className="label">{label}</span>
      <span style={{fontFamily:'var(--font-mono)',fontSize:'.72rem',fontWeight:600,color:color??'var(--text)'}}>{value}</span>
    </div>
  )
}

export default function Home() {
  const { user, isLoaded } = useUser()
  const isPro = (user?.publicMetadata?.isPro as boolean) ?? false

  const [ticker,   setTicker  ] = useState('')
  const [loading,  setLoading ] = useState(false)
  const [result,   setResult  ] = useState<ReturnType<typeof norm>|null>(null)
  const [error,    setError   ] = useState<string|null>(null)
  const [macro,    setMacro   ] = useState<MacroData|null>(null)
  const [fast,     setFast    ] = useState(false)
  const [period,   setPeriod  ] = useState('3mo')
  const [showUpgrade, setShowUpgrade] = useState(false)
  const [upgradeReason, setUpgradeReason] = useState<string|undefined>()
  const [analysisCount, setAnalysisCount] = useState(0)
  const [macroLoaded, setMacroLoaded] = useState(false)

  /* Load daily analysis count */
  useEffect(() => {
    const today = new Date().toDateString()
    const stored = localStorage.getItem('omni_date')
    const count  = parseInt(localStorage.getItem('omni_count') ?? '0')
    if (stored !== today) {
      localStorage.setItem('omni_date', today)
      localStorage.setItem('omni_count', '0')
      setAnalysisCount(0)
    } else {
      setAnalysisCount(count)
    }
  }, [])

  /* Load macro */
  if (!macroLoaded) {
    setMacroLoaded(true)
    fetch('/api/macro').then(r=>r.ok?r.json():null).then(d=>{if(d)setMacro(normMacro({...d,...(d.stats??{})}))}).catch(()=>null)
  }

  const bumpCount = () => {
    const next = analysisCount + 1
    setAnalysisCount(next)
    localStorage.setItem('omni_count', String(next))
  }

  const run = useCallback(async (sym: string) => {
    const t = sym.trim().toUpperCase()
    if (!t) return

    /* Free limit gate */
    if (!isPro && analysisCount >= FREE_LIMIT) {
      setUpgradeReason('limit')
      setShowUpgrade(true)
      return
    }

    setLoading(true); setError(null); setResult(null)
    try {
      const [r1,r2] = await Promise.all([
        fetch('/api/research/' + t + (fast?'?fast=true':'')),
        fetch('/api/chart/' + t + '?period=' + period),
      ])
      if (!r1.ok) { const b=await r1.json().catch(()=>({})); throw new Error(b?.detail||'Error '+r1.status) }
      const [raw,chart] = await Promise.all([r1.json(), r2.json().catch(()=>({}))])
      setResult(norm(raw,chart))
      if (!isPro) bumpCount()
    } catch(e) {
      setError(e instanceof Error?e.message:'Failed')
    } finally {
      setLoading(false)
    }
  }, [fast, period, isPro, analysisCount])

  const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); run(ticker) }

  const handlePeriod = (p: string) => {
    if (!isPro && p !== '3mo') { setUpgradeReason('feature'); setShowUpgrade(true); return }
    setPeriod(p)
    if (result) run(result.ticker)
  }

  if (!isLoaded) return (
    <div style={{minHeight:'100vh',background:'#060d1b',display:'flex',alignItems:'center',justifyContent:'center'}}>
      <div style={{fontFamily:'JetBrains Mono, monospace',fontSize:'.75rem',color:'#4b6480',letterSpacing:'.1em'}}>LOADING…</div>
    </div>
  )

  return (
    <div style={{position:'relative',zIndex:1,minHeight:'100vh',display:'flex',flexDirection:'column'}}>

      {showUpgrade && <UpgradeModal onClose={()=>setShowUpgrade(false)} reason={upgradeReason}/>}

      {/* HEADER */}
      <header style={{position:'sticky',top:0,zIndex:50,backdropFilter:'blur(14px)',WebkitBackdropFilter:'blur(14px)',background:'rgba(6,13,27,0.82)',borderBottom:'1px solid rgba(56,189,248,0.08)',height:50,display:'flex',alignItems:'center',padding:'0 20px',gap:10,overflow:'hidden'}}>
        <div style={{display:'flex',alignItems:'center',gap:8,flexShrink:0}}>
          <Logo/>
          <span style={{fontFamily:'var(--font-display)',fontWeight:800,fontSize:'.88rem',letterSpacing:'.1em',color:'var(--text)',textTransform:'uppercase'}}>OmniSignal</span>
          <span style={{fontSize:'.52rem',color:'var(--accent)',border:'1px solid rgba(56,189,248,0.3)',borderRadius:3,padding:'1px 5px',fontFamily:'var(--font-mono)'}}>v1.0</span>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:2,marginLeft:'auto'}}>
          <div style={{display:'flex',alignItems:'center',gap:5,paddingRight:10}}>
            <span className="status-dot blink"/><span className="label">Live</span>
          </div>
          {macro&&(<>
            <HStat label="SRM"          value={(macro.srm??0).toFixed(3)}              color={(macro.srm??0)>1.2?'var(--amber)':'var(--accent)'}/>
            <HStat label="Yield Spread" value={(macro.yield_spread??0).toFixed(2)+'%'} color={(macro.yield_spread??0)<0?'var(--red)':'var(--text)'}/>
            <HStat label="CPI"          value={(macro.cpi??0).toFixed(2)+'%'}          color={(macro.cpi??0)>4?'var(--amber)':'var(--text)'}/>
            <HStat label="Fed Rate"     value={(macro.fed_funds_rate??0).toFixed(2)+'%'}/>
          </>)}
          <div style={{display:'flex',alignItems:'center',gap:10,paddingLeft:10,borderLeft:'1px solid rgba(255,255,255,0.06)'}}>
            {isPro ? (
              <span style={{fontFamily:'var(--font-mono)',fontSize:'.6rem',fontWeight:700,color:'#38bdf8',background:'rgba(56,189,248,0.1)',border:'1px solid rgba(56,189,248,0.3)',borderRadius:4,padding:'2px 8px',letterSpacing:'.08em'}}>PRO</span>
            ) : (
              <button onClick={()=>{setUpgradeReason(undefined);setShowUpgrade(true)}} style={{fontFamily:'var(--font-mono)',fontSize:'.6rem',fontWeight:700,color:'#060d1b',background:'#38bdf8',border:'none',borderRadius:4,padding:'3px 10px',letterSpacing:'.07em',cursor:'pointer',whiteSpace:'nowrap'}}>
                UPGRADE ↗
              </button>
            )}
            <UserButton appearance={{ elements: { avatarBox:'w-7 h-7' } }}/>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section style={{padding:'clamp(48px,8vw,80px) 24px clamp(36px,6vw,56px)',textAlign:'center',maxWidth:720,margin:'0 auto',width:'100%'}}>
        <div style={{display:'inline-flex',alignItems:'center',gap:7,padding:'4px 14px',border:'1px solid rgba(56,189,248,0.2)',borderRadius:20,marginBottom:22,background:'rgba(56,189,248,0.04)'}}>
          <span style={{width:5,height:5,borderRadius:'50%',background:'var(--accent)',display:'inline-block'}}/>
          <span style={{fontSize:'.6rem',letterSpacing:'.12em',textTransform:'uppercase',color:'var(--accent)',fontFamily:'var(--font-mono)'}}>Agentic Multi-Factor Risk Engine</span>
        </div>
        <h1 style={{fontFamily:'var(--font-display)',fontSize:'clamp(2.8rem,7vw,4.8rem)',fontWeight:800,letterSpacing:'-.035em',lineHeight:1,marginBottom:16}}>
          <span style={{color:'var(--text)'}}>Omni</span><span style={{color:'var(--accent)'}}>Signal</span>
        </h1>
        <p style={{fontFamily:'var(--font-mono)',fontSize:'.78rem',color:'var(--muted)',lineHeight:1.8,marginBottom:36}}>
          FRED macro · Yahoo Finance technicals · RSS news sentiment<br/>Unified into a single risk-adjusted equity verdict.
        </p>

        {!isPro && (
          <div style={{display:'inline-flex',alignItems:'center',gap:6,padding:'5px 14px',background:'rgba(245,158,11,0.07)',border:'1px solid rgba(245,158,11,0.2)',borderRadius:20,marginBottom:20}}>
            <span style={{fontFamily:'var(--font-mono)',fontSize:'.62rem',color:'#f59e0b',letterSpacing:'.06em'}}>
              FREE: {FREE_LIMIT - analysisCount} of {FREE_LIMIT} analyses remaining today
            </span>
            <button onClick={()=>{setUpgradeReason(undefined);setShowUpgrade(true)}} style={{fontFamily:'var(--font-mono)',fontSize:'.58rem',fontWeight:700,color:'#38bdf8',background:'transparent',border:'none',cursor:'pointer',padding:0,letterSpacing:'.06em',textDecoration:'underline'}}>
              Go Pro ↗
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{display:'flex',justifyContent:'center',gap:8,marginBottom:16}}>
          <input type="text" value={ticker} onChange={e=>setTicker(e.target.value.toUpperCase().replace(/[^A-Z.^]/g,''))} placeholder="TICKER" maxLength={8} className="ticker-input" style={{width:200,background:'rgba(10,22,40,0.95)',border:'1px solid var(--border-hi)',borderRadius:6,padding:'11px 16px',fontSize:'1rem',fontFamily:'var(--font-mono)',fontWeight:700,letterSpacing:'.12em',color:'var(--text)',caretColor:'var(--accent)',outline:'none'}}/>
          <button type="submit" disabled={loading||!ticker} style={{background:loading||!ticker?'rgba(56,189,248,0.15)':'var(--accent)',color:loading||!ticker?'var(--accent)':'#060d1b',border:'1px solid '+(loading||!ticker?'var(--border-hi)':'transparent'),borderRadius:6,padding:'11px 18px',fontSize:'.72rem',fontFamily:'var(--font-mono)',fontWeight:700,letterSpacing:'.08em',cursor:loading||!ticker?'not-allowed':'pointer',whiteSpace:'nowrap'}}>
            {loading?'ANALYZING…':'ANALYZE →'}
          </button>
        </form>

        <div style={{display:'flex',justifyContent:'center',alignItems:'center',gap:8,marginBottom:20}}>
          <label style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',fontFamily:'var(--font-mono)',fontSize:'.62rem',color:'var(--muted)',letterSpacing:'.06em'}}>
            <input type="checkbox" checked={fast} onChange={e=>setFast(e.target.checked)} style={{accentColor:'var(--accent)',width:12,height:12}}/>
            FAST MODE (skip sentiment · ~3s)
          </label>
        </div>
        <div style={{display:'flex',gap:6,justifyContent:'center',flexWrap:'wrap'}}>
          {QUICK.map(s=><button key={s} className="chip" onClick={()=>{setTicker(s);run(s)}}>{s}</button>)}
        </div>
      </section>

      {/* CONTENT */}
      <main style={{flex:1,padding:'0 clamp(14px,3vw,32px) 60px',maxWidth:1180,margin:'0 auto',width:'100%'}}>
        {error&&(<div className="fade-up" style={{background:'rgba(239,68,68,0.07)',border:'1px solid rgba(239,68,68,0.22)',borderRadius:8,padding:'13px 18px',marginBottom:22,display:'flex',alignItems:'center',gap:10}}><span style={{color:'var(--red)',fontSize:'.85rem'}}>✕</span><span style={{fontFamily:'var(--font-mono)',fontSize:'.78rem',color:'#fca5a5'}}>{error}</span></div>)}

        {loading&&(<div style={{display:'flex',flexDirection:'column',gap:14}}><div className="grid-halves"><Skel h={200}/><Skel h={200}/></div><Skel h={240}/><div className="grid-asymmetric"><Skel h={280}/><Skel h={280}/></div></div>)}

        {result&&!loading&&(
          <div style={{display:'flex',flexDirection:'column',gap:14}}>
            <div className="grid-halves fade-up-1">
              <VerdictBadge verdict={result.verdict} signalScore={result.signal_score} riskAdjusted={result.risk_adjusted_signal} srm={result.srm}/>
              <div className="card" style={{padding:'20px 22px',display:'flex',flexDirection:'column'}}>
                <div className="section-heading"><span>{result.ticker} · Snapshot</span></div>
                <div style={{marginBottom:16}}><div className="label" style={{marginBottom:4}}>Current Price</div><div style={{fontFamily:'var(--font-mono)',fontSize:'2.2rem',fontWeight:700,letterSpacing:'-.02em',color:'var(--text)',lineHeight:1}}>${(result.current_price??0).toFixed(2)}</div></div>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'12px 16px',marginTop:'auto'}}>
                  {[
                    {label:'RSI (14)',    value:(result.rsi??0).toFixed(1),                   color:(result.rsi??0)>70?'var(--red)':(result.rsi??0)<30?'var(--green)':'var(--text)'},
                    {label:'21D Return', value:((result.momentum??0)*100).toFixed(2)+'%',     color:(result.momentum??0)>0?'var(--green)':'var(--red)'},
                    {label:'Sharpe',     value:(result.sharpe_ratio??0).toFixed(3),           color:(result.sharpe_ratio??0)>1?'var(--green)':(result.sharpe_ratio??0)<0?'var(--red)':'var(--amber)'},
                    {label:'Volatility', value:((result.volatility??0)*100).toFixed(1)+'%',   color:(result.volatility??0)>0.4?'var(--red)':(result.volatility??0)>0.25?'var(--amber)':'var(--green)'},
                    {label:'Sortino',    value:(result.sortino_ratio??0).toFixed(3),          color:(result.sortino_ratio??0)>1?'var(--green)':'var(--text)'},
                    {label:'Drawdown',   value:((result.max_drawdown??0)*100).toFixed(2)+'%', color:'var(--red)'},
                  ].map(({label,value,color})=>(<div key={label}><div className="label" style={{marginBottom:3}}>{label}</div><div style={{fontFamily:'var(--font-mono)',fontSize:'.9rem',fontWeight:600,color}}>{value}</div></div>))}
                </div>
              </div>
            </div>

            {result.price_history.length>0&&(
              <div className="fade-up-2">
                {/* Timeframe toggle */}
                <div style={{display:'flex',gap:6,justifyContent:'flex-end',marginBottom:8,alignItems:'center'}}>
                  {!isPro&&<span style={{fontFamily:'var(--font-mono)',fontSize:'.58rem',color:'var(--muted)',marginRight:4}}>Pro: all timeframes</span>}
                  {[['1mo','1M'],['3mo','3M'],['6mo','6M'],['1y','1Y'],['5y','5Y']].map(([val,lbl])=>(
                    <button key={val} onClick={()=>handlePeriod(val)}
                      style={{fontFamily:'var(--font-mono)',fontSize:'.62rem',fontWeight:600,padding:'3px 10px',borderRadius:4,border:'1px solid',borderColor:period===val?'var(--accent)':'rgba(255,255,255,0.1)',background:period===val?'rgba(56,189,248,0.12)':'transparent',color:period===val?'var(--accent)':!isPro&&val!=='3mo'?'rgba(255,255,255,0.2)':'var(--muted)',cursor:'pointer',position:'relative'}}>
                      {lbl}{!isPro&&val!=='3mo'&&<span style={{fontSize:'.45rem',color:'#f59e0b',marginLeft:2}}>PRO</span>}
                    </button>
                  ))}
                </div>
                <PriceChart data={result.price_history} ticker={result.ticker}/>
              </div>
            )}

            <div className="grid-asymmetric fade-up-3">
              <MacroPanel macro={result.macro}/>
              <TechnicalPanel
                rsi={result.rsi} sharpe={result.sharpe_ratio} sortino={result.sortino_ratio}
                volatility={result.volatility} momentum={result.momentum} drawdown={result.max_drawdown}
                sentiment={result.sentiment_score} sentimentLabel={result.sentiment_label}
                headlineCount={result.sentiment_headline_count}
                headlines={isPro ? result.headlines : result.headlines?.map((h:any)=>({...h, url:''}))}
              />
            </div>
            {!isPro&&result.headlines?.length>0&&(
              <div style={{textAlign:'center',padding:'8px 0'}}>
                <span style={{fontFamily:'var(--font-mono)',fontSize:'.65rem',color:'var(--muted)'}}>
                  Article links available on{' '}
                  <button onClick={()=>{setUpgradeReason('feature');setShowUpgrade(true)}} style={{fontFamily:'var(--font-mono)',fontSize:'.65rem',color:'#38bdf8',background:'transparent',border:'none',cursor:'pointer',textDecoration:'underline',padding:0}}>Pro plan ↗</button>
                </span>
              </div>
            )}
          </div>
        )}

        {!result&&!loading&&!error&&(
          <div style={{display:'flex',flexDirection:'column',alignItems:'center',padding:'40px 0 60px',gap:28}}>
            <div style={{width:72,height:72,border:'1px solid var(--border-hi)',borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',background:'var(--accent-dim)'}}><Logo/></div>
            <p className="label" style={{fontSize:'.68rem',textAlign:'center'}}>Enter a ticker above to start the analysis pipeline</p>
            {macro&&(
              <div style={{display:'flex',flexWrap:'wrap',gap:0,border:'1px solid var(--border)',borderRadius:8,overflow:'hidden',background:'var(--bg-card)'}}>
                {[
                  {label:'Systemic Risk Multiplier',value:(macro.srm??0).toFixed(3),              color:(macro.srm??0)>1.2?'var(--amber)':'var(--accent)'},
                  {label:'Yield Spread (10Y–2Y)',   value:(macro.yield_spread??0).toFixed(2)+'%', color:(macro.yield_spread??0)<0?'var(--red)':'var(--text)'},
                  {label:'CPI Inflation',            value:(macro.cpi??0).toFixed(2)+'%',          color:(macro.cpi??0)>4?'var(--amber)':'var(--text)'},
                  {label:'Fed Funds Rate',           value:(macro.fed_funds_rate??0).toFixed(2)+'%', color:'var(--text)'},
                ].map(({label,value,color})=>(
                  <div key={label} style={{padding:'18px 24px',borderRight:'1px solid var(--border)',minWidth:140,flex:'1 1 120px'}}>
                    <div className="label" style={{marginBottom:6}}>{label}</div>
                    <div style={{fontFamily:'var(--font-mono)',fontSize:'1.3rem',fontWeight:700,color,letterSpacing:'-.01em'}}>{value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      <footer style={{borderTop:'1px solid rgba(56,189,248,0.06)',padding:'14px 24px',display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:8}}>
        <div style={{display:'flex',alignItems:'center',gap:8}}><Logo/><span className="label">OmniSignal · Agentic Risk Engine</span></div>
        <span className="label" style={{fontSize:'.58rem'}}>Research &amp; education only · Not financial advice · <span style={{color:'var(--accent)'}}>iAakash1</span></span>
      </footer>
    </div>
  )
}
