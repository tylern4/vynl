import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Disc3 } from 'lucide-react'
import { useAuth } from '../auth'
import { ApiError } from '../api'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [pending, setPending] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await register(name.trim(), email.trim(), password, inviteCode.trim())
      if (res.access_token) {
        navigate('/', { replace: true })
      } else {
        setPending(true)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (pending) {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <div>
            <h1 className="auth-title">
              <Disc3 size={26} /> vynl
            </h1>
            <p className="auth-sub">Account created — awaiting approval.</p>
          </div>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem', margin: 0 }}>
            Your account is pending approval by an admin. You&apos;ll be able to sign in once it&apos;s
            approved.
          </p>
          <Link className="btn btn-primary btn-block" to="/login">
            Go to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <div>
          <h1 className="auth-title">
            <Disc3 size={26} /> vynl
          </h1>
          <p className="auth-sub">Create an account. An admin will approve your access.</p>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <div className="field">
          <label htmlFor="name">Name</label>
          <input
            id="name"
            type="text"
            required
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>At least 8 characters.</span>
        </div>

        <div className="field">
          <label htmlFor="invite">Setup code (first account only)</label>
          <input
            id="invite"
            type="text"
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
            Optional — only needed to set up the very first account on this instance.
          </span>
        </div>

        <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
          {submitting ? <span className="spinner" /> : 'Create account'}
        </button>

        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  )
}
