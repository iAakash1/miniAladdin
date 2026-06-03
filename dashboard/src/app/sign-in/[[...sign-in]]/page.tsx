import { SignIn } from '@clerk/nextjs'

export default function SignInPage() {
  return (
    <div style={{ minHeight:'100vh', background:'#060d1b', display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', position:'relative' }}>
      <div style={{ position:'absolute', inset:0, backgroundImage:'radial-gradient(rgba(56,189,248,0.055) 1px, transparent 1px)', backgroundSize:'26px 26px', pointerEvents:'none' }} />
      <div style={{ position:'absolute', top:'-180px', left:'50%', transform:'translateX(-50%)', width:'700px', height:'500px', background:'radial-gradient(ellipse, rgba(56,189,248,0.055) 0%, transparent 68%)', pointerEvents:'none' }} />
      <div style={{ position:'relative', zIndex:1, textAlign:'center', marginBottom:32 }}>
        <div style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'2.2rem', letterSpacing:'-.035em', color:'#dde6f5', lineHeight:1 }}>
          Omni<span style={{ color:'#38bdf8' }}>Signal</span>
        </div>
        <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.65rem', color:'#4b6480', marginTop:8, letterSpacing:'.1em', textTransform:'uppercase' }}>
          Agentic Multi-Factor Risk Engine
        </div>
      </div>
      <div style={{ position:'relative', zIndex:1 }}>
        <SignIn appearance={{ variables: { colorPrimary:'#38bdf8', colorBackground:'#0a1628', colorText:'#dde6f5', colorInputBackground:'#0d1e36', colorInputText:'#dde6f5', borderRadius:'7px', fontFamily:'JetBrains Mono, monospace' }, elements: { card:'border border-[rgba(56,189,248,0.15)] shadow-none', formButtonPrimary:'bg-[#38bdf8] text-[#060d1b] hover:bg-[#7dd3fc] font-bold', footerActionLink:'text-[#38bdf8]', headerTitle:'font-bold' } }} />
      </div>
    </div>
  )
}
