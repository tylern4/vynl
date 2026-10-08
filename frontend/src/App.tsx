import { Link, Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { Dices, Disc3, Moon, Sun } from 'lucide-react'
import { ProtectedRoute, useAuth } from './auth'
import { useTheme } from './theme'
import { LoginPage } from './pages/Login'
import { RegisterPage } from './pages/Register'
import { ShelfPage } from './pages/ShelfPage'
import { AlbumDetailPage } from './pages/AlbumDetailPage'
import { AddAlbumPage } from './pages/AddAlbumPage'
import { FindPage } from './pages/FindPage'
import { RecommendPage } from './pages/RecommendPage'

function AppShell() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <Disc3 size={22} /> vynl
        </Link>
        <nav className="topnav">
          <NavLink to="/" end>
            Shelf
          </NavLink>
          <NavLink to="/add">Add</NavLink>
          <NavLink to="/find">Find</NavLink>
          <NavLink to="/recommend">
            <Dices size={15} aria-hidden /> Recommend
          </NavLink>
        </nav>
        <div className="topbar-actions">
          <span className="topbar-user">{user?.name}</span>
          <button className="icon-btn" type="button" onClick={toggle} aria-label="Toggle theme">
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
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
        <Route path="/find" element={<FindPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
