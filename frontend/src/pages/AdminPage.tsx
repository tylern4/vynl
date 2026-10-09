import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { UserPlus } from 'lucide-react'
import { ApiError, api } from '../api'
import { useAuth } from '../auth'
import type { Role, UserAdmin, UserStatus } from '../types'

const ROLES: Role[] = ['admin', 'user', 'read_only']

const ROLE_LABEL: Record<Role, string> = {
  admin: 'Admin',
  user: 'User',
  read_only: 'Read-only',
}

const STATUS_LABEL: Record<UserStatus, string> = {
  active: 'Active',
  pending: 'Pending',
  denied: 'Denied',
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString()
}

/** Admin-only user management (issue #9): create, approve/deny, role, reset, delete. */
export function AdminPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<UserAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  // create-user form
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'user' as Role })
  const [creating, setCreating] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [formNotice, setFormNotice] = useState<string | null>(null)

  // per-row transient UI
  const [resetId, setResetId] = useState<number | null>(null)
  const [resetPw, setResetPw] = useState('')
  const [confirmId, setConfirmId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setUsers(await api.listUsers())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load users')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const replaceUser = (updated: UserAdmin) =>
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))

  async function run(id: number, action: () => Promise<UserAdmin>) {
    setBusyId(id)
    setError(null)
    try {
      replaceUser(await action())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Action failed')
    } finally {
      setBusyId(null)
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setCreating(true)
    setFormError(null)
    setFormNotice(null)
    try {
      const created = await api.createUser({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
      })
      setUsers((prev) => [...prev, created])
      setForm({ name: '', email: '', password: '', role: 'user' })
      setFormNotice(`${created.name} added.`)
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not add the user')
    } finally {
      setCreating(false)
    }
  }

  async function handleReset(id: number) {
    if (resetPw.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    await run(id, () => api.resetUserPassword(id, resetPw))
    setResetId(null)
    setResetPw('')
  }

  async function handleDelete(id: number) {
    setBusyId(id)
    setError(null)
    try {
      await api.deleteUser(id)
      setUsers((prev) => prev.filter((u) => u.id !== id))
      setConfirmId(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete the user')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>Users</h1>
        <p className="muted">Create accounts and manage roles, access, and passwords.</p>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <section className="card section" aria-labelledby="add-user-heading">
        <h2 id="add-user-heading">Add a user</h2>
        <p className="muted">
          The account is ready to sign in immediately — no invite code or approval step.
        </p>
        <form className="admin-create" onSubmit={handleCreate}>
          <div className="admin-create-fields">
            <div className="field">
              <label htmlFor="new-name">Name</label>
              <input
                id="new-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-email">Email</label>
              <input
                id="new-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-password">Password</label>
              <input
                id="new-password"
                type="password"
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="new-role">Role</label>
              <select
                id="new-role"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {formError && (
            <p className="error-banner" role="alert">
              {formError}
            </p>
          )}
          {formNotice && (
            <p className="form-notice" role="status">
              {formNotice}
            </p>
          )}
          <div>
            <button className="btn btn-primary" type="submit" disabled={creating}>
              <UserPlus size={15} aria-hidden /> {creating ? 'Adding…' : 'Add user'}
            </button>
          </div>
        </form>
      </section>

      <section className="card section" aria-labelledby="users-heading">
        <h2 id="users-heading">All users</h2>
        {loading ? (
          <p className="muted">Loading users…</p>
        ) : (
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <th scope="col">User</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                  <th scope="col">Added</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isSelf = u.id === me?.id
                  const busy = busyId === u.id
                  return (
                    <tr key={u.id}>
                      <td>
                        <span className="admin-user-name">
                          {u.name}
                          {isSelf && <span className="admin-you">You</span>}
                        </span>
                        <span className="admin-user-email">{u.email}</span>
                      </td>
                      <td>
                        <select
                          aria-label={`Role for ${u.name}`}
                          value={u.role}
                          disabled={busy || isSelf}
                          title={isSelf ? 'You cannot change your own role' : undefined}
                          onChange={(e) => {
                            void run(u.id, () => api.setUserRole(u.id, e.target.value as Role))
                          }}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {ROLE_LABEL[r]}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <span className={`status-pill status-${u.status}`}>
                          {STATUS_LABEL[u.status]}
                        </span>
                      </td>
                      <td className="admin-date">{formatDate(u.created_at)}</td>
                      <td>
                        <div className="admin-actions">
                          {u.status !== 'active' && (
                            <button
                              className="btn btn-sm"
                              type="button"
                              disabled={busy}
                              onClick={() => {
                                void run(u.id, () => api.approveUser(u.id))
                              }}
                            >
                              Approve
                            </button>
                          )}
                          {u.status !== 'denied' && !isSelf && (
                            <button
                              className="btn btn-sm"
                              type="button"
                              disabled={busy}
                              onClick={() => {
                                void run(u.id, () => api.denyUser(u.id))
                              }}
                            >
                              Deny
                            </button>
                          )}
                          <button
                            className="btn btn-sm"
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              setConfirmId(null)
                              setResetPw('')
                              setResetId(resetId === u.id ? null : u.id)
                            }}
                          >
                            Reset password
                          </button>
                          {!isSelf && (
                            <button
                              className="btn btn-sm btn-danger"
                              type="button"
                              disabled={busy}
                              onClick={() => {
                                setResetId(null)
                                setConfirmId(confirmId === u.id ? null : u.id)
                              }}
                            >
                              Delete
                            </button>
                          )}
                        </div>

                        {resetId === u.id && (
                          <div className="admin-reset">
                            <label htmlFor={`reset-${u.id}`}>New password for {u.name}</label>
                            <input
                              id={`reset-${u.id}`}
                              type="password"
                              minLength={8}
                              value={resetPw}
                              onChange={(e) => setResetPw(e.target.value)}
                            />
                            <div className="admin-reset-actions">
                              <button
                                className="btn btn-sm btn-primary"
                                type="button"
                                disabled={busy}
                                onClick={() => {
                                  void handleReset(u.id)
                                }}
                              >
                                Save
                              </button>
                              <button
                                className="btn btn-sm"
                                type="button"
                                onClick={() => {
                                  setResetId(null)
                                  setResetPw('')
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}

                        {confirmId === u.id && (
                          <div className="confirm-row">
                            <span>Delete {u.name}? This can’t be undone.</span>
                            <div className="confirm-actions">
                              <button
                                className="btn btn-sm"
                                type="button"
                                onClick={() => setConfirmId(null)}
                              >
                                Cancel
                              </button>
                              <button
                                className="btn btn-sm btn-danger"
                                type="button"
                                disabled={busy}
                                onClick={() => {
                                  void handleDelete(u.id)
                                }}
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
