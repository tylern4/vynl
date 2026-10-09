import { Link, Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { Dices, Disc3, Library, Moon, Plus, Search, Settings, Sun, Users } from 'lucide-react'
import { AdminRoute, ProtectedRoute, useAuth } from './auth'
import { useTheme } from './theme'
import { LoginPage } from './pages/Login'
import { RegisterPage } from './pages/Register'
import { AdminPage } from './pages/AdminPage'
import { SettingsPage } from './pages/SettingsPage'
import { ShelfPage } from './pages/ShelfPage'
import { AlbumDetailPage } from './pages/AlbumDetailPage'
import { AddAlbumPage } from './pages/AddAlbumPage'
import { ManualAlbumPage } from './pages/ManualAlbumPage'
import { FindPage } from './pages/FindPage'
import { RecommendPage } from './pages/RecommendPage'

function AppShell() {
  const { user, logout } = useAuth()
  const { mode, toggleMode } = useTheme()

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <Disc3 size={22} /> vynl
        </Link>
        <nav className="topnav" aria-label="Primary">
          <NavLink to="/" end>
            <Library size={15} aria-hidden /> Shelf
          </NavLink>
          <NavLink to="/add">
            <Plus size={15} aria-hidden /> Add
          </NavLink>
          <NavLink to="/find">
            <Search size={15} aria-hidden /> Find
          </NavLink>
          <NavLink to="/recommend">
            <Dices size={15} aria-hidden /> Recommend
          </NavLink>
          {user?.role === 'admin' && (
            <NavLink to="/admin">
              <Users size={15} aria-hidden /> Users
            </NavLink>
          )}
        </nav>
        <div className="topbar-actions">
          <span className="topbar-user">{user?.name}</span>
          <Link to="/settings" className="icon-link" aria-label="Settings">
            <Settings size={18} aria-hidden />
          </Link>
          <button className="icon-btn" type="button" onClick={toggleMode} aria-label="Toggle theme">
            {mode === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="btn btn-ghost btn-sm" type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<ShelfPage />} />
        <Route path="/album/:id" element={<AlbumDetailPage />} />
        <Route path="/add" element={<AddAlbumPage />} />
        <Route path="/add/manual" element={<ManualAlbumPage />} />
        <Route path="/find" element={<FindPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AdminPage />
            </AdminRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
