import crypto from 'node:crypto'

/** Server-side contract for the one-time Pro purchase. */
export const PRO_PRODUCT = 'omnisignal-pro-access-v1'
export const PRO_AMOUNT_PAISE = 10_000
export const PRO_CURRENCY = 'INR'

export interface PaymentCallback {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}

/**
 * The provider records this module needs, described structurally.
 *
 * `notes` is typed `unknown` on purpose. Razorpay's SDK types it as a map that
 * may also be an array, and the value is arbitrary data we asked the provider
 * to store for us and are now reading back across a trust boundary. Declaring a
 * shape here would let the compiler vouch for something only the provider can,
 * so the shape is checked at runtime by `readNote` instead.
 */
interface ProviderOrder {
  id: string
  amount: number | string
  amount_paid: number | string
  currency: string
  status: string
  notes?: unknown
}

interface ProviderPayment {
  id: string
  order_id?: string | null
  amount: number | string
  currency: string
  status: string
  captured: boolean
}

/**
 * Read one provider-stored note as a string, or null.
 *
 * Anything that is not a plain object yields null, and null never equals a
 * Clerk user id or our product constant — so a malformed or array-shaped
 * `notes` fails the binding closed rather than being skipped.
 */
function readNote(notes: unknown, key: string): string | null {
  if (typeof notes !== 'object' || notes === null || Array.isArray(notes)) return null
  const value = (notes as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : null
}

export type PaymentBindingFailure =
  | 'order_user_mismatch'
  | 'order_product_mismatch'
  | 'order_contract_mismatch'
  | 'order_not_paid'
  | 'payment_order_mismatch'
  | 'payment_contract_mismatch'
  | 'payment_not_captured'

export type PaymentBindingResult =
  | { ok: true }
  | { ok: false; reason: PaymentBindingFailure }

/** Parse the untrusted callback before cryptographic or provider work. */
export function parsePaymentCallback(value: unknown): PaymentCallback | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Record<string, unknown>
  const orderId = candidate.razorpay_order_id
  const paymentId = candidate.razorpay_payment_id
  const signature = candidate.razorpay_signature
  if (
    typeof orderId !== 'string' || !/^order_[A-Za-z0-9]+$/.test(orderId) ||
    typeof paymentId !== 'string' || !/^pay_[A-Za-z0-9]+$/.test(paymentId) ||
    typeof signature !== 'string' || !/^[a-f0-9]{64}$/i.test(signature)
  ) return null
  return {
    razorpay_order_id: orderId,
    razorpay_payment_id: paymentId,
    razorpay_signature: signature.toLowerCase(),
  }
}

/** Constant-time comparison for the signed checkout callback. */
export function signatureMatches(callback: PaymentCallback, secret: string): boolean {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(`${callback.razorpay_order_id}|${callback.razorpay_payment_id}`)
    .digest()
  const supplied = Buffer.from(callback.razorpay_signature, 'hex')
  return supplied.length === expected.length && crypto.timingSafeEqual(expected, supplied)
}

/**
 * Bind a verified callback to the authenticated user and exact product.
 *
 * A valid signature proves only that the identifiers belong together. It does
 * not prove that the order belongs to this user, carries our price, or was
 * captured. Provider-fetched records establish those separate claims.
 */
export function verifyPaymentBinding(
  userId: string,
  order: ProviderOrder,
  payment: ProviderPayment,
): PaymentBindingResult {
  if (readNote(order.notes, 'clerk_user_id') !== userId) {
    return { ok: false, reason: 'order_user_mismatch' }
  }
  if (readNote(order.notes, 'product') !== PRO_PRODUCT) {
    return { ok: false, reason: 'order_product_mismatch' }
  }
  if (
    Number(order.amount) !== PRO_AMOUNT_PAISE ||
    order.currency !== PRO_CURRENCY ||
    order.id.length === 0
  ) return { ok: false, reason: 'order_contract_mismatch' }
  // `amount_paid` is the only guard in this module expressed as a `<`
  // comparison, and that makes it the only one that failed OPEN. A missing or
  // non-numeric value coerces to NaN, and `NaN < 10000` is false, so the guard
  // did not fire and an order with `status: 'paid'` but no recorded amount was
  // accepted. Requiring a finite number restores fail-closed: NaN is not finite,
  // so the check now rejects rather than skips.
  const paid = Number(order.amount_paid)
  if (order.status !== 'paid' || !Number.isFinite(paid) || paid < PRO_AMOUNT_PAISE) {
    return { ok: false, reason: 'order_not_paid' }
  }
  if (payment.order_id !== order.id) return { ok: false, reason: 'payment_order_mismatch' }
  if (
    Number(payment.amount) !== PRO_AMOUNT_PAISE ||
    payment.currency !== PRO_CURRENCY ||
    payment.id.length === 0
  ) return { ok: false, reason: 'payment_contract_mismatch' }
  if (payment.status !== 'captured' || !payment.captured) {
    return { ok: false, reason: 'payment_not_captured' }
  }
  return { ok: true }
}
