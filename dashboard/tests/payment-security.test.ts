import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import test from 'node:test'

import {
  PRO_AMOUNT_PAISE,
  PRO_CURRENCY,
  PRO_PRODUCT,
  parsePaymentCallback,
  signatureMatches,
  verifyPaymentBinding,
} from '../src/app/payment/payment-security'

const callback = {
  razorpay_order_id: 'order_Abc123',
  razorpay_payment_id: 'pay_Def456',
  razorpay_signature: '',
}
const order = {
  id: callback.razorpay_order_id,
  amount: PRO_AMOUNT_PAISE,
  amount_paid: PRO_AMOUNT_PAISE,
  currency: PRO_CURRENCY,
  status: 'paid',
  notes: { clerk_user_id: 'user_owner', product: PRO_PRODUCT },
}
const payment = {
  id: callback.razorpay_payment_id,
  order_id: callback.razorpay_order_id,
  amount: PRO_AMOUNT_PAISE,
  currency: PRO_CURRENCY,
  status: 'captured',
  captured: true,
}

test('accepts a captured payment bound to the authenticated user and product', () => {
  assert.deepEqual(verifyPaymentBinding('user_owner', order, payment), { ok: true })
})

test('a valid order cannot be replayed to upgrade another Clerk user', () => {
  assert.deepEqual(
    verifyPaymentBinding('user_attacker', order, payment),
    { ok: false, reason: 'order_user_mismatch' },
  )
})

test('amount, product, order, and capture state are fail-closed', () => {
  assert.equal(verifyPaymentBinding('user_owner', { ...order, amount: 1 }, payment).ok, false)
  assert.equal(
    verifyPaymentBinding(
      'user_owner',
      { ...order, notes: { ...order.notes, product: 'other' } },
      payment,
    ).ok,
    false,
  )
  assert.equal(
    verifyPaymentBinding('user_owner', order, { ...payment, order_id: 'order_Other' }).ok,
    false,
  )
  assert.equal(
    verifyPaymentBinding(
      'user_owner', order, { ...payment, status: 'authorized', captured: false },
    ).ok,
    false,
  )
})

test('callback parsing refuses missing and malformed identifiers', () => {
  assert.equal(parsePaymentCallback(null), null)
  assert.equal(parsePaymentCallback({ ...callback, razorpay_signature: 'nope' }), null)
  assert.equal(parsePaymentCallback({ ...callback, razorpay_order_id: '../order_1' }), null)
})

test('signature verification uses the exact order/payment pair', () => {
  const secret = 'test_secret'
  const signature = crypto
    .createHmac('sha256', secret)
    .update(`${callback.razorpay_order_id}|${callback.razorpay_payment_id}`)
    .digest('hex')
  const signed = { ...callback, razorpay_signature: signature }
  assert.equal(signatureMatches(signed, secret), true)
  assert.equal(signatureMatches({ ...signed, razorpay_payment_id: 'pay_Other' }, secret), false)
})

test('a missing or non-numeric amount_paid fails closed', () => {
  // The only `<` comparison in the module. NaN makes a `<` comparison false, so
  // before the finite check an order marked paid with no recorded amount was
  // accepted. Both shapes must now be refused.
  for (const amountPaid of [undefined, null, '', 'abc', Number.NaN]) {
    const record = { ...order, amount_paid: amountPaid } as unknown as typeof order
    assert.deepEqual(
      verifyPaymentBinding('user_owner', record, payment),
      { ok: false, reason: 'order_not_paid' },
      `amount_paid=${String(amountPaid)} must not pass`,
    )
  }
})

test('an array-shaped or absent notes object fails closed', () => {
  // Razorpay types notes as a map that may also be an array. An array has no
  // clerk_user_id, and reading one must refuse rather than skip the binding.
  for (const notes of [undefined, null, [], ['user_owner'], 'user_owner', 42]) {
    const record = { ...order, notes } as unknown as typeof order
    assert.deepEqual(
      verifyPaymentBinding('user_owner', record, payment),
      { ok: false, reason: 'order_user_mismatch' },
      `notes=${JSON.stringify(notes) ?? 'undefined'} must not pass`,
    )
  }
})

test('a non-string note value cannot satisfy the user binding', () => {
  // A numeric note that stringifies to the user id must not bind. Provider data
  // is compared by type as well as value.
  const record = { ...order, notes: { clerk_user_id: 12345, product: PRO_PRODUCT } }
  assert.deepEqual(
    verifyPaymentBinding('12345', record as unknown as typeof order, payment),
    { ok: false, reason: 'order_user_mismatch' },
  )
})
