import { FormEvent, useEffect, useRef, useState } from 'react'

export type SessionUser = {
  id: string
  email: string
  name: string
  role: 'owner' | 'member'
  workspace_id: string
  workspace_name: string
  csrf_token: string
  data_mode: 'sample' | 'imported'
}

export async function loadSession(): Promise<SessionUser | null> {
  try {
    const response = await fetch('/api/auth/me', { credentials: 'same-origin' })
    if (!response.ok) return null
    const body = await response.json()
    return body.user as SessionUser
  } catch {
    return null
  }
}

export function Login({ onBack, onOpen, user }: { onBack: () => void; onOpen: () => void; user: SessionUser | null }) {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSending(true)
    setError('')
    setMessage('')
    try {
      const response = await fetch('/api/auth/request-link', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) })
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not send a link.')
      setMessage(body.message)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not send a link.')
    } finally {
      setSending(false)
    }
  }

  return <main className="auth-page"><button className="auth-brand" onClick={onBack}>YLD<span>.</span></button><div className="auth-card"><div className="auth-kicker">PRIVATE KITCHEN ACCESS</div><h1>MAKE A<br/><em>better call.</em></h1><p>{user ? `You're signed in to ${user.workspace_name}.` : 'Enter the email address that received your YLD invitation. We’ll send a one-use sign-in link.'}</p>{user ? <button className="auth-submit" onClick={onOpen}>OPEN YOUR KITCHEN <span>→</span></button> : <form onSubmit={event => void submit(event)}><label>EMAIL ADDRESS<input required autoComplete="email" type="email" value={email} onChange={event => setEmail(event.target.value)} /></label>{error && <div className="error" role="alert">{error}</div>}{message && <div className="auth-feedback" role="status">{message}</div>}<button className="auth-submit" disabled={sending}>{sending ? 'SENDING…' : 'EMAIL ME A LINK'} <span>→</span></button></form>}<p className="auth-legal">Access is by invitation. See our <a href="/privacy">Privacy policy</a> and <a href="/terms">Terms of use</a>.</p><button className="back-link" onClick={onBack}>← BACK TO YLD</button></div><div className="auth-aside"><p>PREP WITH<br/><em> PURPOSE.</em></p><span>YLD / 2026</span></div></main>
}

export function AcceptInvite({ onDone }: { onDone: (user: SessionUser) => void }) {
  const [error, setError] = useState('')
  const redeeming = useRef<Promise<SessionUser> | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  useEffect(() => {
    if (!redeeming.current) {
      const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
      if (!token) { setError('This invitation link is incomplete.'); return }
      window.history.replaceState({}, '', '/invite')
      redeeming.current = (async () => {
        const response = await fetch('/api/auth/redeem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) })
        const body = await response.json()
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not open this link.')
        const user = await loadSession()
        if (!user) throw new Error('Your session could not be started. Please request a new link.')
        return user
      })()
    }
    let active = true
    void redeeming.current.then(user => { if (active) onDoneRef.current(user) }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : 'Could not open this link.')
    })
    return () => { active = false }
  }, [])
  return <main className="auth-page"><a className="auth-brand" href="/">YLD<span>.</span></a><div className="auth-card"><div className="auth-kicker">YOUR INVITATION</div><h1>WELCOME<br/><em>to YLD.</em></h1><p role={error ? 'alert' : 'status'}>{error || 'Opening your private kitchen…'}</p>{error && <a className="auth-submit auth-link-button" href="/login">REQUEST A NEW LINK <span>→</span></a>}</div><div className="auth-aside"><p>PREP WITH<br/><em> PURPOSE.</em></p><span>YLD / 2026</span></div></main>
}
