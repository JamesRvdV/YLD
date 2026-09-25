import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import './product.css'
import ProductDashboard from './ProductDashboard'
import LegalPage, { LegalFooter, type LegalPage as LegalScreen } from './LegalPages'
import { AcceptInvite, loadSession, Login, type SessionUser } from './AuthPages'

type Screen='landing'|'how'|'pricing'|'login'|'dashboard'|'invite'|LegalScreen
const screenForPath=():Screen=>({"/":"landing","/how-it-works":"how","/pricing":"pricing","/login":"login","/dashboard":"dashboard","/invite":"invite","/privacy":"privacy","/terms":"terms","/cookies":"cookies","/billing":"billing"}[window.location.pathname] as Screen)||'landing'
const pathForScreen:Record<Screen,string>={landing:'/',how:'/how-it-works',pricing:'/pricing',login:'/login',dashboard:'/dashboard',invite:'/invite',privacy:'/privacy',terms:'/terms',cookies:'/cookies',billing:'/billing'}


function Landing({onLogin,onPricing,onHow}:{onLogin:()=>void;onPricing:()=>void;onHow:()=>void}) {
  return <main className="landing">
    <header className="landing-nav"><button className="brand" onClick={()=>window.scrollTo({top:0,behavior:'smooth'})}>YLD<span>.</span></button><div className="landing-links"><button className="nav-how" onClick={onHow}>HOW IT WORKS</button><button className="nav-pricing" onClick={onPricing}>PRICING</button><button onClick={onLogin}>LOG IN <i>↗</i></button></div></header>
    <section id="landing-hero" className="hero"><div className="hero-meta"><span>YLD / REDUCE YOUR WASTE</span><span>CHRISTCHURCH · NZ</span></div><h1 className="hero-headline"><span>FOOD WASTE</span><span>AT THE END<br/>OF THE DAY?</span></h1><div className="hero-bottom"><p>Built from every service.<br/>Better with every actual.</p><button className="hero-cta" onClick={onLogin}>LOGIN <span>↗</span></button></div></section>
    <section className="landing-problem"><div><span>THE PROBLEM</span><h2>Every service starts<br/>with a <em>guess.</em></h2><p>Over-prep ties up money and leaves food behind. Under-prep means missed plates at the pass. Most kitchens only learn which call was wrong once the service is over.</p></div><div className="problem-stats"><article><b>1</b><p>wrong prep call can affect every section on the menu.</p></article><article><b>0</b><p>clear signals when yesterday's sales are still in a spreadsheet.</p></article></div></section>
    <section className="flagship"><div className="flagship-copy"><span>INTRODUCING THE PREP ENGINE</span><h2>Make the call<br/>before <em>service.</em></h2><p>YLD turns covers, sales history, and the shape of the night into a clear prep plan for every dish. Upload your service history to build a plan from your own kitchen data.</p><button onClick={onLogin}>OPEN A PREP PLAN <i>→</i></button></div><div className="prep-preview"><div className="preview-top"><span>YOUR SERVICE HISTORY</span><b>HOW IT WORKS</b></div><div className="preview-row"><span>UPLOAD SALES CSV</span><strong>01</strong><i>→</i></div><div className="preview-row"><span>REVIEW MENU COSTS</span><strong>02</strong><i>→</i></div><div className="preview-row"><span>BUILD TOMORROW’S PLAN</span><strong>03</strong><i>→</i></div><div className="preview-footer"><span>BASED ON YOUR DATA</span><b>YLD.</b></div></div></section>
    <section className="statement service-intro" id="how"><div className="section-index">( 02 )</div><div className="statement-copy"><h2>Good service starts<br/>before <em>service.</em></h2><p>Plan portions around real demand, not a hunch. YLD gives your kitchen one clear call for every dish.</p></div><div className="step-grid"><article><b>01</b><div><h3>SET THE ROOM</h3><p>Tell YLD your covers and the kind of night you expect.</p></div><i>↘</i></article><article><b>02</b><div><h3>MAKE THE CALL</h3><p>Get a quantified prep plan balanced for sales and waste.</p></div><i>↘</i></article><article><b>03</b><div><h3>GET SHARPER</h3><p>Log actuals. Every service makes the next plan better.</p></div><i>↘</i></article></div></section>
    <section className="numbers dynamic-numbers" id="numbers"><div className="impact-card"><span>FROM YOUR SERVICES</span><strong><em>YLD</em>.</strong><p>Upload your service history, add per-portion costs, and use the resulting plan for your next service.</p></div><div className="numbers-note"><span>ONE PLAN · EVERY SERVICE</span><h2>Keep your<br/><em>kitchen moving.</em></h2><button className="underline-button" onClick={onLogin}>OPEN YOUR DASHBOARD <i>→</i></button></div></section>
    <section className="landing-close"><span>READY FOR TOMORROW'S SERVICE?</span><div><h2>MAKE THE<br/>BETTER CALL.</h2><button onClick={onLogin}>OPEN YOUR PREP PLAN <span>↗</span></button></div></section>
  </main>
}

