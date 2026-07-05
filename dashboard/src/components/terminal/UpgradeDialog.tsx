'use client'

import { useState } from 'react'
import { useUser } from '@clerk/nextjs'
import Dialog from '@/components/ui/Dialog'

interface RazorpayResponse {
  razorpay_payment_id: string
  razorpay_order_id: string
  razorpay_signature: string
}

interface RazorpayOptions {
  key: string | undefined
  amount: number
  currency: string
  name: string
  description: string
  order_id: string
  handler: (response: RazorpayResponse) => void
  prefill: { email: string; name: string }
  theme: { color: string }
  modal: { ondismiss: () => void }
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => { open: () => void }
  }
}

/** Load the checkout script only when the dialog is actually used. */
function loadRazorpay(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve()
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Could not load the payment provider.'))
    document.body.appendChild(script)
  })
}

interface UpgradeDialogProps {
  open: boolean
  onClose: () => void
  reason?: 'limit' | 'feature'
}

export default function UpgradeDialog({ open, onClose, reason }: UpgradeDialogProps) {
  const { user } = useUser()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const startCheckout = async () => {
    setBusy(true)
    setError('')
    try {
      await loadRazorpay()
      const res = await fetch('/payment/create-order', { method: 'POST' })
      if (!res.ok) {
        // Surface the server's diagnostic message (temporary, while the
        // create-order route is in debug mode) instead of a generic string.
        const body = await res.json().catch(() => null)
        const detail = body?.message ?? 'Could not create the order. Please try again.'
        const code = body?.code ? ` [${body.code}]` : ''
        throw new Error(`${detail}${code}`)
      }
      const order = await res.json()

      if (!window.Razorpay) throw new Error('Payment provider unavailable.')
      const rzp = new window.Razorpay({
        key: process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID,
        amount: order.amount,
        currency: order.currency,
        name: 'OmniSignal',
        description: 'Pro subscription',
        order_id: order.id,
        handler: async (response) => {
          const verify = await fetch('/payment/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(response),
          })
          if (verify.ok) {
            await user?.reload()
            onClose()
            window.location.reload()
          } else {
            setError('Payment could not be verified. If you were charged, contact support.')
            setBusy(false)
          }
        },
        prefill: {
          email: user?.emailAddresses[0]?.emailAddress ?? '',
          name: user?.fullName ?? '',
        },
        theme: { color: '#1e6b54' },
        modal: { ondismiss: () => setBusy(false) },
      })
      rzp.open()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.')
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} labelledBy="upgrade-title">
      <div style={{ padding: '28px 30px 26px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
          <h2 id="upgrade-title" className="h-panel" style={{ fontSize: '1.125rem' }}>
            Upgrade to Pro
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="btn btn--ghost btn--sm"
            style={{ marginRight: -8, marginTop: -6 }}
          >
            ✕
          </button>
        </div>

        <p style={{ fontSize: '0.875rem', color: 'var(--muted)', marginBottom: 22, lineHeight: 1.6 }}>
          {reason === 'limit'
            ? "You've used today's five free analyses."
            : reason === 'feature'
              ? 'That view is part of Pro.'
              : 'Everything in Free, without the ceilings.'}
        </p>

        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 8,
            padding: '16px 18px',
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)',
            marginBottom: 22,
          }}
        >
          <span className="num" style={{ fontSize: '1.75rem', fontWeight: 600 }}>
            ₹100
          </span>
          <span style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>per month · cancel anytime</span>
        </div>

        <ul
          style={{
            listStyle: 'none',
            margin: '0 0 24px',
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 11,
          }}
        >
          {[
            'Unlimited analyses per day',
            'All chart timeframes — 1M to 5Y',
            'Article links in sentiment readouts',
          ].map((f) => (
            <li key={f} style={{ display: 'flex', gap: 10, fontSize: '0.875rem', color: 'var(--text)' }}>
              <span aria-hidden="true" style={{ color: 'var(--pos)', fontWeight: 600 }}>
                ✓
              </span>
              {f}
            </li>
          ))}
        </ul>

        {error && (
          <p role="alert" style={{ fontSize: '0.8125rem', color: 'var(--neg)', marginBottom: 14 }}>
            {error}
          </p>
        )}

        <button
          type="button"
          className="btn btn--accent"
          onClick={startCheckout}
          disabled={busy}
          style={{ width: '100%' }}
        >
          {busy ? 'Opening payment…' : 'Continue to payment'}
        </button>

        <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', textAlign: 'center', marginTop: 12 }}>
          Secured by Razorpay
        </p>
      </div>
    </Dialog>
  )
}
