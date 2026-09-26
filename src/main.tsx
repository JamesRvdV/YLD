import React, { useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import './product.css'
import ProductDashboard from './ProductDashboard'
import PublicNav from './PublicNav'
import PricingPage from './PricingPage'
import LegalPage, { LegalFooter, type LegalPage as LegalScreen } from './LegalPages'
import { AcceptInvite, AdminPage, loadSession, Login, type SessionUser } from './AuthPages'

type Screen='landing'|'how'|'pricing'|'login'|'dashboard'|'invite'|'admin'|LegalScreen
const screenForPath=():Screen=>({"/":"landing","/how-it-works":"how","/pricing":"pricing","/login":"login","/dashboard":"dashboard","/invite":"invite","/admin":"admin","/privacy":"privacy","/terms":"terms","/cookies":"cookies","/billing":"billing"}[window.location.pathname] as Screen)||'landing'
const pathForScreen:Record<Screen,string>={landing:'/',how:'/how-it-works',pricing:'/pricing',login:'/login',dashboard:'/dashboard',invite:'/invite',admin:'/admin',privacy:'/privacy',terms:'/terms',cookies:'/cookies',billing:'/billing'}


function Landing({nav,onLogin}:{nav:ReactNode;onLogin:()=>void}) {
  return <main className="landing">
    {nav}
    <section id="landing-hero" className="hero"><div className="hero-meta"><span>YLD / REDUCE YOUR WASTE</span><span>CHRISTCHURCH · NZ</span></div><h1 className="hero-headline"><span>FOOD WASTE</span><span>AT THE END<br/>OF THE DAY?</span></h1><div className="hero-bottom"><p>Built from every service.<br/>Better with every actual.</p><button className="hero-cta" onClick={onLogin}>LOGIN <span>↗</span></button></div></section>
    <section className="landing-problem"><div><span>THE PROBLEM</span><h2>Every service starts<br/>with a <em>guess.</em></h2><p>Over-prep ties up money and leaves food behind. Under-prep means missed plates at the pass. Most kitchens only learn which call was wrong once the service is over.</p></div><div className="problem-stats"><article><b>1</b><p>wrong prep call can affect every section on the menu.</p></article><article><b>0</b><p>clear signals when yesterday's sales are still in a spreadsheet.</p></article></div></section>
    <section className="flagship"><div className="flagship-copy"><span>INTRODUCING THE PREP ENGINE</span><h2>Make the call<br/>before <em>service.</em></h2><p>YLD turns covers, sales history, and the shape of the night into a clear prep plan for every dish. Upload your service history to build a plan from your own kitchen data.</p><button onClick={onLogin}>OPEN A PREP PLAN <i>→</i></button></div><div className="prep-preview"><div className="preview-top"><span>YLD / SERVICE LOOP</span><b>HOW IT WORKS</b></div><div className="preview-row"><span>UPLOAD HISTORY</span><strong>01</strong><i>→</i></div><div className="preview-row"><span>GET PREP QUANTITIES</span><strong>02</strong><i>→</i></div><div className="preview-row"><span>LOG ACTUALS</span><strong>03</strong><i>→</i></div><div className="preview-row"><span>MODEL RELEARNS</span><strong>04</strong><i>↺</i></div><div className="preview-footer"><span>EACH SERVICE SHARPENS THE NEXT</span><b>YLD.</b></div></div></section>
    <section className="statement service-intro" id="how"><div className="section-index">( 02 )</div><div className="statement-copy"><h2>Good service starts<br/>before <em>service.</em></h2><p>Plan portions around real demand, not a hunch. YLD gives your kitchen one clear call for every dish.</p></div><div className="step-grid"><article><b>01</b><div><h3>UPLOAD HISTORY</h3><p>Import past sales and covers from your service CSV.</p></div><i>↘</i></article><article><b>02</b><div><h3>GET PREP QUANTITIES</h3><p>See how many portions of each dish to prepare.</p></div><i>↘</i></article><article><b>03</b><div><h3>LOG ACTUALS</h3><p>Record covers, prepared portions, and sales after service.</p></div><i>↘</i></article><article><b>04</b><div><h3>MODEL RELEARNS</h3><p>New sales and covers update the next forecast.</p></div><i>↺</i></article></div></section>
    <section className="numbers dynamic-numbers" id="numbers"><div className="impact-card"><span>FROM YOUR SERVICES</span><strong><em>YLD</em>.</strong><p>Upload your service history, add per-portion costs, and use the resulting plan for your next service.</p></div><div className="numbers-note"><span>ONE PLAN · EVERY SERVICE</span><h2>Keep your<br/><em>kitchen moving.</em></h2><button className="underline-button" onClick={onLogin}>OPEN YOUR DASHBOARD <i>→</i></button></div></section>
    <section className="landing-close"><span>READY FOR TOMORROW'S SERVICE?</span><div><h2>MAKE THE<br/>BETTER CALL.</h2><button onClick={onLogin}>OPEN YOUR PREP PLAN <span>↗</span></button></div></section>
  </main>
}

function HowItWorks({nav,onLogin}:{nav:ReactNode;onLogin:()=>void}) {
  const steps = [
    { number: '01', phase: 'INPUT', title: 'UPLOAD HISTORY', copy: 'Import a CSV of past services: dishes sold, covers, and optional prep and cost data.' },
    { number: '02', phase: 'DECISION', title: 'GET PREP QUANTITIES', copy: 'YLD recommends how many portions of each dish to prepare for tomorrow, balancing expected demand and waste.' },
    { number: '03', phase: 'FEEDBACK', title: 'LOG ACTUALS', copy: 'Record covers, prepared, and sold after service.' },
    { number: '04', phase: 'LEARNING', title: 'MODEL RELEARNS', copy: 'YLD refits each dish’s demand forecast using the latest sales and covers for the next plan.' },
  ]
  return <main className="how-page">
    {nav}
    <section className="how-intro"><h1>A BETTER CALL,<br/>BEFORE <em>SERVICE.</em></h1></section>
    <section className="how-flow" aria-label="How YLD works">
      <ol>{steps.map((step, index) => <li key={step.number}>
        <div className="how-flow-meta"><span>{step.number}</span><span>{step.phase}</span></div>
        <div className="how-flow-copy"><h2>{step.title}</h2><p>{step.copy}</p></div>
        {index < steps.length - 1 && <span className="how-flow-arrow" aria-hidden="true">→</span>}
      </li>)}</ol>
      <p className="how-flow-loop"><span aria-hidden="true">↺</span> EACH LOGGED SERVICE UPDATES THE NEXT FORECAST</p>
    </section>
    <section className="how-close"><p>Less guessing at the pass. More focus in the kitchen.</p><button onClick={onLogin}>OPEN YOUR PLAN <span>→</span></button></section>
  </main>
}

function App() {
  const [screen, setScreen] = useState<Screen>(screenForPath)
  const [user, setUser] = useState<SessionUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)

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

  const publicNav = <PublicNav onNavigate={route => go(route)} />

  if (checkingSession && (screen === 'dashboard' || screen === 'login' || screen === 'invite' || screen === 'admin')) return <div className="auth-loading">OPENING YLD…</div>

  if (screen === 'landing') return <><Landing nav={publicNav} onLogin={() => go('login')} /><LegalFooter /></>
  if (screen === 'how') return <><HowItWorks nav={publicNav} onLogin={() => go('login')} /><LegalFooter /></>
  if (screen === 'pricing') return <><PricingPage nav={publicNav} onLogin={() => go(user ? 'dashboard' : 'login')} user={user} /><LegalFooter /></>
  if (screen === 'login') return <div className="public-auth-shell">{publicNav}<Login onBack={() => go('landing')} onOpen={() => go('dashboard')} onSignedIn={found => { setUser(found); go('dashboard') }} user={user} /><LegalFooter /></div>
  if (screen === 'invite') return <div className="public-auth-shell">{publicNav}<AcceptInvite onDone={found => { setUser(found); window.history.replaceState({}, '', '/dashboard'); setScreen('dashboard') }} /><LegalFooter /></div>
  if (screen === 'admin') return user?.is_admin ? <><AdminPage user={user} onBack={() => go('dashboard')} /><LegalFooter /></> : <><Login onBack={() => go('landing')} onOpen={() => go('dashboard')} onSignedIn={found => { setUser(found); go('dashboard') }} user={user} /><LegalFooter /></>
  if (screen === 'privacy' || screen === 'terms' || screen === 'cookies' || screen === 'billing') return <LegalPage page={screen} nav={publicNav} />
  if (!user) return <><Login onBack={() => go('landing')} onOpen={() => go('dashboard')} onSignedIn={found => { setUser(found); go('dashboard') }} user={null} /><LegalFooter /></>
  return <ProductDashboard user={user} onAdmin={() => go('admin')} onSignOut={() => void signOut()} onAuthLost={() => { setUser(null); window.history.replaceState({}, '', '/login'); setScreen('login') }} />
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
