import { FormEvent, useEffect, useState } from 'react'

export type SessionUser = {
  id: string
  email: string
  name: string
  role: 'owner' | 'member'
  workspace_id: string
  workspace_name: string
  csrf_token: string
  data_mode: 'empty' | 'imported'
  is_admin: boolean
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

async function responseError(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}))
  return typeof body.detail === 'string' ? body.detail : fallback
}

export function Login({ onBack, onOpen, onSignedIn, user }: { onBack: () => void; onOpen: () => void; onSignedIn: (user: SessionUser) => void; user: SessionUser | null }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSending(true)
    setError('')
    try {
      const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
      if (!response.ok) throw new Error(await responseError(response, 'Could not sign in.'))
      const found = await loadSession()
      if (!found) throw new Error('Your session could not be started. Please try again.')
      onSignedIn(found)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in.')
    } finally {
      setSending(false)
    }
  }

  return <main className="auth-page public-auth-page"><div className="auth-card"><div className="auth-kicker">PRIVATE KITCHEN ACCESS</div><h1>MAKE A<br/><em>better call.</em></h1><p>{user ? `You're signed in to ${user.workspace_name}.` : 'Sign in with the email address and password you set when you accepted your invitation.'}</p>{user ? <><button className="auth-submit" onClick={onOpen}>OPEN YOUR KITCHEN <span>→</span></button>{user.is_admin && <a className="auth-admin-link" href="/admin">ADMIN INVITATIONS →</a>}</> : <form onSubmit={event => void submit(event)}><label>EMAIL ADDRESS<input required autoComplete="username" type="email" value={email} onChange={event => setEmail(event.target.value)} /></label><label>PASSWORD<input required autoComplete="current-password" type="password" value={password} onChange={event => setPassword(event.target.value)} /></label>{error && <div className="error" role="alert">{error}</div>}<button className="auth-submit" disabled={sending}>{sending ? 'SIGNING IN…' : 'SIGN IN'} <span>→</span></button></form>}<p className="auth-legal">Access is by invitation. Need a password setup link? Contact us at <a href="mailto:hello@yld.co.nz">hello@yld.co.nz</a>. See our <a href="/privacy">Privacy policy</a> and <a href="/terms">Terms of use</a>.</p><button className="back-link" onClick={onBack}>← BACK TO YLD</button></div><div className="auth-aside"><p>PREP WITH<br/><em> PURPOSE.</em></p><span>YLD / 2026</span></div></main>
}

export function AcceptInvite({ onDone }: { onDone: (user: SessionUser) => void }) {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token'))
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => { window.history.replaceState({}, '', '/invite') }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirm) { setError('Passwords do not match.'); return }
    if (!token) { setError('This invitation link is incomplete.'); return }
    setSending(true)
    setError('')
    try {
      const response = await fetch('/api/auth/redeem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, password }) })
      if (!response.ok) throw new Error(await responseError(response, 'Could not open this link.'))
      const user = await loadSession()
      if (!user) throw new Error('Your session could not be started. Please sign in.')
      onDone(user)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not open this link.')
    } finally {
      setSending(false)
    }
  }

  return <main className="auth-page public-auth-page"><div className="auth-card"><div className="auth-kicker">YOUR INVITATION</div><h1>WELCOME<br/><em>to YLD.</em></h1><p>Set a password to access your private kitchen. Use at least 12 characters.</p>{token ? <form onSubmit={event => void submit(event)}><label>NEW PASSWORD<input required minLength={12} maxLength={256} autoComplete="new-password" type="password" value={password} onChange={event => setPassword(event.target.value)} /></label><label>CONFIRM PASSWORD<input required minLength={12} maxLength={256} autoComplete="new-password" type="password" value={confirm} onChange={event => setConfirm(event.target.value)} /></label>{error && <div className="error" role="alert">{error}</div>}<button className="auth-submit" disabled={sending}>{sending ? 'SETTING PASSWORD…' : 'SET PASSWORD'} <span>→</span></button></form> : <p role="alert">This invitation link is incomplete.</p>}<p className="auth-legal">This invitation works once and expires after 48 hours. Need a new invitation? Contact us at <a href="mailto:hello@yld.co.nz">hello@yld.co.nz</a>.</p></div><div className="auth-aside"><p>PREP WITH<br/><em> PURPOSE.</em></p><span>YLD / 2026</span></div></main>
}

type Workspace = { id: string; name: string }

export function AdminPage({ user, onBack }: { user: SessionUser; onBack: () => void }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [email, setEmail] = useState('')
  const [workspaceName, setWorkspaceName] = useState('')
  const [workspaceId, setWorkspaceId] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    let active = true
    void fetch('/api/admin/workspaces').then(async response => {
      if (!response.ok) throw new Error(await responseError(response, 'Could not load workspaces.'))
      return response.json()
    }).then(body => { if (active) setWorkspaces(body.workspaces) }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load workspaces.') })
    return () => { active = false }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSending(true)
    setError('')
    setMessage('')
    try {
      const response = await fetch('/api/admin/invitations', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token }, body: JSON.stringify({ email, ...(mode === 'new' ? { workspace_name: workspaceName } : { workspace_id: workspaceId }) }) })
      if (!response.ok) throw new Error(await responseError(response, 'Could not send invitation.'))
      setMessage(`Invitation sent to ${email.trim().toLowerCase()}.`)
      setEmail('')
      if (mode === 'new') {
        setWorkspaceName('')
        const list = await fetch('/api/admin/workspaces').then(response => response.json())
        setWorkspaces(list.workspaces)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not send invitation.')
    } finally {
      setSending(false)
    }
  }

  return <main className="auth-page"><button className="auth-brand" onClick={onBack}>YLD<span>.</span></button><div className="auth-card"><div className="auth-kicker">ADMIN / INVITATIONS</div><h1>OPEN A<br/><em>kitchen.</em></h1><p>Send a one-use password setup link. Sending a new invitation to an existing account lets them reset their password.</p><form onSubmit={event => void submit(event)}><label>EMAIL ADDRESS<input required type="email" autoComplete="off" value={email} onChange={event => setEmail(event.target.value)} /></label><label>KITCHEN<select value={mode} onChange={event => setMode(event.target.value as 'new' | 'existing')}><option value="new">Create a new kitchen</option><option value="existing">Add to an existing kitchen</option></select></label>{mode === 'new' ? <label>KITCHEN NAME<input required maxLength={120} value={workspaceName} onChange={event => setWorkspaceName(event.target.value)} /></label> : <label>EXISTING KITCHEN<select required value={workspaceId} onChange={event => setWorkspaceId(event.target.value)}><option value="">Choose a kitchen</option>{workspaces.map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select></label>}{error && <div className="error" role="alert">{error}</div>}{message && <div className="auth-feedback" role="status">{message}</div>}<button className="auth-submit" disabled={sending}>{sending ? 'SENDING…' : 'SEND INVITATION'} <span>→</span></button></form><button className="back-link" onClick={onBack}>← BACK TO YOUR KITCHEN</button></div><div className="auth-aside"><p>PREP WITH<br/><em> PURPOSE.</em></p><span>YLD / ADMIN</span></div></main>
}
