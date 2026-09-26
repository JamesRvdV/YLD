import React, { useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import './product.css'
import ProductDashboard from './ProductDashboard'
import PublicNav from './PublicNav'
import PricingPage from './PricingPage'
import WaitlistPrompt from './WaitlistPrompt'
import LegalPage, { LegalFooter, type LegalPage as LegalScreen } from './LegalPages'
import { AcceptInvite, AdminPage, loadSession, Login, type SessionUser } from './AuthPages'

type Screen='landing'|'how'|'pricing'|'login'|'dashboard'|'invite'|'admin'|LegalScreen
const screenForPath=():Screen=>({"/":"landing","/how-it-works":"how","/pricing":"pricing","/login":"login","/dashboard":"dashboard","/invite":"invite","/admin":"admin","/privacy":"privacy","/terms":"terms","/cookies":"cookies","/billing":"billing"}[window.location.pathname] as Screen)||'landing'
const pathForScreen:Record<Screen,string>={landing:'/',how:'/how-it-works',pricing:'/pricing',login:'/login',dashboard:'/dashboard',invite:'/invite',admin:'/admin',privacy:'/privacy',terms:'/terms',cookies:'/cookies',billing:'/billing'}


function Landing({nav,onWaitlist}:{nav:ReactNode;onWaitlist:()=>void}) {
  return <main className="landing">
    {nav}
    <section id="landing-hero" className="hero"><div className="hero-meta"><span>YLD / PREP WITH CONFIDENCE</span><span>CHRISTCHURCH · NZ</span></div><h1 className="hero-headline"><span>KNOW WHAT</span><span>TO PREP.<br/>EVERY DAY.</span></h1><aside className="hero-prep-card" aria-label="Example daily prep plan"><header><span>YLD / DAILY PREP</span><b>TOMORROW</b></header><div className="hero-prep-summary"><span>EXPECTED COVERS</span><strong>84</strong></div><ul><li><i>✓</i><span>BEEF BURGERS</span><b>36</b></li><li><i>✓</i><span>CHICKEN SALAD</span><b>22</b></li><li><i>✓</i><span>FISH TACOS</span><b>28</b></li><li><i>✓</i><span>CHIPS</span><b>42</b></li></ul><footer><span>PORTIONS TO PREP</span><b>YLD.</b></footer></aside><div className="hero-bottom"><p>Built on your sales,<br/>covers, and actuals.</p><button className="hero-cta" onClick={onWaitlist}>JOIN THE WAITLIST <span>↗</span></button></div></section>
    <section className="landing-problem"><div className="problem-copy"><span>THE PROBLEM</span><h2>Prep is too costly<br/>to <em>guess.</em></h2><p>New Zealand cafés and restaurants lose an estimated $58m a year to avoidable food waste. YLD turns your service history into a clear prep call before the first order lands.</p></div><div className="problem-stats"><article><b>$58M</b><p>estimated annual cost of avoidable food waste to New Zealand cafés and restaurants.</p></article><article><b>61%</b><p>of food waste in New Zealand cafés and restaurants is avoidable.</p></article></div></section>
    <section className="flagship"><div className="flagship-copy"><span>YOUR DAILY PREP PLAN</span><h2>How we<br/>solve <em>that.</em></h2><p>YLD combines your covers and sales history into recommended prep quantities. After service, log what happened and the next plan gets sharper.</p><button onClick={onWaitlist}>JOIN THE WAITLIST <i>→</i></button></div><div className="prep-preview"><div className="preview-top"><span>YLD / SERVICE LOOP</span><b>HOW IT WORKS</b></div><div className="preview-row"><span>UPLOAD HISTORY</span><strong>01</strong><i>→</i></div><div className="preview-row"><span>GET PREP QUANTITIES</span><strong>02</strong><i>→</i></div><div className="preview-row"><span>LOG ACTUALS</span><strong>03</strong><i>→</i></div><div className="preview-row"><span>MODEL RELEARNS</span><strong>04</strong><i>↺</i></div><div className="preview-footer"><span>EACH SERVICE SHARPENS THE NEXT</span><b>YLD.</b></div></div></section>
    <section className="statement service-intro" id="how"><div className="section-index">( 02 )<br/>THE AGENT LOOP</div><div className="statement-copy"><h2>How our<br/><em>agent works.</em></h2><p>YLD turns your service history into a prep plan, then closes the loop with an end-of-service summary of what actually happened.</p></div><div className="step-grid"><article><b>01</b><div><h3>UPLOAD SALES DATA</h3><p>Import a CSV of past services, including dishes sold and covers.</p></div><i>→</i></article><article><b>02</b><div><h3>GET YOUR PREP PLAN</h3><p>The agent recommends portions for every dish before prep begins.</p></div><i>→</i></article><article><b>03</b><div><h3>LOG THE SERVICE</h3><p>Capture what was prepared, sold, and left over once service is done.</p></div><i>→</i></article><article><b>04</b><div><h3>REVIEW THE SUMMARY</h3><p>See the plan versus actuals, then use that feedback for tomorrow.</p></div><i>↺</i></article></div></section>
    <section className="numbers dynamic-numbers" id="numbers"><div className="impact-card"><span>ONE PLAN · EVERY SERVICE</span><strong><em>YLD</em>.</strong><p>Your kitchen data stays at the centre: import service history, get a prep plan, then teach it with actuals.</p></div><div className="numbers-note"><span>OPENING WITH A SMALL GROUP OF KITCHENS</span><h2>Make tomorrow<br/><em>less uncertain.</em></h2></div></section>
    <WaitlistPrompt eyebrow="READY FOR A CLEARER PREP PLAN?" title={<>MAKE THE<br/>BETTER CALL.</>} onWaitlist={onWaitlist} />
  </main>
}

type FlowIconName = 'upload' | 'plan' | 'log' | 'learn'

function FlowIcon({ name }: { name: FlowIconName }) {
  const paths: Record<FlowIconName, ReactNode> = {
    upload: <><path d="M12 16V3m0 0L7.5 7.5M12 3l4.5 4.5M5 14v6h14v-6" /></>,
    plan: <><path d="M4 16h16M6 16v2h12v-2M7 15a5 5 0 0 1 10 0M12 10V7M10 7h4" /></>,
    log: <><path d="M5 20V4M5 20h15M9 16v-5M13 16V7M17 16v-8" /></>,
    learn: <><><path d="M19 9a7 7 0 0 0-12.1-2.8L5 8m0-4v4h4" /><path d="M5 15a7 7 0 0 0 12.1 2.8L19 16m0 4v-4h-4" /></></>,
  }
  return <span className="how-flow-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" strokeLinejoin="miter">{paths[name]}</svg></span>
}

export function HowItWorks({nav,onWaitlist}:{nav:ReactNode;onWaitlist:()=>void}) {
  const steps = [
    { number: '01', phase: 'INPUT', icon: 'upload' as const, title: 'UPLOAD HISTORY', copy: 'Import a CSV of past services: dishes sold, covers, and optional prep and cost data.' },
    { number: '02', phase: 'DECISION', icon: 'plan' as const, title: 'GET PREP QUANTITIES', copy: 'YLD recommends how many portions of each dish to prepare for tomorrow, balancing expected demand and waste.' },
    { number: '03', phase: 'FEEDBACK', icon: 'log' as const, title: 'LOG ACTUALS', copy: 'Record covers, prepared, and sold after service.' },
    { number: '04', phase: 'LEARNING', icon: 'learn' as const, title: 'MODEL RELEARNS', copy: 'YLD refits each dish’s demand forecast using the latest sales and covers for the next plan.' },
  ]
  return <main className="how-page">
    {nav}
    <section className="how-intro"><h1>A BETTER CALL,<br/>BEFORE <em>SERVICE.</em></h1></section>
    <section className="how-flow" aria-label="How YLD works">
      <ol>{steps.map((step, index) => <li key={step.number}>
        <div className="how-flow-meta"><span>{step.number}</span><span>{step.phase}</span></div>
        <FlowIcon name={step.icon} />
        <div className="how-flow-copy"><h2>{step.title}</h2><p>{step.copy}</p></div>
        {index < steps.length - 1 && <span className="how-flow-arrow" aria-hidden="true">→</span>}
      </li>)}</ol>
      <p className="how-flow-loop"><span aria-hidden="true">↺</span> EACH LOGGED SERVICE UPDATES THE NEXT FORECAST</p>
    </section>
    <WaitlistPrompt eyebrow="LESS GUESSING AT THE PASS. MORE FOCUS IN THE KITCHEN." title={<>MAKE THE<br/>BETTER CALL.</>} onWaitlist={onWaitlist} />
  </main>
}

function WaitlistDialog({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'sending' | 'done'>('idle')
  const [error, setError] = useState('')
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setStatus('sending'); setError('')
    try {
      const response = await fetch('/api/waitlist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'We could not save your place. Please try again.')
      setStatus('done')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'We could not save your place. Please try again.'); setStatus('idle') }
  }
  return <div className="waitlist-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="waitlist-dialog" role="dialog" aria-modal="true" aria-labelledby="waitlist-title">
      <button className="waitlist-close" type="button" aria-label="Close waitlist form" onClick={onClose}>×</button>
      {status === 'done' ? <><span>YOU'RE ON THE LIST</span><h2 id="waitlist-title">WE'LL BE IN<br/><em>TOUCH.</em></h2><p>Thanks for your interest in YLD. We’ll be in touch when early access opens.</p><button className="waitlist-submit" type="button" onClick={onClose}>CLOSE <span>→</span></button></> : <><span>NOW ONBOARDING EARLY KITCHENS</span><h2 id="waitlist-title">JOIN THE<br/><em>WAITLIST.</em></h2><p>Get early access to a clearer daily prep plan.</p><form onSubmit={event => void submit(event)}><label>EMAIL ADDRESS<input required autoComplete="email" placeholder="you@kitchen.co.nz" type="email" value={email} onChange={event => setEmail(event.target.value)} /></label>{error && <p className="waitlist-error" role="alert">{error}</p>}<button className="waitlist-submit" disabled={status === 'sending'}>{status === 'sending' ? 'JOINING…' : 'JOIN WAITLIST'} <span>→</span></button></form><p className="waitlist-privacy">No spam. Just early access updates. Read our <a href="/privacy">Privacy policy</a>.</p></>}
    </section>
  </div>
}

function App() {
  const [screen, setScreen] = useState<Screen>(screenForPath)
  const [user, setUser] = useState<SessionUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [showWaitlist, setShowWaitlist] = useState(false)

  const go = (next: Screen) => {
    window.history.pushState({}, '', pathForScreen[next])
    setScreen(next)
    window.scrollTo(0, 0)
  }

  useEffect(() => {
    const sync = () => setScreen(screenForPath())
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])

  useEffect(() => {
    let active = true
    void loadSession().then(found => { if (active) setUser(found) }).finally(() => { if (active) setCheckingSession(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!checkingSession && !user && (screen === 'dashboard' || screen === 'admin')) {
      window.history.replaceState({}, '', '/login')
      setScreen('login')
    }
  }, [checkingSession, user, screen])

  async function signOut() {
    if (user) {
      try {
        const response = await fetch('/api/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': user.csrf_token } })
        if (!response.ok) throw new Error('Sign-out failed')
      } catch {
        window.alert('Could not sign out. Check your connection and try again.')
        return
      }
    }
    setUser(null)
    go('landing')
  }

  const publicNav = <PublicNav onNavigate={route => go(route)} onWaitlist={() => setShowWaitlist(true)} />
  const publicPage = (page: ReactNode) => <>{page}{showWaitlist && <WaitlistDialog onClose={() => setShowWaitlist(false)} />}</>

  if (checkingSession && (screen === 'dashboard' || screen === 'login' || screen === 'invite' || screen === 'admin')) return <div className="auth-loading">OPENING YLD…</div>

  if (screen === 'landing') return publicPage(<><Landing nav={publicNav} onWaitlist={() => setShowWaitlist(true)} /><LegalFooter /></>)
  if (screen === 'how') return publicPage(<><HowItWorks nav={publicNav} onWaitlist={() => setShowWaitlist(true)} /><LegalFooter /></>)
  if (screen === 'pricing') return publicPage(<><PricingPage nav={publicNav} onLogin={() => go(user ? 'dashboard' : 'login')} onWaitlist={() => setShowWaitlist(true)} user={user} /><LegalFooter /></>)
  if (screen === 'login') return publicPage(<div className="public-auth-shell">{publicNav}<Login onBack={() => go('landing')} onOpen={() => go('dashboard')} onSignedIn={found => { setUser(found); go('dashboard') }} user={user} /><LegalFooter /></div>)
  if (screen === 'invite') return <div className="public-auth-shell">{publicNav}<AcceptInvite onDone={found => { setUser(found); window.history.replaceState({}, '', '/dashboard'); setScreen('dashboard') }} /><LegalFooter /></div>
  if (screen === 'admin') return user?.is_admin ? <><AdminPage user={user} onBack={() => go('dashboard')} /><LegalFooter /></> : <><Login onBack={() => go('landing')} onOpen={() => go('dashboard')} onSignedIn={found => { setUser(found); go('dashboard') }} user={user} /><LegalFooter /></>
  if (screen === 'privacy' || screen === 'terms' || screen === 'cookies' || screen === 'billing') return publicPage(<LegalPage page={screen} nav={publicNav} />)
  if (!user) return <><Login onBack={() => go('landing')} onOpen={() => go('dashboard')} onSignedIn={found => { setUser(found); go('dashboard') }} user={null} /><LegalFooter /></>
  return <ProductDashboard user={user} onSignOut={() => void signOut()} onAuthLost={() => { setUser(null); window.history.replaceState({}, '', '/login'); setScreen('login') }} />
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
