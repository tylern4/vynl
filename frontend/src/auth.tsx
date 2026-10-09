import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { api, clearToken, getToken, setToken } from './api'
import type { RegisterResult, User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  canEdit: boolean
  login: (email: string, password: string) => Promise<void>
  register: (
    name: string,
    email: string,
    password: string,
    inviteCode: string,
  ) => Promise<RegisterResult>
  setToken: (token: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!getToken()) {
        setLoading(false)
        return
      }
      try {
        const me = await api.me()
        if (!cancelled) setUser(me)
      } catch {
        clearToken()
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const canEdit = user?.role === 'admin' || user?.role === 'user'

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      canEdit,
      login: async (email, password) => {
        const res = await api.login({ email, password })
        setToken(res.access_token)
        setUser(res.user)
      },
      register: async (name, email, password, inviteCode) => {
        const res = await api.register({ name, email, password, invite_code: inviteCode })
        if (res.access_token) {
          setToken(res.access_token)
          setUser(res.user)
        }
        return res
      },
      setToken: (token: string) => {
        setToken(token)
      },
      logout: () => {
        clearToken()
        setUser(null)
      },
    }),
    [user, loading, canEdit],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="centered">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

/** Like ProtectedRoute, but admin-only (issue #9). Non-admins go to the shelf. */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="centered">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/" replace />
  return children
}
