'use client'
import { useState } from 'react'
import { useUser } from '@clerk/nextjs'

export default function UpgradeModal({ onClose, reason }: { onClose: () => void; reason?: string }) {
  const { user } = useUser()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleUpgrade = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/payment/create-order', { method: 'POST' })
      if (!res.ok) throw new Error('Could not create order')
      const order = await res.json()

      const options = {
        key:         process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID,
        amount:      order.amount,
        currency:    order.currency,
        name:        'OmniSignal',
        description: 'Pro Subscription — Unlimited Access',
        order_id:    order.id,
        handler: async (response: any) => {
          const verifyRes = await fetch('/payment/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(response),
          })
          if (verifyRes.ok) {
            await user?.reload()
            onClose()
            window.location.reload()
          } else {
            setError('Payment verification failed. Contact support.')
          }
        },
        prefill: {
          email: user?.emailAddresses[0]?.emailAddress ?? '',
          name:  user?.fullName ?? '',
        },
        theme:  { color: '#38bdf8' },
        modal:  { ondismiss: () => setLoading(false) },
      }

      const rzp = new (window as any).Razorpay(options)
      rzp.open()
    } catch (e: any) {
      setError(e.message || 'Something went wrong')
      setLoading(false)
    }
  }

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', backdropFilter:'blur(6px)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:1000 }}>
      <div style={{ background:'#0a1628', border:'1px solid rgba(56,189,248,0.2)', borderRadius:12, padding:'36px 40px', maxWidth:460, width:'90%', boxShadow:'0 0 60px rgba(56,189,248,0.1)' }}>

        {/* Header */}
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:24 }}>
          <div>
            <div style={{ fontFamily:'Syne, sans-serif', fontWeight:800, fontSize:'1.4rem', color:'#dde6f5', letterSpacing:'-.02em' }}>
              Upgrade to <span style={{ color:'#38bdf8' }}>Pro</span>
            </div>
            {reason === 'limit' && (
              <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.65rem', color:'#f59e0b', marginTop:4, letterSpacing:'.06em' }}>
                ⚠ You have reached your free daily limit
              </div>
            )}
          </div>
          <button onClick={onClose} style={{ background:'transparent', border:'none', color:'#4b6480', cursor:'pointer', fontSize:'1.2rem', lineHeight:1 }}>✕</button>
        </div>

        {/* Price */}
        <div style={{ background:'rgba(56,189,248,0.06)', border:'1px solid rgba(56,189,248,0.15)', borderRadius:8, padding:'16px 20px', marginBottom:24, textAlign:'center' }}>
          <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'2rem', fontWeight:700, color:'#38bdf8', letterSpacing:'-.02em', lineHeight:1 }}>₹50</div>
          <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.65rem', color:'#4b6480', marginTop:4, letterSpacing:'.08em' }}>PER MONTH · CANCEL ANYTIME</div>
        </div>

        {/* Features */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:28 }}>
          {[
            ['✓', 'Unlimited analyses per day', true],
            ['✓', 'All timeframes — 1M, 3M, 6M, 1Y, 5Y', true],
            ['✓', 'Full news feed with article links', true],
            ['✓', 'FRED macro data — real-time SRM', true],
            ['✗', '5 analyses / day', false],
            ['✗', '3-month chart only', false],
          ].map(([icon, text, isPro]) => (
            <div key={String(text)} style={{ display:'flex', alignItems:'center', gap:10 }}>
              <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.75rem', color: isPro ? '#10b981' : '#374151', fontWeight:700, width:14, flexShrink:0 }}>{icon}</span>
              <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.73rem', color: isPro ? '#dde6f5' : '#374151', textDecoration: isPro ? 'none' : 'line-through' }}>{text}</span>
            </div>
          ))}
        </div>

        {error && <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.7rem', color:'#ef4444', marginBottom:16 }}>{error}</div>}

        <button
          onClick={handleUpgrade}
          disabled={loading}
          style={{ width:'100%', background: loading ? 'rgba(56,189,248,0.2)' : '#38bdf8', color: loading ? '#38bdf8' : '#060d1b', border:'none', borderRadius:7, padding:'13px 0', fontFamily:'JetBrains Mono, monospace', fontWeight:700, fontSize:'.8rem', letterSpacing:'.08em', cursor: loading ? 'not-allowed' : 'pointer', transition:'all .16s ease' }}
        >
          {loading ? 'OPENING PAYMENT…' : 'UPGRADE NOW — ₹50/MONTH'}
        </button>

        <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'.58rem', color:'#374151', textAlign:'center', marginTop:12, letterSpacing:'.04em' }}>
          Secured by Razorpay · Test mode active
        </div>
      </div>
    </div>
  )
}
