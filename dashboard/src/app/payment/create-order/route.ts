import { auth } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'
import Razorpay from 'razorpay'

/**
 * Razorpay SDK rejections are plain objects, NOT Error instances:
 *   { statusCode: 400, error: { code, description, source, step, reason, metadata, field } }
 * Treating them as Error (e.message) is why failures previously surfaced as a
 * generic 500 with no detail.
 */
interface RazorpayApiError {
  statusCode?: number
  error?: {
    code?: string
    description?: string
    source?: string
    step?: string
    reason?: string
    metadata?: Record<string, unknown>
    field?: string
  }
}

/** Razorpay requires receipt length <= 40 chars. Clerk user ids make the
    naive `omni_<userId>_<ts>` 51 chars, which test mode rejects with
    BAD_REQUEST_ERROR. Keep prefix + full timestamp (uniqueness) + as much
    of the user id as fits. */
function buildReceipt(userId: string): string {
  const receipt = `omni_${Date.now()}_${userId}`
  return receipt.length <= 40 ? receipt : receipt.slice(0, 40)
}

export async function POST() {
  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  if (!process.env.RAZORPAY_KEY_ID || !process.env.RAZORPAY_KEY_SECRET) {
    // Operator detail stays in the server log; the browser gets a plain message.
    console.error(
      '[create-order] missing RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET — set both server-side (no NEXT_PUBLIC_ prefix)',
    )
    return NextResponse.json(
      { message: 'Payments aren’t configured on this deployment yet.' },
      { status: 500 },
    )
  }

  const rzp = new Razorpay({
    // Server-only variables: backend routes never read NEXT_PUBLIC_* values.
    key_id: process.env.RAZORPAY_KEY_ID,
    key_secret: process.env.RAZORPAY_KEY_SECRET,
  })

  const orderRequest = {
    amount: 10000, // paise → ₹100.00; integer >= 100 required by Razorpay
    currency: 'INR',
    receipt: buildReceipt(userId), // <= 40 chars enforced above
  }

  try {
    const order = await rzp.orders.create(orderRequest)
    return NextResponse.json(order)
  } catch (e: unknown) {
    const rzpError = e as RazorpayApiError
    // Full diagnostics to the server log only — the response carries a
    // human-readable message and nothing else (no stacks, no env shape).
    console.error('[create-order] order creation failed:', e)

    return NextResponse.json(
      {
        message:
          rzpError.error?.description ??
          'The payment provider rejected the request. Please try again in a moment.',
      },
      { status: 500 },
    )
  }
}
