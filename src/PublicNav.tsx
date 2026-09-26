export type PublicRoute = 'landing' | 'how' | 'pricing' | 'login'

export default function PublicNav({ onNavigate }: { onNavigate: (route: PublicRoute) => void }) {
  return <header className="landing-nav public-nav">
    <button className="brand" aria-label="YLD home" onClick={() => onNavigate('landing')}>YLD<span>.</span></button>
    <nav className="landing-links" aria-label="Main navigation">
      <button className="nav-home" onClick={() => onNavigate('landing')}>HOME</button>
      <button className="nav-how" onClick={() => onNavigate('how')}>HOW IT WORKS</button>
      <button className="nav-pricing" onClick={() => onNavigate('pricing')}>PRICING</button>
      <button className="nav-login" onClick={() => onNavigate('login')}>LOG IN <i>↗</i></button>
    </nav>
  </header>
}
