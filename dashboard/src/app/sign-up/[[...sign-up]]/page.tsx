import { SignUp } from '@clerk/nextjs'

export default function SignUpPage() {
  return (
    <div style={{ minHeight:'100vh', background:'#060d1b', display:'flex', position:'relative', overflow:'hidden' }}>
      {/* Dot grid */}
      <div style={{ position:'absolute', inset:0, backgroundImage:'radial-gradient(rgba(56,189,248,0.055) 1px, transparent 1px)', backgroundSize:'26px 26px', pointerEvents:'none' }} />
      {/* Ambient glow */}
      <div style={{ position:'absolute', top:'-200px', left:'30%', width:'800px', height:'600px', background:'radial-gradient(ellipse, rgba(56,189,248,0.06) 0%, transparent 68%)', pointerEvents:'none' }} />

      {/* Left panel — branding */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', justifyContent:'center', padding:'60px', position:'relative', zIndex:1 }}>
        <div style={{ maxWidth:420 }}>
          {/* Logo */}
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:48 }}>
            <svg width="28" height="28" viewBox="0 0 22 22" fill="none">
              <polygon points="11,1 21,6 21,16 11,21 1,16 1,6" stroke="#38bdf8" strokeWidth="1.2" fill="rgba(56,189,248,0.1)"/>
              <circle cx="11" cy="11" r="3.2" fill="#38bdf8" fillOpacity="0.9"/>
              <line x1="11" y1="5" x2="11" y2="8.2" stroke="#38bdf8" strokeWidth="1"/>
              <line x1="11" y1="13.8" x2="11" y2="17" stroke="#38bdf8" strokeWidth="1"/>
            </svg>
            <span style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'1.4rem', letterSpacing:'.08em', color:'#dde6f5', textTransform:'uppercase' }}>OmniSignal</span>
          </div>

          <h1 style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'2.8rem', letterSpacing:'-.03em', lineHeight:1.1, color:'#dde6f5', marginBottom:20 }}>
            Your edge in<br/><span style={{ color:'#38bdf8' }}>the market.</span>
          </h1>
          <p style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.78rem', color:'#4b6480', lineHeight:1.8, marginBottom:40 }}>
            FRED macro signals · Live technicals<br/>
            NewsAPI sentiment · Risk-adjusted verdicts
          </p>

          {/* Feature chips */}
          {[
            ['⬡', 'Systemic Risk Multiplier from FRED'],
            ['↗', 'Real-time price charts — 1M to 5Y'],
            ['◎', 'News sentiment from 80,000+ sources'],
            ['★', 'Pro plan from ₹50/month'],
          ].map(([icon, text]) => (
            <div key={String(text)} style={{ display:'flex', alignItems:'center', gap:12, marginBottom:14 }}>
              <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.8rem', color:'#38bdf8', width:16, flexShrink:0 }}>{icon}</span>
              <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.72rem', color:'#64748b', letterSpacing:'.03em' }}>{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — Clerk form */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', padding:'60px 60px 60px 0', position:'relative', zIndex:1, minWidth:480 }}>
        <div style={{ width:'100%', maxWidth:400 }}>
          <SignUp
            appearance={{
              variables: {
                colorPrimary:       '#38bdf8',
                colorBackground:    '#0a1628',
                colorText:          '#dde6f5',
                colorTextSecondary: '#4b6480',
                colorInputBackground: '#0d1e36',
                colorInputText:     '#dde6f5',
                colorDanger:        '#ef4444',
                borderRadius:       '7px',
                fontFamily:         'JetBrains Mono, monospace',
                fontSize:           '14px',
              },
              elements: {
                card:              { background:'#0a1628', border:'1px solid rgba(56,189,248,0.15)', boxShadow:'0 0 48px rgba(56,189,248,0.08)', borderRadius:'10px' },
                headerTitle:       { fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'1.3rem', color:'#dde6f5', letterSpacing:'-.01em' },
                headerSubtitle:    { color:'#4b6480', fontSize:'.72rem' },
                socialButtonsBlockButton: { background:'rgba(56,189,248,0.07)', border:'1px solid rgba(56,189,248,0.15)', color:'#dde6f5', borderRadius:'6px' },
                socialButtonsBlockButtonText: { fontFamily:'JetBrains Mono, monospace', fontSize:'.72rem' },
                dividerLine:       { background:'rgba(56,189,248,0.1)' },
                dividerText:       { color:'#4b6480', fontFamily:'JetBrains Mono, monospace', fontSize:'.65rem' },
                formFieldLabel:    { color:'#4b6480', fontFamily:'JetBrains Mono, monospace', fontSize:'.65rem', letterSpacing:'.08em', textTransform:'uppercase' },
                formFieldInput:    { background:'#0d1e36', border:'1px solid rgba(56,189,248,0.15)', color:'#dde6f5', borderRadius:'6px', fontFamily:'JetBrains Mono, monospace' },
                formButtonPrimary: { background:'#38bdf8', color:'#060d1b', fontFamily:'JetBrains Mono, monospace', fontWeight:700, letterSpacing:'.06em', borderRadius:'6px' },
                footerActionLink:  { color:'#38bdf8', fontFamily:'JetBrains Mono, monospace' },
                identityPreviewText: { color:'#dde6f5', fontFamily:'JetBrains Mono, monospace' },
                formResendCodeLink: { color:'#38bdf8' },
              }
            }}
          />
        </div>
      </div>
    </div>
  )
}
