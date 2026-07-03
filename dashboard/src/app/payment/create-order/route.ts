import { auth } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'
import Razorpay from 'razorpay'

export async function POST() {
  const rzp = new Razorpay({
    // Server-only variables: backend routes never read NEXT_PUBLIC_* values.
    key_id:     process.env.RAZORPAY_KEY_ID!,
    key_secret: process.env.RAZORPAY_KEY_SECRET!,
  })
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  try {
    const order = await rzp.orders.create({
      amount:   5000,
      currency: 'INR',
      receipt:  'omni_' + userId + '_' + Date.now(),
    })
    return NextResponse.json(order)
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Order creation failed'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
