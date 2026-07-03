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
  // ── Environment diagnostics (never log secret values) ──────────────────
  const hasKeyId = Boolean(process.env.RAZORPAY_KEY_ID)
  const hasSecret = Boolean(process.env.RAZORPAY_KEY_SECRET)
  // Key IDs are public by design; first 8 chars is enough to spot
  // test/live mode (rzp_test / rzp_live) and typos.
  const keyIdPrefix = process.env.RAZORPAY_KEY_ID?.slice(0, 8) ?? null

  const { userId } = await auth()
  if (!userId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  console.log('[create-order] env', { hasKeyId, hasSecret, keyIdPrefix })

  if (!hasKeyId || !hasSecret) {
    console.error('[create-order] missing server env vars', { hasKeyId, hasSecret })
    return NextResponse.json(
      {
        message:
          'Server is missing Razorpay credentials. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in Vercel (server-side, no NEXT_PUBLIC_ prefix).',
        razorpay: null,
        stack: null,
        environment: { hasKeyId, hasSecret, keyIdPrefix },
      },
      { status: 500 },
    )
  }

  const rzp = new Razorpay({
    // Server-only variables: backend routes never read NEXT_PUBLIC_* values.
    key_id: process.env.RAZORPAY_KEY_ID!,
    key_secret: process.env.RAZORPAY_KEY_SECRET!,
  })

  const orderRequest = {
    amount: 5000, // paise → ₹50.00; integer >= 100 required by Razorpay ✓
    currency: 'INR', // supported currency ✓
    receipt: buildReceipt(userId), // <= 40 chars enforced above ✓
  }

  console.log('[create-order] creating order', {
    amount: orderRequest.amount,
    currency: orderRequest.currency,
    receipt: orderRequest.receipt,
    receiptLength: orderRequest.receipt.length,
  })

  try {
    const order = await rzp.orders.create(orderRequest)
    console.log('[create-order] order created', { orderId: order.id, status: order.status })
    return NextResponse.json(order)
  } catch (e: unknown) {
    const rzpError = e as RazorpayApiError
    const diagnostics = {
      statusCode: rzpError.statusCode ?? null,
      code: rzpError.error?.code ?? null,
      description: rzpError.error?.description ?? null,
      source: rzpError.error?.source ?? null,
      step: rzpError.error?.step ?? null,
      reason: rzpError.error?.reason ?? null,
      field: rzpError.error?.field ?? null,
      metadata: rzpError.error?.metadata ?? null,
    }
    console.error('[create-order] razorpay error', JSON.stringify(diagnostics))

    // TEMPORARY DEBUG RESPONSE — verbose by design while diagnosing the
    // test-mode failure; revert to a generic message once resolved.
    // Contains no secrets (key prefix only; auth-gated route).
    return NextResponse.json(
      {
        message: diagnostics.description ?? 'Razorpay order creation failed',
        razorpay: diagnostics,
        stack: e instanceof Error ? e.stack ?? null : null,
        environment: { hasKeyId, hasSecret, keyIdPrefix },
      },
      { status: 500 },
    )
  }
}
