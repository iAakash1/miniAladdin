import { auth, clerkClient } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'
import Razorpay from 'razorpay'
import {
  parsePaymentCallback,
  signatureMatches,
  verifyPaymentBinding,
} from '../payment-security'

export async function POST(req: Request) {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const keyId = process.env.RAZORPAY_KEY_ID
  const keySecret = process.env.RAZORPAY_KEY_SECRET
  if (!keyId || !keySecret) {
    console.error('[verify-payment] missing server-side Razorpay credentials')
    return NextResponse.json(
      { error: 'Payments are not configured on this deployment.' },
      { status: 503 },
    )
  }

  const callback = parsePaymentCallback(await req.json().catch(() => null))
  if (!callback) {
    return NextResponse.json({ error: 'Malformed payment response' }, { status: 400 })
  }

  if (!signatureMatches(callback, keySecret)) {
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 })
  }

  const rzp = new Razorpay({ key_id: keyId, key_secret: keySecret })
  let order
  let payment
  try {
    ;[order, payment] = await Promise.all([
      rzp.orders.fetch(callback.razorpay_order_id),
      rzp.payments.fetch(callback.razorpay_payment_id),
    ])
  } catch (error) {
    console.error('[verify-payment] provider lookup failed:', error)
    return NextResponse.json(
      { error: 'The payment provider could not confirm this purchase yet.' },
      { status: 502 },
    )
  }

  const binding = verifyPaymentBinding(userId, order, payment)
  if (!binding.ok) {
    console.error(
      '[verify-payment] rejected callback:',
      binding.reason,
      callback.razorpay_order_id,
      callback.razorpay_payment_id,
    )
    return NextResponse.json(
      { error: 'Payment is not captured for this account and product.' },
      { status: 409 },
    )
  }

  const clerk = await clerkClient()
  const current = await clerk.users.getUser(userId)
  if (
    current.privateMetadata.razorpayPaymentId === callback.razorpay_payment_id &&
    current.publicMetadata.isPro === true
  ) {
    return NextResponse.json({ success: true, alreadyProcessed: true })
  }

  await clerk.users.updateUserMetadata(userId, {
    publicMetadata: {
      ...current.publicMetadata,
      isPro: true,
      proSince: new Date().toISOString(),
      proProduct: 'one-time-access',
    },
    privateMetadata: {
      ...current.privateMetadata,
      razorpayOrderId: callback.razorpay_order_id,
      razorpayPaymentId: callback.razorpay_payment_id,
    },
  })

  return NextResponse.json({ success: true })
}