function HowItWorks({onBack,onLogin,onPricing}:{onBack:()=>void;onLogin:()=>void;onPricing:()=>void}){const steps=[['01','SET THE ROOM','Start with your covers and tell YLD whether service looks quiet, normal, or busy.'],['02','MAKE THE CALL','YLD reads your historical sales and gives every dish a clear prep quantity.'],['03','LOG THE ACTUAL','Record what you made and sold. YLD improves for the next service.']];return <main className="how-page"><header className="pricing-nav"><button className="brand" onClick={onBack}>YLD<span>.</span></button><div><button onClick={onPricing}>PRICING</button><button onClick={onLogin}>LOG IN ↗</button></div></header><section className="how-intro"><span>( HOW IT WORKS )</span><h1>A BETTER CALL,<br/>BEFORE <em>SERVICE.</em></h1><p>A simple three-step system for calm, confident prep.</p></section><section className="how-steps">{steps.map(([number,title,copy])=><article key={number}><span>{number}</span><h2>{title}</h2><p>{copy}</p><b>→</b></article>)}</section><section className="how-close"><p>Less guessing at the pass. More focus in the kitchen.</p><button onClick={onLogin}>OPEN YOUR PLAN <span>→</span></button></section></main>}

function Pricing({onBack,onLogin}:{onBack:()=>void;onLogin:()=>void}){const plans=[['SERVICE','49','Proposed for one focused kitchen.','Daily prep plans','Demand adjustments','Actuals logging'],['KITCHEN','119','Proposed for a team running every service.','Everything in Service','Unlimited team members','Weekly performance view'],['GROUP','CUSTOM','Proposed for operators with more than one room.','Everything in Kitchen','Multi-site view','Dedicated onboarding']];return <main className="pricing-page"><header className="pricing-nav"><button className="brand" onClick={onBack}>YLD<span>.</span></button><div><button onClick={onBack}>HOME</button><button onClick={onLogin}>LOG IN ↗</button></div></header><section className="pricing-intro"><span>( PROPOSED PRICING / NZD )</span><h1>PAY FOR<br/>LESS <em>WASTE.</em></h1><p>These plans are a preview. YLD is currently an invite-only pilot; online subscriptions and trials are not available yet.</p></section><section className="price-grid">{plans.map(([name,price,description,...items],index)=><article key={name} className={index===1?'featured':''}><div className="plan-number">0{index+1}</div><h2>{name}</h2><p>{description}</p><strong>{price==='CUSTOM'?price:<><small>$</small>{price}<small>/ MO</small></>}</strong><ul>{items.map(item=><li key={item}>{item}</li>)}</ul><button onClick={onLogin}>INVITED? SIGN IN <span>→</span></button></article>)}</section><section className="pricing-note"><span>NO PAYMENT TAKEN</span><p>Prices and features may change before launch. See our <a href="/billing">billing policy</a> for the current status.</p></section></main>}

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
    if (!checkingSession && !user && screen === 'dashboard') {
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

  if (checkingSession && (screen === 'dashboard' || screen === 'login' || screen === 'invite')) return <div className="auth-loading">OPENING YLD…</div>

  if (screen === 'landing') return <><Landing onLogin={() => go('login')} onPricing={() => go('pricing')} onHow={() => go('how')} /><LegalFooter /></>
  if (screen === 'how') return <><HowItWorks onBack={() => go('landing')} onPricing={() => go('pricing')} onLogin={() => go('login')} /><LegalFooter /></>
  if (screen === 'pricing') return <><Pricing onBack={() => go('landing')} onLogin={() => go('login')} /><LegalFooter /></>
  if (screen === 'login') return <><Login onBack={() => go('landing')} onOpen={() => go('dashboard')} user={user} /><LegalFooter /></>
  if (screen === 'invite') return <><AcceptInvite onDone={found => { setUser(found); window.history.replaceState({}, '', '/dashboard'); setScreen('dashboard') }} /><LegalFooter /></>
  if (screen === 'privacy' || screen === 'terms' || screen === 'cookies' || screen === 'billing') return <LegalPage page={screen} />
  if (!user) return <><Login onBack={() => go('landing')} onOpen={() => go('dashboard')} user={null} /><LegalFooter /></>
  return <ProductDashboard user={user} onSignOut={() => void signOut()} onAuthLost={() => { setUser(null); window.history.replaceState({}, '', '/login'); setScreen('login') }} />
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
