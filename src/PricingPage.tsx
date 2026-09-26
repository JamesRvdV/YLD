import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { SessionUser } from './AuthPages'

type BillingStatus = { plan: string; status: string } | null

const plans = [
  { key: 'local', name: 'LOCAL', price: '30', description: 'Proposed for one focused kitchen.', items: ['Daily prep plans', 'Demand adjustments', 'Actuals logging'] },
  { key: 'multi_chain', name: 'MULTI-CHAIN', price: '119', description: 'Proposed for teams running multiple locations.', items: ['Everything in Local', 'Unlimited team members', 'Multi-site view'] },
  { key: 'enterprise', name: 'ENTERPRISE', price: 'CUSTOM', description: 'Proposed for operators with a tailored rollout.', items: ['Everything in Multi-chain', 'Weekly performance view', 'Dedicated onboarding'] },
]

export default function PricingPage({ nav, onLogin, user }: { nav: ReactNode; onLogin: () => void; user: SessionUser | null }) {
  const [testCheckout, setTestCheckout] = useState(false)
  const [billing, setBilling] = useState<BillingStatus>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmationTimedOut, setConfirmationTimedOut] = useState(false)
  const [checkoutRecovery, setCheckoutRecovery] = useState<'open' | 'expired' | null>(null)
  const [checkoutUrl, setCheckoutUrl] = useState('')
  const abandoned = useRef(false)
  const checkoutResult = new URLSearchParams(window.location.search).get('checkout')

  useEffect(() => {
    void fetch('/api/billing/config').then(response => response.ok ? response.json() : null)
      .then(body => setTestCheckout(Boolean(body?.test_checkout_enabled))).catch(() => setTestCheckout(false))
  }, [])

  useEffect(() => {
    if (checkoutResult !== 'cancel' || !user || !testCheckout || abandoned.current) return
    abandoned.current = true
    setBusy(true)
    void fetch('/api/billing/checkout/abandon', { method: 'POST', headers: { 'X-CSRF-Token': user.csrf_token } })
      .then(async response => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}))
          throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not close the cancelled checkout.')
        }
      }).catch(cause => setError(cause instanceof Error ? cause.message : 'Could not close the cancelled checkout.'))
      .finally(() => setBusy(false))
  }, [checkoutResult, user, testCheckout])

  useEffect(() => {
    if (!user || !testCheckout) return
    let active = true
    let poll: ReturnType<typeof setInterval> | undefined
    let stop: ReturnType<typeof setTimeout> | undefined
    async function refresh() {
      try {
        const response = await fetch('/api/billing/status')
        if (!response.ok) return
        const body = await response.json()
        if (active) {
          setBilling(body.billing ?? null)
          if (body.billing) {
            if (poll) clearInterval(poll)
            if (stop) clearTimeout(stop)
            setConfirmationTimedOut(false)
          }
        }
      } catch { /* The pricing page remains available if billing status cannot be loaded. */ }
    }
    void refresh()
    if (checkoutResult === 'success') poll = setInterval(() => void refresh(), 2000)
    if (checkoutResult === 'success') stop = setTimeout(() => {
      if (poll) clearInterval(poll)
      if (active) setConfirmationTimedOut(true)
    }, 12000)
    return () => { active = false; if (poll) clearInterval(poll); if (stop) clearTimeout(stop) }
  }, [user, testCheckout, checkoutResult])

  async function openBilling(path: 'checkout' | 'portal', plan?: string) {
    if (!user) { onLogin(); return }
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`/api/billing/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token },
        body: path === 'checkout' ? JSON.stringify({ plan }) : undefined,
      })
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not open Stripe.')
      if (typeof body.url !== 'string' || !body.url.startsWith('https://')) throw new Error('Stripe did not return a secure link.')
      window.location.assign(body.url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not open Stripe.')
      setBusy(false)
    }
  }

  async function verifyCheckout() {
    if (!user) return
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/api/billing/checkout/verify', { method: 'POST', headers: { 'X-CSRF-Token': user.csrf_token } })
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not check Stripe checkout.')
      if (body.billing) {
        setBilling(body.billing)
        setCheckoutRecovery(null)
      } else if (body.checkout === 'expired') {
        setCheckoutRecovery('expired')
      } else if (body.checkout === 'open' && typeof body.url === 'string' && body.url.startsWith('https://')) {
        setCheckoutRecovery('open')
        setCheckoutUrl(body.url)
      } else {
        setError('Stripe has not confirmed a subscription yet. Check again shortly or contact us.')
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not check Stripe checkout.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="pricing-page">
    {nav}
    <section className="pricing-intro"><h1>PAY FOR<br/>LESS <em>WASTE.</em></h1></section>
    {checkoutResult === 'success' && !billing && <p className="pricing-feedback" role="status">{checkoutRecovery === 'expired' ? 'This checkout expired. You can start another test checkout.' : checkoutRecovery === 'open' ? <>Checkout has not completed. <a href={checkoutUrl}>Resume your open checkout</a>.</> : confirmationTimedOut ? <>Stripe has not confirmed your test subscription yet. Check again or contact <a href="mailto:hello@arro.co.nz">hello@arro.co.nz</a> if it persists.</> : 'Stripe checkout returned. Your subscription status will appear here after Stripe confirms it.'}</p>}
    {checkoutResult === 'cancel' && <p className="pricing-feedback" role="status">Checkout was cancelled. No test subscription was started.</p>}
    {error && <p className="pricing-feedback" role="alert">{error}</p>}
    <section className="price-grid">{plans.map((plan, index) => <article key={plan.key} className={index === 1 ? 'featured' : ''}>
      <div className="plan-number">0{index + 1}</div><h2>{plan.name}</h2><p>{plan.description}</p>
      <strong>{plan.price === 'CUSTOM' ? plan.price : <><small>$</small>{plan.price}<small>/ MO</small></>}</strong>
      <ul>{plan.items.map(item => <li key={item}>{item}</li>)}</ul>
      {plan.key === 'enterprise' || !testCheckout ? null
        : !user ? <button onClick={onLogin}>SIGN IN TO TEST CHECKOUT <span>→</span></button>
        : user.role !== 'owner' ? <p className="billing-hint">Ask your workspace owner to manage billing.</p>
        : billing && billing.status !== 'canceled' ? <button disabled={busy} onClick={() => void openBilling('portal')}>MANAGE TEST BILLING <span>→</span></button>
        : checkoutResult === 'success' && !billing && checkoutRecovery !== 'expired' ? confirmationTimedOut
          ? <button disabled={busy} onClick={() => void verifyCheckout()}>{busy ? 'CHECKING STRIPE…' : 'CHECK STATUS AGAIN'} <span>→</span></button>
          : <p className="billing-hint">Waiting for Stripe to confirm the test subscription.</p>
        : <button disabled={busy} onClick={() => void openBilling('checkout', plan.key)}>{busy ? 'OPENING STRIPE…' : 'TEST CHECKOUT'} <span>→</span></button>}
    </article>)}</section>
  </main>
}
